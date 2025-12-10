from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QMainWindow, QHBoxLayout, 
                             QPushButton, QApplication, QMessageBox, QShortcut)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QPropertyAnimation
from PyQt5.QtGui import QKeySequence, QBrush, QColor, QKeyEvent
from core.constants import *
from core.network import NetworkManager
from core.settings import get_settings

class ScoreboardDisplay(QWidget):
    def __init__(self, parent=None, network_manager=None):
        super().__init__(parent)
        self.network_manager = network_manager
        self.settings = get_settings()
        self.font_update_timer = QTimer()
        self.font_update_timer.setSingleShot(True)
        self.font_update_timer.timeout.connect(self.update_font_sizes)
        self._last_settings_mtime = 0
        self.setup_ui()

    def setup_ui(self):
        # Устанавливаем черный фон для всего виджета
        self.setStyleSheet("background-color: #000000;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # Используем QHBoxLayout для основного расположения
        main_layout = QHBoxLayout()
        layout.addLayout(main_layout)

        # Левая половина - Красный (увеличиваем блок имени)
        red_container = QWidget()
        red_container.setStyleSheet("background-color: #8B0000; border: 5px solid #ff0000; border-radius: 20px;")
        red_layout = QVBoxLayout(red_container)
        red_layout.setContentsMargins(15, 15, 15, 15)
        red_layout.setSpacing(10)

        self.red_name = QLabel("КРАСНЫЙ")
        self.red_name.setAlignment(Qt.AlignCenter)
        self.red_name.setWordWrap(True)
        self.red_name.setStyleSheet("font-size: 48px; font-weight: bold; color: white; padding: 15px;")
        red_layout.addWidget(self.red_name, 3)

        self.red_region = QLabel("")
        self.red_region.setAlignment(Qt.AlignCenter)
        self.red_region.setStyleSheet("font-size: 24px; color: white; padding: 5px;")  # Уменьшаем шрифт региона
        self.red_region.setMaximumHeight(200)
        red_layout.addWidget(self.red_region, 2)

        # Объединенный блок счета, предупреждений и пассивности
        red_score_container = QWidget()
        red_score_container.setStyleSheet("background-color: #600000; border-radius: 15px;")
        red_score_layout = QVBoxLayout(red_score_container)
        red_score_layout.setContentsMargins(20, 15, 20, 15)

        self.red_points = QLabel("0")
        self.red_points.setAlignment(Qt.AlignCenter)
        self.red_points.setStyleSheet("font-size: 120px; font-weight: bold; color: white; border: none;")
        red_score_layout.addWidget(self.red_points)

        # Блок предупреждений и пассивности
        red_details = QHBoxLayout()
        red_detail = QHBoxLayout()

        self.red_cautions = QLabel("Предупреждения: 0")
        self.red_cautions.setAlignment(Qt.AlignCenter)
        self.red_cautions.setStyleSheet("font-size: 32px; color: #ffcc00; border: none;")
        red_detail.addWidget(self.red_cautions)

        self.red_passivity = QLabel("Пассивность: 0")
        self.red_passivity.setAlignment(Qt.AlignCenter)
        self.red_passivity.setStyleSheet("font-size: 32px; color: #ffcc00; border: none;")
        red_details.addWidget(self.red_passivity)

        red_score_layout.addLayout(red_details)
        red_score_layout.addLayout(red_detail)
        red_layout.addWidget(red_score_container, 5)

        main_layout.addWidget(red_container)

        # Центральная часть с временем и периодом
        center_container = QWidget()
        center_container.setStyleSheet("background-color: #000000;")
        center_layout = QVBoxLayout(center_container)
        center_layout.setAlignment(Qt.AlignCenter)

        self.period_label = QLabel("ПЕРИОД: 1")
        self.period_label.setAlignment(Qt.AlignCenter)
        self.period_label.setStyleSheet("font-size: 40px; color: #00ff00; padding: 10px;")
        center_layout.addWidget(self.period_label)
        
        # Подпись категории под периодом
        self.category_label = QLabel("")
        self.category_label.setAlignment(Qt.AlignCenter)
        self.category_label.setStyleSheet("font-size: 40px; color: #00ff00; padding: 10px;")
        center_layout.addWidget(self.category_label)

        self.time_label = QLabel("03:00")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet("font-size: 96px; font-weight: bold; color: #00ff00; padding: 20px; border: 4px solid #00ff00; border-radius: 20px;")
        center_layout.addWidget(self.time_label)
        
        # Таймер ожидания соперника
        self.opponent_wait_label = QLabel("ОЖИДАНИЕ: 00:00")
        self.opponent_wait_label.setAlignment(Qt.AlignCenter)
        self.opponent_wait_label.setStyleSheet("font-size: 32px; color: #FFA500; padding: 10px;")
        center_layout.addWidget(self.opponent_wait_label)

        main_layout.addWidget(center_container)

        # Правая половина - Синий (аналогично красному)
        blue_container = QWidget()
        blue_container.setStyleSheet("background-color: #00008B; border: 5px solid #0000ff; border-radius: 20px;")
        blue_layout = QVBoxLayout(blue_container)
        blue_layout.setContentsMargins(15, 15, 15, 15)
        blue_layout.setSpacing(10)

        self.blue_name = QLabel("СИНИЙ")
        self.blue_name.setAlignment(Qt.AlignCenter)
        self.blue_name.setWordWrap(True)
        self.blue_name.setStyleSheet("font-size: 48px; font-weight: bold; color: white; padding: 15px;")
        self.blue_name.setMinimumHeight(120)
        blue_layout.addWidget(self.blue_name, 3)

        self.blue_region = QLabel("")
        self.blue_region.setAlignment(Qt.AlignCenter)
        self.blue_region.setStyleSheet("font-size: 24px; color: white; padding: 5px;")
        blue_layout.addWidget(self.blue_region, 2)

        # Объединенный блок для синего
        blue_score_container = QWidget()
        blue_score_container.setStyleSheet("background-color: #000060; border-radius: 15px;")
        blue_score_layout = QVBoxLayout(blue_score_container)
        blue_score_layout.setContentsMargins(20, 15, 20, 15)

        self.blue_points = QLabel("0")
        self.blue_points.setAlignment(Qt.AlignCenter)
        self.blue_points.setStyleSheet("font-size: 120px; font-weight: bold; color: white; border: none;")
        blue_score_layout.addWidget(self.blue_points)

        blue_details = QHBoxLayout()
        blue_detail = QHBoxLayout()

        self.blue_cautions = QLabel("Предупреждения: 0")
        self.blue_cautions.setAlignment(Qt.AlignCenter)
        self.blue_cautions.setStyleSheet("font-size: 32px; color: #ffcc00; border: none;")
        blue_details.addWidget(self.blue_cautions)

        self.blue_passivity = QLabel("Пассивность: 0")
        self.blue_passivity.setAlignment(Qt.AlignCenter)
        self.blue_passivity.setStyleSheet("font-size: 32px; color: #ffcc00; border: none;")
        blue_detail.addWidget(self.blue_passivity)

        blue_score_layout.addLayout(blue_detail)
        blue_score_layout.addLayout(blue_details)
        blue_layout.addWidget(blue_score_container, 5)

        main_layout.addWidget(blue_container)
        QTimer.singleShot(100, self.update_font_sizes)

    def format_name(self, name: str) -> str:
        parts = name.split(" ", 1)
        if len(parts) == 2:
            return parts[0] + "\n" + parts[1]
        return name

    
    def update_display(self, red_name, red_region, red_points, red_cautions, red_passivity,
                      blue_name, blue_region, blue_points, blue_cautions, blue_passivity,
                      period, time_remaining, is_break=False, category: str = "", opponent_wait_time=0):
        # Перезагружаем настройки из файла, если файл изменился
        import os
        from core.settings import SETTINGS_FILE
        if os.path.exists(SETTINGS_FILE):
            current_mtime = os.path.getmtime(SETTINGS_FILE)
            if current_mtime != self._last_settings_mtime:
                self.settings.load_settings()
                self._last_settings_mtime = current_mtime
        # Применяем настройки видимости
        show_cautions = self.settings.get_scoreboard_setting("show_cautions")
        show_passivity = self.settings.get_scoreboard_setting("show_passivity")
        show_period = self.settings.get_scoreboard_setting("show_period")
        show_opponent_wait = self.settings.get_scoreboard_setting("show_opponent_wait_timer")
        
        # Обновляем красного борца (только если значения изменились)
        if self.red_name.text() != self.format_name(red_name):
            self.red_name.setText(self.format_name(red_name))
        if self.red_region.text() != red_region:
            self.red_region.setText(red_region)
        if self.red_points.text() != str(red_points):
            self.red_points.setText(str(red_points))
        if show_cautions:
            if self.red_cautions.text() != f"Предупреждения: {red_cautions}":
                self.red_cautions.setText(f"Предупреждения: {red_cautions}")
            self.red_cautions.setVisible(True)
        else:
            self.red_cautions.setVisible(False)
        if show_passivity:
            if self.red_passivity.text() != f"Пассивность: {red_passivity}":
                self.red_passivity.setText(f"Пассивность: {red_passivity}")
            self.red_passivity.setVisible(True)
        else:
            self.red_passivity.setVisible(False)
        
        # Обновляем синего борца (только если значения изменились)
        if self.blue_name.text() != self.format_name(blue_name):
            self.blue_name.setText(self.format_name(blue_name))
        if self.blue_region.text() != blue_region:
            self.blue_region.setText(blue_region)
        if self.blue_points.text() != str(blue_points):
            self.blue_points.setText(str(blue_points))
        if show_cautions:
            if self.blue_cautions.text() != f"Предупреждения: {blue_cautions}":
                self.blue_cautions.setText(f"Предупреждения: {blue_cautions}")
            self.blue_cautions.setVisible(True)
        else:
            self.blue_cautions.setVisible(False)
        if show_passivity:
            if self.blue_passivity.text() != f"Пассивность: {blue_passivity}":
                self.blue_passivity.setText(f"Пассивность: {blue_passivity}")
            self.blue_passivity.setVisible(True)
        else:
            self.blue_passivity.setVisible(False)
        
        # Обновляем период и время (показываем перерыв, если он идет)
        if show_period:
            if is_break:
                self.period_label.setText(f"ПЕРЕРЫВ МЕЖДУ ПЕРИОДАМИ")
                self.period_label.setStyleSheet("font-size: 36px; color: #FFA500; padding: 10px;")
                # Желтые линии во время перерыва
                self.time_label.setStyleSheet("font-size: 72px; font-weight: bold; color: #FFA500; padding: 20px; border: 3px solid #FFA500; border-radius: 15px;")
            else:
                self.period_label.setText(f"ПЕРИОД: {period}")
                self.period_label.setStyleSheet("font-size: 36px; color: #00ff00; padding: 10px;")
                # Зеленые линии во время периода
                self.time_label.setStyleSheet("font-size: 72px; font-weight: bold; color: #00ff00; padding: 20px; border: 3px solid #00ff00; border-radius: 15px;")
            self.period_label.setVisible(True)
        else:
            self.period_label.setVisible(False)
            # Если период скрыт, используем стандартный стиль времени
            self.time_label.setStyleSheet("font-size: 72px; font-weight: bold; color: #00ff00; padding: 20px; border: 3px solid #00ff00; border-radius: 15px;")
        
        # Категория под периодом
        category_text = category or ""
        if category_text:
            self.category_label.setText(str(category_text))
        else:
            self.category_label.setText("")

        minutes = time_remaining // 60
        seconds = time_remaining % 60
        self.time_label.setText(f"{minutes:02d}:{seconds:02d}")
        
        # Обновляем таймер ожидания соперника
        if show_opponent_wait and opponent_wait_time > 0:
            wait_minutes = opponent_wait_time // 60
            wait_seconds = opponent_wait_time % 60
            self.opponent_wait_label.setText(f"ОЖИДАНИЕ: {wait_minutes:02d}:{wait_seconds:02d}")
            self.opponent_wait_label.setVisible(True)
        else:
            self.opponent_wait_label.setVisible(False)
    
    def handle_scoreboard_update(self, message, client_socket=None):
        """Обрабатывает обновления от NetworkManager"""
        print(f"[ТАБЛО] Получено обновление от mat={message.get('data', {}).get('mat', 0)}")

        if not hasattr(self, 'display') or self.display is None:
            print("ОШИБКА: display не инициализирован!")
            return

        data = message.get('data', {})
        if not data:
            print("ОШИБКА: пустые данные в scoreboard_update")
            return

        # ФИЛЬТРАЦИЯ: Игнорируем обновления от mat=0 (скорее всего, это тестовые/ошибочные данные)
        mat_number = data.get('mat', 0)
        if mat_number == 0:
            print("[ТАБЛО] Игнорируем обновление от mat=0")
            return

        try:
            # Сохраняем текущие данные для обновления времени
            self.current_data = data

            # === Красный ===
            red_data = data.get('red', {})
            red_name = red_data.get('name', 'КРАСНЫЙ')
            red_region = red_data.get('region', '')
            red_points = red_data.get('points', 0)
            red_cautions = red_data.get('cautions', 0)
            red_passivity = red_data.get('passivity', 0)

            # === Синий ===
            blue_data = data.get('blue', {})
            blue_name = blue_data.get('name', 'СИНИЙ')
            blue_region = blue_data.get('region', '')
            blue_points = blue_data.get('points', 0)
            blue_cautions = blue_data.get('cautions', 0)
            blue_passivity = blue_data.get('passivity', 0)

            # === Период, категория и время ===
            period = data.get('period', 1)
            time_remaining = data.get('time_remaining', PERIOD_DURATION)
            is_break = data.get('is_break', False)
            category = data.get('category', "")

            # === ОБНОВЛЕНИЕ ДИСПЛЕЯ ===
            opponent_wait_time = data.get('opponent_wait_time', 0)
            self.display.update_display(
                red_name, red_region, red_points, red_cautions, red_passivity,
                blue_name, blue_region, blue_points, blue_cautions, blue_passivity,
                period, time_remaining, is_break, category, opponent_wait_time
            )

            print(f"[ТАБЛО] Обновлено mat={mat_number}: {red_name} {red_points} : {blue_points} {blue_name}")

        except Exception as e:
            print(f"ОШИБКА в handle_scoreboard_update: {e}")
            import traceback
            traceback.print_exc()
    
    def resizeEvent(self, event):
        """Адаптивное изменение размеров шрифтов при изменении размера окна"""
        super().resizeEvent(event)
        self.update_font_sizes()

    def update_font_sizes(self):
        """Обновление размеров шрифтов в зависимости от размера окна"""
        width = self.width()

        # Базовые размеры для ширины 1920px
        base_width = 1920
        scale_factor = width / base_width

        # Применяем масштабирование к шрифтам
        name_size = max(24, int(48 * scale_factor))
        region_size = max(20, int(24 * scale_factor))
        points_size = max(60, int(160 * scale_factor))
        details_size = max(20, int(32 * scale_factor))
        time_size = max(48, int(96 * scale_factor))
        period_size = max(24, int(40 * scale_factor))

        # Применяем стили
        self.red_name.setStyleSheet(f"font-size: {name_size}px; font-weight: bold; color: white; padding: 15px;")
        self.red_region.setStyleSheet(f"font-size: {region_size}px; font-weight: bold; color: white; padding: 5px;")
        self.red_points.setStyleSheet(f"font-size: {points_size}px; font-weight: bold; color: white; border: none;")
        self.red_cautions.setStyleSheet(f"font-size: {details_size}px; color: #ffcc00; border: none;")
        self.red_passivity.setStyleSheet(f"font-size: {details_size}px; color: #ffcc00; border: none;")

        self.blue_name.setStyleSheet(f"font-size: {name_size}px; font-weight: bold; color: white; padding: 15px;")
        self.blue_region.setStyleSheet(f"font-size: {region_size}px; font-weight: bold; color: white; padding: 5px;")
        self.blue_points.setStyleSheet(f"font-size: {points_size}px; font-weight: bold; color: white; border: none;")
        self.blue_cautions.setStyleSheet(f"font-size: {details_size}px; color: #ffcc00; border: none;")
        self.blue_passivity.setStyleSheet(f"font-size: {details_size}px; color: #ffcc00; border: none;")

        self.time_label.setStyleSheet(f"font-size: {time_size}px; font-weight: bold; color: #00ff00; padding: 20px; border: 4px solid #00ff00; border-radius: 20px;")
        self.period_label.setStyleSheet(f"font-size: {period_size}px; color: #00ff00; padding: 10px;")

class ScoreboardWindow(QMainWindow):
    closed = pyqtSignal()
    def __init__(self, network_manager=None, parent=None):
        super().__init__(parent)
        self.network_manager = network_manager

        # === 1. Окно ===
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowTitleHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setWindowTitle("ТАБЛО — ВОЛЬНАЯ БОРЬБА")
        self.setStyleSheet("QMainWindow { background-color: #ffffff; }")

        # === 2. ДИСПЛЕЙ ===
        self.display = ScoreboardDisplay(self, network_manager)
        self.setCentralWidget(self.display)

        # === 3. Панель управления ===
        self.control_panel = self.create_control_panel()
        self.control_panel.hide()

        # === 4. Таймер и мышь ===
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_controls)
        self.last_mouse_pos = None

        # === 5. Горячие клавиши ===
        QShortcut(QKeySequence("Ctrl+W"), self, self.close)
        QShortcut(QKeySequence("F11"), self, self.toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self, self.showMinimized)
        # Горячая клавиша Host + C для переключения полноэкранного режима
        QShortcut(QKeySequence("Alt+C"), self, self.toggle_fullscreen)

        # === 6. Перемещение на второй экран ===
        self.move_to_second_screen()

        
        # === 8. ТАЙМЕР ДЛЯ ПЕРИОДИЧЕСКОГО ОБНОВЛЕНИЯ ===
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.request_update)
        self.update_timer.start(1000)  # Запрос обновления каждую секунду

        # === 9. ТАЙМЕР ДЛЯ ОБНОВЛЕНИЯ ВРЕМЕНИ НА ТАБЛО ===
        self.time_update_timer = QTimer()
        self.time_update_timer.timeout.connect(self.update_time_display)
        self.time_update_timer.start(500)  # Обновление времени каждые 500 мс (уменьшена частота для устранения мерцания)
        
        self.current_data = None
        self._last_is_break = False  # Инициализация для отслеживания состояния перерыва

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def request_update(self):
        """Запрашивает обновление данных с главного ПК"""
        if self.network_manager and not self.network_manager.is_server:
            self.network_manager.send_message('request_scoreboard_update', {})
            print("[ТАБЛО] Запрос обновления отправлен")

    def update_time_display(self):
        """Обновляет отображение времени на табло"""
        if hasattr(self, 'current_data') and self.current_data:
            # Обновляем время на табло
            period = self.current_data.get('period', 1)
            time_remaining = self.current_data.get('time_remaining', PERIOD_DURATION)
            is_break = self.current_data.get('is_break', False)
            
            if hasattr(self, 'display') and self.display:
                # Обновляем только время, не трогая текст периода и стили
                minutes = time_remaining // 60
                seconds = time_remaining % 60
                new_time_text = f"{minutes:02d}:{seconds:02d}"
                # Обновляем только если время изменилось
                if self.display.time_label.text() != new_time_text:
                    self.display.time_label.setText(new_time_text)
                
                # Обновляем цвет границ во время перерыва (только если изменилось состояние)
                current_is_break = hasattr(self, '_last_is_break') and self._last_is_break
                if current_is_break != is_break:
                    self._last_is_break = is_break
                    if is_break:
                        self.display.time_label.setStyleSheet("font-size: 72px; font-weight: bold; color: #FFA500; padding: 20px; border: 3px solid #FFA500; border-radius: 15px;")
                    else:
                        self.display.time_label.setStyleSheet("font-size: 72px; font-weight: bold; color: #00ff00; padding: 20px; border: 3px solid #00ff00; border-radius: 15px;")

    def handle_scoreboard_update(self, message, client_socket=None):
        """Обрабатывает обновления от NetworkManager"""
        print(f"[ТАБЛО] Получено обновление: {message}")
        
        if not hasattr(self, 'display') or self.display is None:
            print("ОШИБКА: display не инициализирован!")
            return

        data = message.get('data', {})
        if not data:
            print("ОШИБКА: пустые данные в scoreboard_update")
            return

        try:
            # Сохраняем текущие данные для обновления времени
            self.current_data = data
            
            # === Красный ===
            red_data = data.get('red', {})
            red_name = red_data.get('name', 'КРАСНЫЙ')
            red_region = red_data.get('region', '')
            red_points = red_data.get('points', 0)
            red_cautions = red_data.get('cautions', 0)
            red_passivity = red_data.get('passivity', 0)

            # === Синий ===
            blue_data = data.get('blue', {})
            blue_name = blue_data.get('name', 'СИНИЙ')
            blue_region = blue_data.get('region', '')
            blue_points = blue_data.get('points', 0)
            blue_cautions = blue_data.get('cautions', 0)
            blue_passivity = blue_data.get('passivity', 0)

            # === Период, категория и время ===
            period = data.get('period', 1)
            time_remaining = data.get('time_remaining', PERIOD_DURATION)
            is_break = data.get('is_break', False)
            category = data.get('category', "")

            # === ОБНОВЛЕНИЕ ДИСПЛЕЯ ===
            opponent_wait_time = data.get('opponent_wait_time', 0)
            self.display.update_display(
                red_name, red_region, red_points, red_cautions, red_passivity,
                blue_name, blue_region, blue_points, blue_cautions, blue_passivity,
                period, time_remaining, is_break, category, opponent_wait_time
            )

            print(f"[ТАБЛО] Обновлено: {red_name} {red_points} : {blue_points} {blue_name}")

        except Exception as e:
            print(f"ОШИБКА в handle_scoreboard_update: {e}")
            import traceback
            traceback.print_exc()
        
    def showEvent(self, event):
        """Вызывается при показе окна"""
        super().showEvent(event)
        # Обновляем шрифты после показа окна
        QTimer.singleShot(100, self.display.update_font_sizes)

    def create_control_panel(self):
        """Создаёт панель с кнопками управления"""
        panel = QWidget(self)
        panel.setStyleSheet("""
            background-color: rgba(0, 0, 0, 180);
            border-radius: 15px;
            padding: 8px;
        """)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        # Кнопка: Свернуть
        minimize_btn = QPushButton("−")
        minimize_btn.setFixedSize(40, 40)
        minimize_btn.setStyleSheet("""
            QPushButton {
                background-color: #444444; color: white; 
                border-radius: 20px; font-weight: bold; font-size: 18px;
            }
            QPushButton:hover { background-color: #666666; }
        """)
        minimize_btn.clicked.connect(self.showMinimized)
        layout.addWidget(minimize_btn)

        # Кнопка: Полный экран / Окно
        self.fullscreen_btn = QPushButton("⛶")
        self.fullscreen_btn.setFixedSize(40, 40)
        self.fullscreen_btn.setStyleSheet("""
            QPushButton {
                background-color: #444444; color: white; 
                border-radius: 20px; font-weight: bold; font-size: 16px;
            }
            QPushButton:hover { background-color: #666666; }
        """)
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        layout.addWidget(self.fullscreen_btn)

        # Кнопка: Закрыть
        close_btn = QPushButton("×")
        close_btn.setFixedSize(40, 40)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #c62828; color: white; 
                border-radius: 20px; font-weight: bold; font-size: 20px;
            }
            QPushButton:hover { background-color: #e53935; }
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        # Позиционирование в правом верхнем углу
        panel.setGeometry(20, 20, 180, 60)
        return panel

    def toggle_fullscreen(self):
        """Переключает полноэкранный режим на втором экране"""
        screens = QApplication.screens()
        if self.isFullScreen():
            # Выходим из полноэкранного режима
            self.showNormal()
            # Убеждаемся, что окно остается на втором экране
            if len(screens) > 1:
                screen = screens[1]
                self.move(screen.geometry().left(), screen.geometry().top())
            if hasattr(self, 'fullscreen_btn'):
                self.fullscreen_btn.setText("⛶")
        else:
            # Включаем полноэкранный режим на втором экране
            if len(screens) > 1:
                screen = screens[1]
                # Перемещаем окно на второй экран перед включением полноэкранного режима
                self.move(screen.geometry().left(), screen.geometry().top())
                self.setGeometry(screen.geometry())
            self.showFullScreen()
            if hasattr(self, 'fullscreen_btn'):
                self.fullscreen_btn.setText("⛶")

    def keyPressEvent(self, event: QKeyEvent):
        """Обработка нажатий клавиш, включая Host + C"""
        # Обработка комбинации Host + C (Windows Key + C)
        # В Qt это MetaModifier + Key_C
        if (event.modifiers() & Qt.MetaModifier) and event.key() == Qt.Key_C:
            self.toggle_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)
    def mouseMoveEvent(self, event):
        current_pos = event.pos()
        if self.last_mouse_pos is None or current_pos != self.last_mouse_pos:  # ← ПРОВЕРКА
            ...
        self.last_mouse_pos = current_pos  # ← ОБНОВЛЕНИЕ

    def leaveEvent(self, event):
        """Скрываем при выходе курсора (если не на панели)"""
        self.hide_timer.start(1000)
        super().leaveEvent(event)

    def show_controls(self):
        """Показать панель с анимацией"""
        self.control_panel.show()
        self.hide_timer.stop()

        # Плавное появление
        self.anim = QPropertyAnimation(self.control_panel, b"windowOpacity")
        self.anim.setDuration(300)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()

    def hide_controls(self):
        """Скрыть панель с анимацией"""
        anim = QPropertyAnimation(self.control_panel, b"windowOpacity")
        anim.setDuration(300)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self.control_panel.hide)
        anim.start()

    def move_to_second_screen(self):
        """Открывает на втором экране, полноэкранно"""
        screens = QApplication.screens()
        if len(screens) > 1:
            screen = screens[1]
            self.move(screen.geometry().left(), screen.geometry().top())
            self.showFullScreen()
        else:
            # Если только один экран, открываем максимизированным
            self.showMaximized()

        # Убедимся, что окно остается поверх других
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.show()
        # Убираем поверх всех после показа, чтобы можно было переключаться
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()

    def handle_update(self, message, client_socket=None):
        """Обрабатывает обновления от NetworkManager"""
        if not hasattr(self, 'display') or self.display is None:
            print("ОШИБКА: display не инициализирован!")
            return

        data = message.get('data', {})
        if not data:
            print("ОШИБКА: пустые данные в scoreboard_update")
            return

        try:
            # === Красный ===
            red_data = data.get('red', {})
            red_name = red_data.get('name', 'КРАСНЫЙ')
            red_region = red_data.get('region', '')
            red_points = red_data.get('points', 0)
            red_cautions = red_data.get('cautions', 0)
            red_passivity = red_data.get('passivity', 0)

            # === Синий ===
            blue_data = data.get('blue', {})
            blue_name = blue_data.get('name', 'СИНИЙ')
            blue_region = blue_data.get('region', '')
            blue_points = blue_data.get('points', 0)
            blue_cautions = blue_data.get('cautions', 0)
            blue_passivity = blue_data.get('passivity', 0)

            # === Период, категория и время ===
            period = data.get('period', 1)
            time_remaining = data.get('time_remaining', 180)
            category = data.get('category', "")

            # === ОБНОВЛЕНИЕ ДИСПЛЕЯ ===
            opponent_wait_time = data.get('opponent_wait_time', 0)
            self.display.update_display(
                red_name, red_region, red_points, red_cautions, red_passivity,
                blue_name, blue_region, blue_points, blue_cautions, blue_passivity,
                period, time_remaining, False, category, opponent_wait_time
            )

            print(f"[ТАБЛО] Обновлено: {red_name} {red_points} : {blue_points} {blue_name} | Период: {period} | Время: {time_remaining}")

        except Exception as e:
            print(f"ОШИБКА в handle_update: {e}")
            import traceback
            traceback.print_exc()