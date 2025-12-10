"""
Окно настроек приложения
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTabWidget, QWidget, QCheckBox,
                             QGroupBox, QFormLayout, QMessageBox, QSpinBox,
                             QLineEdit, QComboBox)
from PyQt5.QtCore import Qt
from core.settings import get_settings

class SettingsWindow(QDialog):
    """Окно настроек приложения"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = get_settings()
        self.setWindowTitle("Настройки")
        self.setMinimumSize(600, 400)
        self.setup_ui()
        self.load_settings()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Вкладки
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Вкладка "Интерфейс табло"
        scoreboard_tab = self.create_scoreboard_tab()
        self.tabs.addTab(scoreboard_tab, "Интерфейс табло")
        
        # Вкладка "Турнир"
        tournament_tab = self.create_tournament_tab()
        self.tabs.addTab(tournament_tab, "Турнир")

        # Вкладка "Сеть"
        network_tab = self.create_network_tab()
        self.tabs.addTab(network_tab, "Сетевой модуль")
        
        # Кнопки
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        ok_btn = QPushButton("ОК")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        buttons_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)
        
        apply_btn = QPushButton("Применить")
        apply_btn.clicked.connect(self.apply_settings)
        buttons_layout.addWidget(apply_btn)
        
        layout.addLayout(buttons_layout)
    
    def create_scoreboard_tab(self):
        """Создает вкладку настроек интерфейса табло"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        group = QGroupBox("Отображение элементов на табло")
        form_layout = QFormLayout(group)
        
        # Чекбоксы для элементов табло
        self.show_passivity_cb = QCheckBox("Показывать пассивность")
        self.show_passivity_cb.setToolTip("Если выключено, пассивность не будет отображаться на табло и кнопки в панели управления будут скрыты")
        form_layout.addRow(self.show_passivity_cb)
        
        self.show_cautions_cb = QCheckBox("Показывать предупреждения")
        self.show_cautions_cb.setToolTip("Если выключено, предупреждения не будут отображаться на табло и кнопки в панели управления будут скрыты")
        form_layout.addRow(self.show_cautions_cb)
        
        self.show_period_cb = QCheckBox("Показывать период")
        self.show_period_cb.setToolTip("Если выключено, период не будет отображаться на табло")
        form_layout.addRow(self.show_period_cb)
        
        self.show_opponent_wait_timer_cb = QCheckBox("Показывать таймер ожидания соперника")
        self.show_opponent_wait_timer_cb.setToolTip("Если включено, на табло и в панели управления будет отображаться таймер ожидания соперника")
        form_layout.addRow(self.show_opponent_wait_timer_cb)
        
        layout.addWidget(group)
        layout.addStretch()
        
        return tab
    
    def create_tournament_tab(self):
        """Создает вкладку настроек турнира"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        group = QGroupBox("Настройки турнира")
        form_layout = QFormLayout(group)
        
        # Количество ковров
        self.number_of_mats_spin = QSpinBox()
        self.number_of_mats_spin.setMinimum(1)
        self.number_of_mats_spin.setMaximum(5)
        self.number_of_mats_spin.setToolTip("Количество ковров для проведения турнира (от 1 до 5)")
        form_layout.addRow("Количество ковров:", self.number_of_mats_spin)
        
        layout.addWidget(group)

        timers_group = QGroupBox("Таймеры")
        timers_layout = QFormLayout(timers_group)

        self.period_duration_spin = QSpinBox()
        self.period_duration_spin.setRange(30, 900)
        self.period_duration_spin.setSuffix(" сек")
        timers_layout.addRow("Длительность периода:", self.period_duration_spin)

        self.break_duration_spin = QSpinBox()
        self.break_duration_spin.setRange(0, 300)
        self.break_duration_spin.setSuffix(" сек")
        timers_layout.addRow("Перерыв между периодами:", self.break_duration_spin)

        self.wait_duration_spin = QSpinBox()
        self.wait_duration_spin.setRange(10, 600)
        self.wait_duration_spin.setSuffix(" сек")
        timers_layout.addRow("Таймер ожидания соперника:", self.wait_duration_spin)

        layout.addWidget(timers_group)
        layout.addStretch()
        
        return tab

    def create_network_tab(self):
        """Создает вкладку настроек сетевого модуля."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Роль устройства")
        form = QFormLayout(group)

        self.role_combo = QComboBox()
        self.role_combo.addItems(["coordinator", "node", "relay"])
        form.addRow("Роль:", self.role_combo)

        self.mat_spin = QSpinBox()
        self.mat_spin.setRange(1, 8)
        form.addRow("Ковёр:", self.mat_spin)

        self.device_edit = QLineEdit()
        form.addRow("Имя устройства:", self.device_edit)

        self.coordinator_edit = QLineEdit()
        self.coordinator_edit.setPlaceholderText("IP главного ПК (для узла)")
        form.addRow("IP координатора:", self.coordinator_edit)

        self.relay_cb = QCheckBox("Разрешить ретрансляцию расписания")
        form.addRow(self.relay_cb)

        self.auto_start_cb = QCheckBox("Автозапуск модуля при старте")
        form.addRow(self.auto_start_cb)

        layout.addWidget(group)
        layout.addStretch()
        return tab
    
    def load_settings(self):
        """Загружает текущие настройки в интерфейс"""
        self.show_passivity_cb.setChecked(
            self.settings.get_scoreboard_setting("show_passivity")
        )
        self.show_cautions_cb.setChecked(
            self.settings.get_scoreboard_setting("show_cautions")
        )
        self.show_period_cb.setChecked(
            self.settings.get_scoreboard_setting("show_period")
        )
        self.show_opponent_wait_timer_cb.setChecked(
            self.settings.get_scoreboard_setting("show_opponent_wait_timer")
        )
        # Загружаем настройки турнира
        self.number_of_mats_spin.setValue(
            self.settings.get("tournament", "number_of_mats", 2)
        )
        self.period_duration_spin.setValue(
            self.settings.get("timers", "period_duration", 180)
        )
        self.break_duration_spin.setValue(
            self.settings.get("timers", "break_duration", 30)
        )
        self.wait_duration_spin.setValue(
            self.settings.get("timers", "opponent_wait_duration", 60)
        )

        # Сетевой модуль
        self.role_combo.setCurrentText(
            self.settings.get("network", "role", "coordinator")
        )
        self.mat_spin.setValue(
            self.settings.get("network", "mat_number", 1)
        )
        self.device_edit.setText(
            self.settings.get("network", "device_name", "Устройство")
        )
        self.coordinator_edit.setText(
            self.settings.get("network", "coordinator_host", "")
        )
        self.relay_cb.setChecked(
            self.settings.get("network", "allow_relay", True)
        )
        self.auto_start_cb.setChecked(
            self.settings.get("network", "auto_start", True)
        )
    
    def apply_settings(self):
        """Применяет настройки"""
        self.settings.set("scoreboard", "show_passivity", self.show_passivity_cb.isChecked())
        self.settings.set("scoreboard", "show_cautions", self.show_cautions_cb.isChecked())
        self.settings.set("scoreboard", "show_period", self.show_period_cb.isChecked())
        self.settings.set("scoreboard", "show_opponent_wait_timer", self.show_opponent_wait_timer_cb.isChecked())
        # Сохраняем настройки турнира
        self.settings.set("tournament", "number_of_mats", self.number_of_mats_spin.value())
        self.settings.set("timers", "period_duration", self.period_duration_spin.value())
        self.settings.set("timers", "break_duration", self.break_duration_spin.value())
        self.settings.set("timers", "opponent_wait_duration", self.wait_duration_spin.value())

        # Сохраняем сеть
        self.settings.set("network", "role", self.role_combo.currentText())
        self.settings.set("network", "mat_number", self.mat_spin.value())
        self.settings.set("network", "device_name", self.device_edit.text() or "Устройство")
        self.settings.set("network", "coordinator_host", self.coordinator_edit.text())
        self.settings.set("network", "allow_relay", self.relay_cb.isChecked())
        self.settings.set("network", "auto_start", self.auto_start_cb.isChecked())
        
        QMessageBox.information(self, "Настройки", "Настройки применены. Изменения вступят в силу после перезапуска соответствующих окон.")
    
    def accept(self):
        """Принимает изменения и закрывает окно"""
        self.apply_settings()
        super().accept()
