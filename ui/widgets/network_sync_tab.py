from datetime import datetime
import time
from typing import Any, Callable, Dict, Optional

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTextEdit,
)
from PyQt5.QtCore import Qt

from core.settings import get_settings
from network.schedule_sync import ScheduleSyncService


class NetworkSyncTab(QWidget):
    """UI-вкладка для настройки и мониторинга модуля синхронизации расписаний."""

    def __init__(
        self,
        tournament_data: Dict[str, Any],
        schedule_sync: ScheduleSyncService,
        on_schedule_apply: Optional[Callable[[Any], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.tournament_data = tournament_data
        self.schedule_sync = schedule_sync
        self.on_schedule_apply = on_schedule_apply
        self.settings = get_settings()
        self._build_ui()
        self._load_defaults()
        self._connect_service_callbacks()

    # ------------------------------------------------------------------ #
    #  UI
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        layout = QVBoxLayout(self)

        cfg_group = QGroupBox("Режим и параметры")
        cfg_layout = QHBoxLayout(cfg_group)

        self.role_combo = QComboBox()
        self.role_combo.addItems(["coordinator", "node", "relay"])
        cfg_layout.addWidget(QLabel("Роль:"))
        cfg_layout.addWidget(self.role_combo)

        self.mat_spin = QSpinBox()
        self.mat_spin.setRange(1, 8)
        cfg_layout.addWidget(QLabel("Ковёр:"))
        cfg_layout.addWidget(self.mat_spin)

        self.device_edit = QLineEdit()
        self.device_edit.setPlaceholderText("Имя устройства")
        cfg_layout.addWidget(QLabel("Имя:"))
        cfg_layout.addWidget(self.device_edit)

        self.coordinator_edit = QLineEdit()
        self.coordinator_edit.setPlaceholderText("IP главного ПК (для узла)")
        cfg_layout.addWidget(self.coordinator_edit)

        self.relay_cb = QCheckBox("Разрешить ретрансляцию")
        self.relay_cb.setChecked(True)
        cfg_layout.addWidget(self.relay_cb)

        layout.addWidget(cfg_group)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Старт модуля")
        self.stop_btn = QPushButton("Стоп")
        self.push_btn = QPushButton("Передать расписание")
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(self.push_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        peers_group = QGroupBox("Узлы в сети")
        peers_layout = QVBoxLayout(peers_group)
        self.peers_table = QTableWidget(0, 6)
        self.peers_table.setHorizontalHeaderLabels(
            ["Имя", "Роль", "Ковёр", "IP", "Статус", "Обновл."]
        )
        self.peers_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        peers_layout.addWidget(self.peers_table)
        layout.addWidget(peers_group)

        log_group = QGroupBox("Лог модуля")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)

        # Подключения
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.push_btn.clicked.connect(self._on_push_schedule)
        # Автоматически сохраняем mat_number при изменении (без перезапуска сервиса)
        self.mat_spin.valueChanged.connect(self._on_mat_changed)

    def _load_defaults(self):
        self.role_combo.setCurrentText(self.settings.get("network", "role", "coordinator"))
        self.mat_spin.setValue(int(self.settings.get("network", "mat_number", 1)))
        self.device_edit.setText(self.settings.get("network", "device_name", "Устройство"))
        self.coordinator_edit.setText(self.settings.get("network", "coordinator_host", ""))
        self.relay_cb.setChecked(bool(self.settings.get("network", "allow_relay", True)))

    def _connect_service_callbacks(self):
        # Переназначаем колбеки сервиса
        if self.schedule_sync:
            self.schedule_sync.on_schedule_received = self._on_remote_schedule
            self.schedule_sync.on_peer_update = self._on_peer_update
            self.schedule_sync.on_log = self._log

    # ------------------------------------------------------------------ #
    #  Actions
    # ------------------------------------------------------------------ #
    def _on_start(self):
        role = self.role_combo.currentText()
        mat = self.mat_spin.value()
        name = self.device_edit.text().strip() or "Устройство"
        host = self.coordinator_edit.text().strip()
        allow_relay = self.relay_cb.isChecked()

        self.schedule_sync.start(
            role=role,
            mat_number=mat,
            allow_relay=allow_relay,
            coordinator_host=host,
            device_name=name,
        )
        self._log(f"Старт роли {role}, ковёр {mat}")

        # Сохраняем в настройки
        self.settings.set("network", "role", role)
        self.settings.set("network", "mat_number", mat)
        self.settings.set("network", "device_name", name)
        self.settings.set("network", "coordinator_host", host)
        self.settings.set("network", "allow_relay", allow_relay)
        
        # ВАЖНО: также обновляем mat_number в сервисе, если он уже запущен
        # Это нужно для случаев, когда пользователь меняет mat_number без перезапуска
        if hasattr(self.schedule_sync, 'update_mat_number'):
            self.schedule_sync.update_mat_number(mat)

    def _on_stop(self):
        if self.schedule_sync:
            self.schedule_sync.stop()
        self._log("Модуль остановлен")

    def _on_mat_changed(self, value):
        """Обработчик изменения номера ковра - автоматически сохраняет в настройки"""
        # Сохраняем в настройки сразу при изменении
        self.settings.set("network", "mat_number", value)
        # Обновляем mat_number в сервисе, если он запущен
        if self.schedule_sync and hasattr(self.schedule_sync, 'update_mat_number'):
            self.schedule_sync.update_mat_number(value)
            self._log(f"Номер ковра обновлён на {value}")

    def _on_push_schedule(self):
        if not self.tournament_data:
            self._log("Нет данных турнира")
            return
        if self.schedule_sync:
            # Перед отправкой убеждаемся, что mat_number актуален
            current_mat = self.mat_spin.value()
            if hasattr(self.schedule_sync, 'update_mat_number'):
                self.schedule_sync.update_mat_number(current_mat)
            self.schedule_sync.push_schedule(self.tournament_data)

    def _on_remote_schedule(self, schedule, sender_ip: str):
        if not schedule:
            return
        if self.on_schedule_apply:
            self.on_schedule_apply(schedule)
        self._log(f"Принято расписание от {sender_ip} ({len(schedule)} записей)")

    def _on_peer_update(self, peers: Dict[str, Dict[str, Any]]):
        self.peers_table.setRowCount(0)
        for info in peers.values():
            row = self.peers_table.rowCount()
            self.peers_table.insertRow(row)
            items = [
                info.get("device", ""),
                info.get("role", ""),
                str(info.get("mat", "")),
                info.get("ip", ""),
                info.get("status", "") or info.get("current_match", "") or "",
                datetime.fromtimestamp(info.get("last_seen", time.time())).strftime("%H:%M:%S"),
            ]
            for col, value in enumerate(items):
                self.peers_table.setItem(row, col, QTableWidgetItem(str(value)))

    def _log(self, text: str):
        now = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{now}] {text}")

    # ------------------------------------------------------------------ #
    #  External API
    # ------------------------------------------------------------------ #
    def update_data(self, tournament_data: Dict[str, Any]):
        """Обновление данных турнира (для последующей рассылки)."""
        self.tournament_data = tournament_data


