import json
import socket
import threading
import time
import hashlib
from typing import Any, Callable, Dict, Optional, List

from core.constants import (
    SCHEDULE_SYNC_PORT,
    SCHEDULE_SYNC_HEARTBEAT,
    SCHEDULE_SYNC_TIMEOUT,
)
from core.utils import get_local_ip


def _hash_schedule(schedule: Any) -> str:
    """Возвращает стабильный хеш расписания для сравнения версий."""
    try:
        dumped = json.dumps(schedule or [], ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(dumped.encode("utf-8")).hexdigest()
    except Exception:
        return ""


def _deduplicate_schedule(schedule: Any) -> Any:
    """
    Убирает дубли матчей по match_id (с сохранением порядка).
    Если match_id пуст, используем ключ по набору полей, чтобы не плодить копии.
    """
    if not isinstance(schedule, list):
        return schedule

    seen_ids = set()
    cleaned = []
    for match in schedule:
        if not isinstance(match, dict):
            continue
        mid = match.get("match_id") or match.get("id")
        key = mid or (
            match.get("category"),
            match.get("wrestler1"),
            match.get("wrestler2"),
            match.get("mat"),
            match.get("time"),
            match.get("round"),
        )
        if key in seen_ids:
            continue
        seen_ids.add(key)
        cleaned.append(match)
    return cleaned


MAX_UDP_PAYLOAD = 60000  # небольшой запас от системного лимита ~64К для UDP
DEFAULT_SCHEDULE_CHUNK = 80  # кол-во матчей в одном пакете (держим размером < MAX_UDP_PAYLOAD)


class ScheduleSyncService:
    """
    Простой модуль синхронизации расписания по UDP broadcast в одной подсети.

    Роли:
      - coordinator: главный ПК, рассылает расписание и принимает статусы ковров.
      - node: узел ковра, получает расписание и шлет свой статус.
      - relay: узел, который ретранслирует schedule_full/heartbeat для покрытия нескольких узлов.
    """

    def __init__(
        self,
        on_schedule_received: Optional[Callable[[Any, str], None]] = None,
        on_peer_update: Optional[Callable[[Dict[str, Dict[str, Any]]], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        on_log_received: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.on_schedule_received = on_schedule_received
        self.on_peer_update = on_peer_update
        self.on_log = on_log
        self.on_log_received = on_log_received

        self.role = "node"
        self.device_name = socket.gethostname()
        self.device_id = f"{self.device_name}-{int(time.time()*1000)}"
        self.mat_number = 1
        self.allow_relay = True
        self.coordinator_host: Optional[str] = None

        self._sock: Optional[socket.socket] = None
        self._receiver_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self.running = False

        self.schedule_hash = ""
        self.peers: Dict[str, Dict[str, Any]] = {}
        # Хранилище собираемых чанков расписания: transfer_id -> {"total": int, "received": {idx: part}, "hash": str}
        self._incoming_schedule_parts: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #
    def start(
        self,
        role: str = "node",
        mat_number: int = 1,
        allow_relay: bool = True,
        coordinator_host: str = "",
        device_name: Optional[str] = None,
    ):
        """Запуск сервиса."""
        self.stop()
        # Небольшая задержка для освобождения порта на Linux
        time.sleep(0.1)

        self.role = role
        self.mat_number = mat_number or 1
        self.allow_relay = allow_relay
        self.coordinator_host = coordinator_host or None
        if device_name:
            self.device_name = device_name
            self.device_id = f"{self.device_name}-{int(time.time()*1000)}"

        self.running = True
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Включаем SO_REUSEADDR для возможности повторного использования порта
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.settimeout(1.0)
        
        # Пытаемся привязать порт с обработкой ошибки "Address already in use"
        try:
            self._sock.bind(("", SCHEDULE_SYNC_PORT))
        except OSError as e:
            if e.errno == 98 or "Address already in use" in str(e):  # Linux errno 98, Windows может быть другой текст
                self._log(f"[sync] Порт {SCHEDULE_SYNC_PORT} занят, ожидание освобождения...")
                time.sleep(0.5)
                try:
                    self._sock.close()
                except:
                    pass
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                self._sock.settimeout(1.0)
                self._sock.bind(("", SCHEDULE_SYNC_PORT))
            else:
                raise

        try:
            self._receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)
            self._receiver_thread.start()

            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._heartbeat_thread.start()

            self._log(f"[sync] старт модуля ({self.role}), порт {SCHEDULE_SYNC_PORT}")
        except Exception as e:
            self.running = False
            self._log(f"[sync] Ошибка при запуске потоков: {e}")
            raise

    def stop(self):
        """Остановка сервиса."""
        self.running = False
        
        # Закрываем сокет, чтобы освободить порт
        if self._sock:
            try:
                # Закрываем сокет перед закрытием потоков
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        
        # Даем потокам время завершиться
        if self._receiver_thread and self._receiver_thread.is_alive():
            self._receiver_thread.join(timeout=0.5)
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=0.5)

    def push_schedule(self, tournament_data: Dict[str, Any]):
        """Отправка полного расписания всем узлам."""
        schedule = _deduplicate_schedule((tournament_data or {}).get("schedule", []))
        self.schedule_hash = _hash_schedule(schedule)
        payload = {
            "type": "schedule_full",
            "schedule": schedule,
            "schedule_hash": self.schedule_hash,
            "role": self.role,
            "mat": self.mat_number,
            "device": self.device_name,
            "device_id": self.device_id,
            "ts": time.time(),
        }

        # Пробуем отправить одним пакетом; если не помещается в безопасный размер UDP — шлем чанками
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(raw) <= MAX_UDP_PAYLOAD:
            self._send(payload)
            self._log(f"[sync] отправлено расписание ({len(schedule)} записей)")
        else:
            self._send_schedule_chunks(schedule)

    def send_mat_status(self, status: str, current_match: Optional[str] = None):
        """Отправка статуса ковра координатору/узлам."""
        payload = {
            "type": "mat_status",
            "mat": self.mat_number,
            "status": status,
            "current_match": current_match,
            "role": self.role,
            "device": self.device_name,
            "device_id": self.device_id,
            "ts": time.time(),
            "schedule_hash": self.schedule_hash,
        }
        self._send(payload, target=self.coordinator_host)

    def update_mat_number(self, mat_number: int):
        self.mat_number = mat_number or 1

    def get_peers(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает актуальный список узлов."""
        return dict(self.peers)

    # ------------------------------------------------------------------ #
    #  Internal
    # ------------------------------------------------------------------ #
    def _receiver_loop(self):
        while self.running and self._sock:
            try:
                data, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                message = json.loads(data.decode("utf-8"))
            except Exception:
                continue

            self._handle_message(message, addr[0])

        self._log("[sync] прием остановлен")

    def _heartbeat_loop(self):
        while self.running and self._sock:
            hb = {
                "type": "heartbeat",
                "role": self.role,
                "mat": self.mat_number,
                "device": self.device_name,
                "device_id": self.device_id,
                "ip": get_local_ip(),
                "schedule_hash": self.schedule_hash,
                "ts": time.time(),
            }
            self._send(hb)
            self._drop_stale_peers()
            time.sleep(SCHEDULE_SYNC_HEARTBEAT)

    def _send(self, payload: Dict[str, Any], target: Optional[str] = None):
        if not self._sock:
            return
        try:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            addr = (target or "<broadcast>", SCHEDULE_SYNC_PORT)
            self._sock.sendto(raw, addr)
        except Exception as e:
            self._log(f"[sync] ошибка отправки: {e}")
    
    def send_log(self, log_data: Dict[str, Any]):
        """Отправляет лог-запись на coordinator"""
        if self.role == "coordinator":
            # Если мы coordinator, не отправляем сами себе
            return
        
        if not self.coordinator_host:
            return
        
        payload = {
            "type": "log_entry",
            "log_data": log_data,
            "device": self.device_name,
            "device_id": self.device_id,
            "ts": time.time(),
        }
        self._send(payload, target=self.coordinator_host)

    def _send_schedule_chunks(self, schedule: List[Any]):
        """Безопасно отправляет расписание несколькими пакетами, чтобы избежать переполнения UDP."""
        chunk_size = DEFAULT_SCHEDULE_CHUNK
        total_chunks = max(1, (len(schedule) + chunk_size - 1) // chunk_size)
        transfer_id = f"{self.schedule_hash}-{int(time.time()*1000)}"

        for idx in range(total_chunks):
            part = schedule[idx * chunk_size : (idx + 1) * chunk_size]
            payload = {
                "type": "schedule_chunk",
                "chunk_index": idx,
                "total_chunks": total_chunks,
                "schedule_part": part,
                "schedule_hash": self.schedule_hash,
                "role": self.role,
                "mat": self.mat_number,
                "device": self.device_name,
                "device_id": self.device_id,
                "transfer_id": transfer_id,
                "ts": time.time(),
            }
            self._send(payload)

        self._log(
            f"[sync] отправлено расписание чанками ({len(schedule)} записей, {total_chunks} пакетов)"
        )

    def _handle_message(self, message: Dict[str, Any], sender_ip: str):
        if not isinstance(message, dict):
            return
        # Не обрабатываем свои сообщения
        if message.get("device_id") == self.device_id:
            return

        msg_type = message.get("type")
        device_id = message.get("device_id", sender_ip)
        now = time.time()

        # Обновляем peers
        peer_info = self.peers.get(device_id, {})
        peer_info.update(
            {
                "device": message.get("device"),
                "ip": sender_ip,
                "role": message.get("role"),
                "mat": message.get("mat"),
                "schedule_hash": message.get("schedule_hash"),
                "last_seen": now,
                "status": message.get("status"),
                "current_match": message.get("current_match"),
            }
        )
        self.peers[device_id] = peer_info
        if self.on_peer_update:
            self.on_peer_update(self.get_peers())

        if msg_type == "schedule_full":
            incoming_hash = message.get("schedule_hash", "")
            if incoming_hash and incoming_hash != self.schedule_hash:
                self.schedule_hash = incoming_hash
                if self.on_schedule_received:
                    self.on_schedule_received(
                        _deduplicate_schedule(message.get("schedule")), sender_ip
                    )
                # Ретрансляция при необходимости (только для node/relay, НЕ для coordinator)
                # Coordinator принимает расписание, но не отправляет его обратно, чтобы избежать циклов
                if self.allow_relay and self.role != "coordinator":
                    self._send(message)
        elif msg_type == "schedule_chunk":
            transfer_id = message.get("transfer_id") or message.get("schedule_hash") or ""
            chunk_idx = message.get("chunk_index")
            total_chunks = message.get("total_chunks") or 1
            incoming_hash = message.get("schedule_hash", "")
            part = message.get("schedule_part") or []

            # Валидация индекса
            if chunk_idx is None or chunk_idx < 0 or chunk_idx >= total_chunks:
                return

            # Сохраняем кусок
            entry = self._incoming_schedule_parts.setdefault(
                transfer_id,
                {"total": total_chunks, "received": {}, "hash": incoming_hash, "ts": time.time()},
            )
            entry["received"][chunk_idx] = part
            entry["total"] = total_chunks  # на случай, если первый пакет пришел не первым
            entry["hash"] = incoming_hash or entry.get("hash", "")

            # Ретрансляция чанка для покрытия сети (аналогично полной отправке)
            if self.allow_relay and self.role != "coordinator":
                self._send(message)

            # Проверяем, собрали ли всё
            if len(entry["received"]) >= entry["total"]:
                combined: List[Any] = []
                for idx in range(entry["total"]):
                    combined.extend(entry["received"].get(idx, []))

                self._incoming_schedule_parts.pop(transfer_id, None)

                if entry["hash"] and entry["hash"] != self.schedule_hash:
                    self.schedule_hash = entry["hash"]
                    if self.on_schedule_received:
                        self.on_schedule_received(_deduplicate_schedule(combined), sender_ip)
                    # Ретрансляция при необходимости (только для node/relay, НЕ для coordinator)
                    # Coordinator принимает расписание, но не отправляет его обратно, чтобы избежать циклов
                    if self.allow_relay and self.role != "coordinator":
                        # Рассылаем дальше уже собранное расписание, соблюдая лимит
                        self._send_schedule_chunks(_deduplicate_schedule(combined))
        elif msg_type == "mat_status":
            # Координатор обновляет статус ковра
            pass  # статус уже записан в peers
        elif msg_type == "heartbeat":
            # Дополнительно ничего не делаем, peers уже обновили
            pass
        elif msg_type == "log_entry":
            # Получен лог от другого устройства - сохраняем на coordinator
            if self.role == "coordinator" and self.on_log_received:
                self.on_log_received(message.get("log_data", {}))

    def _drop_stale_peers(self):
        """Убираем узлы, которые давно не отвечали."""
        now = time.time()
        removed = []
        for device_id, info in list(self.peers.items()):
            if now - info.get("last_seen", 0) > SCHEDULE_SYNC_TIMEOUT:
                removed.append(device_id)
                self.peers.pop(device_id, None)
        if removed and self.on_peer_update:
            self.on_peer_update(self.get_peers())

    def _log(self, text: str):
        if self.on_log:
            self.on_log(text)

