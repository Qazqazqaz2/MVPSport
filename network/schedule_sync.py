import json
import socket
import threading
import time
import hashlib
from typing import Any, Callable, Dict, Optional

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
    ):
        self.on_schedule_received = on_schedule_received
        self.on_peer_update = on_peer_update
        self.on_log = on_log

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

        self.role = role
        self.mat_number = mat_number or 1
        self.allow_relay = allow_relay
        self.coordinator_host = coordinator_host or None
        if device_name:
            self.device_name = device_name
            self.device_id = f"{self.device_name}-{int(time.time()*1000)}"

        self.running = True
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.settimeout(1.0)
        self._sock.bind(("", SCHEDULE_SYNC_PORT))

        self._receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)
        self._receiver_thread.start()

        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        self._log(f"[sync] старт модуля ({self.role}), порт {SCHEDULE_SYNC_PORT}")

    def stop(self):
        """Остановка сервиса."""
        self.running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None

    def push_schedule(self, tournament_data: Dict[str, Any]):
        """Отправка полного расписания всем узлам."""
        schedule = (tournament_data or {}).get("schedule", [])
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
        self._send(payload)
        self._log(f"[sync] отправлено расписание ({len(schedule)} записей)")

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
                    self.on_schedule_received(message.get("schedule"), sender_ip)
                # Ретрансляция при необходимости
                if self.allow_relay and self.role != "coordinator":
                    self._send(message)
        elif msg_type == "mat_status":
            # Координатор обновляет статус ковра
            pass  # статус уже записан в peers
        elif msg_type == "heartbeat":
            # Дополнительно ничего не делаем, peers уже обновили
            pass

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

