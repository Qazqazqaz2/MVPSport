import json
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, 
                             QPushButton, QGroupBox, QTextEdit, QLabel, QMessageBox, QInputDialog, QHBoxLayout)
from PyQt5.QtCore import QTimer
from core.network import NetworkManager
from ui.widgets.scoreboard import ScoreboardDisplay, ScoreboardWindow
from ui.widgets.control_panel import ControlPanel
from ui.widgets.tournament_manager import TournamentManager
from ui.widgets.excel_importer import ExcelImporter
from ui.widgets.schedule import ScheduleWindow, MatScheduleWindow, ScheduleMainWindow
from ui.widgets.secretary import SecretaryWindow, CategoriesManagerTab
from ui.widgets.settings_window import SettingsWindow
from core.utils import get_local_ip
from core.settings import get_settings
from network.schedule_sync import ScheduleSyncService

class EnhancedControlPanel(QMainWindow):
    def __init__(self, is_secondary=False, server_host=None):
        super().__init__()
        self.tournament_data = None
        self.tab_widget = None
        self.control_panel_instance = None
        self.scoreboard_instance = None
        self.external_scoreboard = None
        self.is_secondary = is_secondary
        self.network_manager = NetworkManager()
        self.network_manager.register_handler('tournament_update', self.handle_tournament_update)
        self.settings = get_settings()
        self.schedule_sync_service = ScheduleSyncService(
            on_schedule_received=self._on_schedule_from_sync,
            on_log=lambda msg: print(msg)
        )
        self._auto_start_schedule_sync()
        
        # Настройка сетевого взаимодействия
        if is_secondary:
            if server_host and self.network_manager.connect_to_server(server_host):
                print(f"Успешно подключено к серверу {server_host}")
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось подключиться к серверу")
        else:
            if self.network_manager.start_server():
                print("Сервер запущен")
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось запустить сервер")
        
        self.setup_ui()

    def _auto_start_schedule_sync(self):
        """Автозапуск модуля синхронизации расписаний согласно настройкам."""
        net_role_default = "node" if self.is_secondary else "coordinator"
        net_role = self.settings.get("network", "role", net_role_default)
        mat_number = self.settings.get("network", "mat_number", 1)
        allow_relay = self.settings.get("network", "allow_relay", True)
        coordinator_host = self.settings.get("network", "coordinator_host", "")
        device_name = self.settings.get("network", "device_name", "Устройство")
        auto_start = self.settings.get("network", "auto_start", True)

        if auto_start:
            self.schedule_sync_service.start(
                role=net_role,
                mat_number=mat_number,
                allow_relay=allow_relay,
                coordinator_host=coordinator_host,
                device_name=device_name,
            )

    def setup_ui(self):
        title = "Второстепенный ПК - Управление схваткой" if self.is_secondary else "Основной ПК - Управление турниром"
        self.setWindowTitle(title)
        
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        
        if self.is_secondary:
            self.setGeometry(100, 100, 1000, 700)
        else:
            self.setGeometry(100, 100, min(1200, screen_geometry.width() - 100), min(800, screen_geometry.height() - 100))
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        
        layout.addWidget(self.tab_widget)
        
        self.create_main_tab()

    def find_control_panel_by_mat(self, mat_number):
        """Находит панель управления по номеру ковра"""
        # Ищем среди открытых вкладок
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            # Проверяем по типу и атрибуту mat_number
            if hasattr(widget, 'mat_number') and widget.mat_number == mat_number:
                return widget
            # Альтернативная проверка по заголовку вкладки
            elif self.tab_widget.tabText(i) == f"Управление — Ковёр {mat_number}":
                return widget
        
        # Если не нашли, ищем среди дочерних виджетов
        for widget in self.findChildren(QWidget):
            if hasattr(widget, 'mat_number') and widget.mat_number == mat_number:
                return widget
        
        return None
    
    def open_external_scoreboard(self):
        """Открывает внешнее табло (для вызова из других мест)"""
        control_panel = self.find_control_panel_tab()
        if control_panel:
            control_panel.open_external_scoreboard()

    def handle_tournament_update(self, message, client_socket):
        """Получение обновлённых данных турнира от секретаря"""
        new_data = message['data']
        self.tournament_data = new_data
        self.update_status()
        self.update_schedule_tab()
        # Обновляем открытые MatScheduleWindow
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, MatScheduleWindow):
                widget.update_data(new_data)

        # Рассылаем расписание через модуль синхронизации (если мы координатор)
        self._push_schedule_to_sync()

    def _on_schedule_from_sync(self, schedule, sender_ip=None):
        """Применение расписания, полученного через модуль синхронизации."""
        if not schedule:
            return
        if self.tournament_data is None:
            self.tournament_data = {}
        self.tournament_data['schedule'] = schedule
        self.update_schedule_tab()
        print(f"[sync] Расписание обновлено из {sender_ip}")

    def create_main_tab(self):
        """Создает главную вкладку с кнопками управления"""
        main_tab = QWidget()
        layout = QVBoxLayout(main_tab)
        
        # Заголовок с указанием режима
        if self.is_secondary:
            title_text = "ВТОРОЙ ПК - УПРАВЛЕНИЕ СХВАТКОЙ"
            title_color = "#FFA500"
        else:
            title_text = "ОСНОВНОЙ ПК - УПРАВЛЕНИЕ ТУРНИРОМ"
            title_color = "#00FF00"
        
        title = QLabel(title_text)
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; margin: 10px; padding: 10px; text-align: center; background-color: {title_color}; color: black;")
        layout.addWidget(title)
        
        buttons_layout = QHBoxLayout()
        
        if self.is_secondary:
            buttons = [
                ("Панель управления\nсхваткой", self.open_control_panel_tab),
                ("Табло\nсхватки", self.open_scoreboard_tab),
                ("Расписание\nна ковре", self.open_mat_schedule_tab)  # Добавляем кнопку для второго ПК
            ]
        else:
            buttons = [
                ("Импорт данных\nиз Excel", self.open_importer_tab),
                ("Секретариат", self.open_secretary_window),
                ("Настройки", self.open_settings_window),
                ("Панель управления\nсхваткой", self.open_control_panel_tab),
                ("Табло\nсхватки", self.open_scoreboard_tab),
                ("Расписание\nтурнира", self.open_schedule_tab),
                ("Расписание\nна ковре", self.open_mat_schedule_tab)
            ]
        
        for text, slot in buttons:
            btn = QPushButton(text)
            btn.setStyleSheet("font-size: 14px; padding: 15px; min-height: 80px;")
            btn.clicked.connect(slot)
            buttons_layout.addWidget(btn)
        
        layout.addLayout(buttons_layout)
        
        # Статус турнира (только для основного ПК)
        if not self.is_secondary:
            status_group = QGroupBox("Текущий статус турнира")
            status_layout = QVBoxLayout(status_group)
            
            self.status_text = QTextEdit()
            self.status_text.setReadOnly(True)
            self.update_status()
            status_layout.addWidget(self.status_text)
            
            layout.addWidget(status_group)
        
        # Сетевой статус
        network_group = QGroupBox("Сетевой статус")
        network_layout = QVBoxLayout(network_group)
        
        if self.is_secondary:
            status_text = "Режим: КЛИЕНТ (Управление схваткой)"
        else:
            status_text = "Режим: СЕРВЕР (Управление турниром)"
        
        network_status = QLabel(status_text)
        network_status.setStyleSheet("font-weight: bold; padding: 5px;")
        network_layout.addWidget(network_status)
        
        layout.addWidget(network_group)
        
        self.tab_widget.addTab(main_tab, "Главная")
        self.tab_widget.setCurrentIndex(0)
    
    def open_secretary_window(self):
        """Открывает окно секретаря только на основном ПК"""
        if self.is_secondary:
            QMessageBox.warning(self, "Доступ запрещён", "Редактирование доступно только главному секретарю")
            return
        if not self.tournament_data:
            QMessageBox.warning(self, "Внимание", "Сначала загрузите турнир через импорт")
            return
        # Проверяем, не открыто ли уже
        for window in QApplication.topLevelWidgets():
            if isinstance(window, SecretaryWindow):
                window.activateWindow()
                return
        secretary = SecretaryWindow(self.tournament_data, self.network_manager, self.schedule_sync_service, self)
        secretary.show()
    
    def open_settings_window(self):
        """Открывает окно настроек"""
        settings_window = SettingsWindow(self)
        settings_window.exec_()

    def open_mat_schedule_tab(self):
        """Открывает вкладку с расписанием на ковре"""
        if not self.tournament_data:
            QMessageBox.warning(self, "Внимание", "Сначала загрузите турнир")
            return
            
        if not self.tab_exists("Расписание на ковре"):
            mat_schedule = MatScheduleWindow(self.tournament_data, self, self.network_manager)
            mat_schedule.match_selected.connect(self.start_match_from_schedule)
            self.tab_widget.addTab(mat_schedule, "Расписание на ковре")
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)
        else:
            # Если вкладка уже открыта, переключаемся на нее
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) == "Расписание на ковре":
                    self.tab_widget.setCurrentIndex(i)
                    break
    
    def start_match_from_schedule(self, match_data):
        """Запускает схватку из расписания на ковре"""
        # Находим или создаем панель управления
        control_panel = self.find_control_panel_tab()
        if not control_panel:
            self.open_control_panel_tab()
            control_panel = self.find_control_panel_tab()
        
        if control_panel:
            # Устанавливаем данных борцов в панель управления
            control_panel.set_match_competitors(match_data['wrestler1'], match_data['wrestler2'])
            
            # Переключаемся на вкладку управления
            self.activate_control_panel_tab()
            
            # Показываем информационное сообщение
            QMessageBox.information(self, "Данные переданы", 
                                  f"Данные борцов установлены в панель управления:\n"
                                  f"Красный: {match_data['wrestler1']['name']}\n"
                                  f"Синий: {match_data['wrestler2']['name']}\n"
                                  f"Категория: {match_data['category']}")
    
    def activate_control_panel_tab(self):
        """Активирует вкладку управления схваткой"""
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Управление схваткой":
                self.tab_widget.setCurrentIndex(i)
                break
    
    def open_importer_tab(self):
        if not self.is_secondary and not self.tab_exists("Импорт данных"):
            importer = ExcelImporter(self, self.network_manager)
            self.tab_widget.addTab(importer, "Импорт данных")
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)

    def open_control_panel_tab(self, mat_number=None):
        """Открывает панель управления для конкретного ковра"""
        if mat_number is None:
            # Диалог выбора ковра
            items = ["Ковёр 1", "Ковёр 2", "Ковёр 3", "Ковёр 4"]
            item, ok = QInputDialog.getItem(self, "Выбор ковра", "Выберите ковёр:", items, 0, False)
            if not ok:
                return
            mat_number = int(item.split()[-1])  # "Ковёр 1" → 1
        else:
            mat_number = int(mat_number)

        tab_title = f"Управление — Ковёр {mat_number}"

        # Проверяем, есть ли уже вкладка
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == tab_title:
                self.tab_widget.setCurrentIndex(i)
                return

        # Создаём новую панель - передаем is_secondary
        control = ControlPanel(
            self.tournament_data,
            self.network_manager,
            mat_number,
            self,
            self.is_secondary,
            schedule_sync=self.schedule_sync_service,
        )
        self.tab_widget.addTab(control, tab_title)
        self.tab_widget.setCurrentWidget(control)

        # Автооткрытие табло
        QTimer.singleShot(300, self.open_external_scoreboard)

    def find_control_panel_tab(self):
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, ControlPanel):
                return widget
        return None

    def activate_control_panel_tab(self):
        """Активирует вкладку управления схваткой"""
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Управление схваткой":
                self.tab_widget.setCurrentIndex(i)
                break

    def open_scoreboard_tab(self):
        if not self.tab_exists("Табло"):
            self.scoreboard_instance = ScoreboardDisplay(self, self.network_manager)
            self.tab_widget.addTab(self.scoreboard_instance, "Табло")
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)

    def find_scoreboard_tab(self):
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, ScoreboardDisplay):
                return widget
        return None

    def open_schedule_tab(self):
        """Открывает расписание турнира в отдельном окне"""
        if not self.is_secondary and self.tournament_data:
            if getattr(self, "_schedule_window", None) and self._schedule_window.isVisible():
                self._schedule_window.activateWindow()
                self._schedule_window.raise_()
                return

            # Создаем новое окно расписания
            self._schedule_window = ScheduleMainWindow(self.tournament_data, self, self.network_manager)
            self._schedule_window.closed.connect(self.on_schedule_window_closed)
            self._schedule_window.show()
        elif not self.tournament_data:
            QMessageBox.warning(self, "Внимание", "Сначала загрузите турнир")
    
    def on_schedule_window_closed(self):
        """Обработчик закрытия окна расписания"""
        self._schedule_window = None

    def open_tournament_manager_tab(self):
        if not self.is_secondary and not self.tab_exists("Менеджер турнира"):
            tournament_manager = TournamentManager(self, self.network_manager)
            self.tab_widget.addTab(tournament_manager, "Менеджер турнира")
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)

    def tab_exists(self, tab_name):
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == tab_name:
                self.tab_widget.setCurrentIndex(i)
                return True
        return False

    def close_tab(self, index):
        if self.tab_widget.tabText(index) != "Главная":
            self.tab_widget.removeTab(index)

    def set_tournament_data(self, data):
        # Сохраняем данные турнира (без автоматического подмешивания других турниров из БД)
        self.tournament_data = data
        self.update_status()
        # Инициализируем статусы матчей если их нет
        if 'schedule' in self.tournament_data:
            for match in self.tournament_data['schedule']:
                if 'status' not in match:
                    match['status'] = 'Ожидание'
        self._push_schedule_to_sync()

    def update_status(self):
        if self.tournament_data:
            info = f"Турнир: {self.tournament_data['name']}\nДата: {self.tournament_data['date']}\nМесто: {self.tournament_data['location']}\nКатегорий: {len(self.tournament_data['categories'])}\nУчастников: {len(self.tournament_data['participants'])}"
            self.status_text.setPlainText(info)
        else:
            self.status_text.setPlainText("Турнир не начат. Используйте импорт данных для начала работы.")

    def update_schedule_tab(self):
        """Обновляет окно расписания если оно открыто"""
        # Обновляем отдельное окно расписания, если оно открыто
        for window in QApplication.topLevelWidgets():
            if isinstance(window, ScheduleMainWindow):
                window.update_data(self.tournament_data)
        
        # Обновляем вкладки расписания на ковре
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, MatScheduleWindow):
                widget.update_data(self.tournament_data)

    def closeEvent(self, event):
        """Обработчик закрытия приложения"""
        if hasattr(self, 'tournament_data') and self.tournament_data:
            self.save_tournament_data()
        
        if hasattr(self, 'network_manager'):
            self.network_manager.stop()

        if hasattr(self, 'schedule_sync_service'):
            self.schedule_sync_service.stop()
        
        event.accept()

    def _push_schedule_to_sync(self):
        """Рассылает текущее расписание через модуль синхронизации (если мы координатор)."""
        if self.schedule_sync_service and self.tournament_data:
            if self.schedule_sync_service.role == "coordinator":
                self.schedule_sync_service.push_schedule(self.tournament_data)

    def save_tournament_data(self):
        try:
            if hasattr(self, 'tournament_data') and self.tournament_data:
                filename = f"autosave_{self.tournament_data.get('name', 'tournament')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(self.tournament_data, f, ensure_ascii=False, indent=2)
                print(f"Турнир автоматически сохранен в {filename}")
        except Exception as e:
            print(f"Ошибка при автосохранении: {e}")
    
    def find_control_panel_by_mat(self, mat_number):
        """Находит панель управления по номеру ковра"""
        # Ищем среди открытых вкладок
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            # Проверяем по типу и атрибуту mat_number
            if hasattr(widget, 'mat_number') and widget.mat_number == mat_number:
                return widget
            # Альтернативная проверка по заголовку вкладки
            elif self.tab_widget.tabText(i) == f"Управление — Ковёр {mat_number}":
                return widget
            # Дополнительная проверка для старых версий
            elif isinstance(widget, ControlPanel):
                if hasattr(widget, 'mat_number'):
                    if widget.mat_number == mat_number:
                        return widget

        # Если не нашли, ищем среди всех виджетов
        for widget in QApplication.allWidgets():
            if hasattr(widget, 'mat_number') and widget.mat_number == mat_number:
                return widget

        return None