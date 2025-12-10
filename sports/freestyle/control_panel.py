# sports/freestyle/control_panel.py
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QTimer, QTime
from core.models import Wrestler, MatchHistory
from core.network import NetworkManager
from ..greco_roman.constants import *  # ← НЕТ! Динамически импортируем
import importlib

# Динамический импорт констант
constants = importlib.import_module("sports.freestyle.constants")

class ControlPanel(QWidget):
    def __init__(self, tournament_data, network_manager, mat_number, parent=None):
        super().__init__(parent)
        self.red = Wrestler("Красный")
        self.blue = Wrestler("Синий")
        self.current_period = 1
        self.remaining_time = constants.PERIOD_DURATION
        self.current_time_label = QLabel("02:00")
        self.current_time_label.setStyleSheet("font-size: 20px; font-weight: bold; padding: 5px;")
        time_layout = QHBoxLayout()
        time_layout.addWidget(self.current_time_label)

        # Новый селектор времени для ручного изменения
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("mm:ss")
        self.time_edit.setTime(QTime(0, constants.PERIOD_DURATION // 60, constants.PERIOD_DURATION % 60))
        self.time_edit.timeChanged.connect(self.handle_time_edit)
        time_layout.addWidget(self.time_edit)

        # ... остальное как раньше, но с constants.*