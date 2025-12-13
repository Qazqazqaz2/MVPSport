import json
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, 
                             QPushButton, QGroupBox, QTextEdit, QLabel, QMessageBox, QInputDialog, QHBoxLayout)
from PyQt5.QtCore import QTimer, pyqtSignal, QMetaObject, Qt
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
from core.logger import get_logger

class EnhancedControlPanel(QMainWindow):
    # Сигналы для безопасного обновления UI из потоков
    schedule_update_signal = pyqtSignal(list, str)  # schedule, sender_ip
    match_update_signal = pyqtSignal(dict, str)  # match_data, sender_ip
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
        # Подключаем сигналы для безопасного обновления UI из потока
        self.schedule_update_signal.connect(self._on_schedule_from_sync_safe)
        self.match_update_signal.connect(self._on_match_update_safe)
        
        # Инициализируем логирование
        logger = get_logger()
        if logger:
            # Обновляем параметры логгера на основе настроек
            device_name = self.settings.get("network", "device_name", "Устройство")
            coordinator_host = self.settings.get("network", "coordinator_host", "")
            net_role_default = "node" if self.is_secondary else "coordinator"
            net_role = self.settings.get("network", "role", net_role_default)
            logger.role = net_role
            logger.coordinator_host = coordinator_host if coordinator_host else None
        
        # Создаем schedule_sync_service БЕЗ обработчика логов сначала
        # Обработчик будет установлен после полной инициализации
        self.schedule_sync_service = ScheduleSyncService(
            on_schedule_received=self._on_schedule_from_sync_thread_safe,
            on_log=lambda msg: print(msg),
            on_log_received=None,  # Установим позже
            on_match_update=self._on_match_update_thread_safe
        )
        
        # Устанавливаем обработчик получения логов только для coordinator
        # Обработчик отправки логов установим ПОСЛЕ запуска schedule_sync_service
        if logger and logger.role == "coordinator":
            self.schedule_sync_service.on_log_received = self._on_log_received
        
        self._auto_start_schedule_sync()
        
        # Устанавливаем функцию отправки логов ПОСЛЕ запуска schedule_sync_service
        # Это важно для node устройств, чтобы избежать ошибок сегментации
        if logger and logger.role != "coordinator":
            logger.on_log_send = self._send_log_to_coordinator
        
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
            try:
                self.schedule_sync_service.start(
                    role=net_role,
                    mat_number=mat_number,
                    allow_relay=allow_relay,
                    coordinator_host=coordinator_host,
                    device_name=device_name,
                )
                # После успешного запуска обновляем логгер и устанавливаем обработчик отправки логов
                logger = get_logger()
                if logger and logger.role != "coordinator":
                    logger.on_log_send = self._send_log_to_coordinator
            except Exception as e:
                # Логируем ошибку, но не используем logger, чтобы избежать рекурсии
                print(f"Ошибка при запуске schedule_sync_service: {e}")
                import traceback
                traceback.print_exc()

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
        
        # Обновляем расписания в панелях управления
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, ControlPanel) and hasattr(widget, 'refresh_inline_schedule'):
                widget.refresh_inline_schedule()

        # НЕ рассылаем расписание обратно, если оно пришло из сети
        # Это предотвращает бесконечный цикл синхронизации
        # Coordinator должен отправлять расписание только когда он сам его создал/изменил

    def _on_schedule_from_sync_thread_safe(self, schedule, sender_ip=None):
        """Безопасный вызов из потока - эмитирует сигнал."""
        self.schedule_update_signal.emit(schedule, sender_ip or "")
    
    def _on_match_update_thread_safe(self, match_data, sender_ip=None):
        """Безопасный вызов из потока - эмитирует сигнал."""
        self.match_update_signal.emit(match_data, sender_ip or "")
    
    def _on_schedule_from_sync_safe(self, schedule, sender_ip=None):
        """Применение расписания, полученного через модуль синхронизации (вызывается из главного потока)."""
        if not schedule:
            return
        
        # Отладочная информация о входящем расписании
        mats_in_incoming = {}
        for item in schedule:
            mat = item.get("mat")
            mats_in_incoming[mat] = mats_in_incoming.get(mat, 0) + 1
        print(f"[DEBUG sync] Входящее расписание от {sender_ip}: {len(schedule)} записей, ковры: {mats_in_incoming}")
        
        if self.tournament_data is None:
            self.tournament_data = {}
        
        existing_schedule = self.tournament_data.get('schedule', [])
        if existing_schedule:
            mats_in_existing = {}
            for item in existing_schedule:
                mat = item.get("mat")
                mats_in_existing[mat] = mats_in_existing.get(mat, 0) + 1
            print(f"[DEBUG sync] Существующее расписание: {len(existing_schedule)} записей, ковры: {mats_in_existing}")
        
        self.tournament_data['schedule'] = self._merge_schedule(
            existing_schedule,
            schedule
        )
        
        # Обновляем результаты матчей в категориях на основе обновленного расписания
        updated_categories = self._update_category_matches_from_schedule(schedule)
        
        # Отладочная информация о результате слияния
        merged_schedule = self.tournament_data['schedule']
        mats_in_merged = {}
        for item in merged_schedule:
            mat = item.get("mat")
            mats_in_merged[mat] = mats_in_merged.get(mat, 0) + 1
        print(f"[DEBUG sync] После слияния: {len(merged_schedule)} записей, ковры: {mats_in_merged}")
        
        # Используем QTimer.singleShot для гарантии выполнения в главном потоке
        QTimer.singleShot(0, self.update_schedule_tab)
        
        # Обновляем открытые сетки для обновленных категорий
        if updated_categories:
            QTimer.singleShot(0, lambda: self._update_brackets_for_categories(updated_categories))
        
        print(f"[sync] Расписание обновлено из {sender_ip} ({len(schedule)} записей, всего: {len(merged_schedule)})")
    
    def _update_brackets_for_categories(self, categories):
        """Обновляет открытые сетки для указанных категорий."""
        from ui.widgets.tournament_manager import BracketWindow
        for widget in QApplication.allWidgets():
            if isinstance(widget, BracketWindow):
                if hasattr(widget, 'current_category') and widget.current_category in categories:
                    widget.update_bracket(widget.current_category)
    
    def _update_category_matches_from_schedule(self, schedule):
        """Обновляет результаты матчей в категориях на основе данных из расписания."""
        if not self.tournament_data or not schedule:
            return set()
        
        categories = self.tournament_data.get('categories', {})
        updated_count = 0
        updated_categories = set()
        
        for s_match in schedule:
            match_id = s_match.get('match_id')
            if not match_id:
                continue
            
            # Ищем матч в категориях по match_id
            for cat_name, cat_data in categories.items():
                matches = cat_data.get('matches', [])
                for match in matches:
                    if match.get('id') == match_id:
                        # Обновляем результаты матча из расписания
                        updated = False
                        if 'winner' in s_match and match.get('winner') != s_match['winner']:
                            match['winner'] = s_match['winner']
                            updated = True
                        if 'score1' in s_match and match.get('score1') != s_match['score1']:
                            match['score1'] = s_match['score1']
                            updated = True
                        if 'score2' in s_match and match.get('score2') != s_match['score2']:
                            match['score2'] = s_match['score2']
                            updated = True
                        if 'completed' in s_match:
                            if match.get('completed') != s_match['completed']:
                                match['completed'] = s_match['completed']
                                updated = True
                        elif s_match.get('status') == 'Завершен':
                            if not match.get('completed'):
                                match['completed'] = True
                                updated = True
                        
                        if updated:
                            updated_count += 1
                            updated_categories.add(cat_name)
                        break
        
        if updated_count > 0:
            print(f"[SYNC] Обновлено {updated_count} матчей в категориях на основе расписания: {updated_categories}")
        
        return updated_categories
    
    def _on_match_update_safe(self, match_data, sender_ip=None):
        """Обработка обновления одного матча в реальном времени (вызывается из главного потока)."""
        if not match_data or not self.tournament_data:
            return
        
        match_id = match_data.get('match_id')
        if not match_id:
            return
        
        print(f"[SYNC] Получено обновление матча {match_id} от {sender_ip}")
        
        # Обновляем матч в расписании
        schedule = self.tournament_data.get('schedule', [])
        updated_in_schedule = False
        for s_match in schedule:
            if s_match.get('match_id') == match_id:
                # Обновляем все поля из входящего матча
                s_match.update(match_data)
                updated_in_schedule = True
                break
        
        # Если матча нет в расписании, добавляем его
        if not updated_in_schedule:
            schedule.append(match_data)
            self.tournament_data['schedule'] = schedule
        
        # Обновляем матч в категориях
        updated_categories = self._update_category_match_from_data(match_id, match_data)
        
        # Обновляем UI
        QTimer.singleShot(0, self.update_schedule_tab)
        
        # Обновляем открытые сетки для обновленных категорий
        if updated_categories:
            QTimer.singleShot(0, lambda: self._update_brackets_for_categories(updated_categories))
        
        print(f"[SYNC] Матч {match_id} обновлен в реальном времени")
    
    def _update_category_match_from_data(self, match_id, match_data):
        """Обновляет один матч в категориях на основе данных."""
        if not self.tournament_data:
            return set()
        
        categories = self.tournament_data.get('categories', {})
        updated_categories = set()
        
        # Ищем матч в категориях по match_id
        for cat_name, cat_data in categories.items():
            matches = cat_data.get('matches', [])
            for match in matches:
                if match.get('id') == match_id:
                    # Обновляем результаты матча
                    updated = False
                    for key in ['winner', 'score1', 'score2', 'completed', 'status', 'completed_at']:
                        if key in match_data and match.get(key) != match_data[key]:
                            match[key] = match_data[key]
                            updated = True
                    
                    if updated:
                        updated_categories.add(cat_name)
                    break
        
        return updated_categories

    @staticmethod
    def _merge_schedule(existing_schedule, incoming_schedule):
        """Объединяет расписания, не теряя матчи с других ковров. Приоритет у входящих данных для результатов."""
        if not existing_schedule:
            return list(incoming_schedule or [])
        if not incoming_schedule:
            return list(existing_schedule or [])

        def make_key(m):
            match_id = m.get('match_id')
            if match_id:
                return ('id', match_id)
            return (
                'tuple',
                m.get('category', ''),
                m.get('wrestler1', ''),
                m.get('wrestler2', ''),
                m.get('mat', 0),
                m.get('time', ''),
                m.get('round', 0),
            )

        merged = {}
        # Сначала добавляем существующие матчи
        for m in existing_schedule:
            merged[make_key(m)] = m.copy()  # Копируем, чтобы не изменять оригинал
        
        # Затем обновляем/добавляем входящие матчи (приоритет у входящих данных)
        for m in incoming_schedule:
            key = make_key(m)
            if key in merged:
                # Объединяем данные: входящие данные имеют приоритет, но сохраняем все поля
                existing = merged[key]
                # Обновляем все поля из входящего матча
                existing.update(m)
            else:
                # Новый матч
                merged[key] = m.copy()

        result = list(merged.values())
        result.sort(key=lambda x: (
            x.get('time', ''),
            x.get('mat', 0),
            x.get('round', 0),
            x.get('match_id', '')
        ))
        return result

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
        # Проверяем tournament_data более тщательно - может быть пустым словарем после импорта
        if not self.tournament_data or not isinstance(self.tournament_data, dict) or not self.tournament_data.get('categories'):
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

    def open_mat_schedule_tab(self, mat_number=None):
        """Открывает вкладку с расписанием на ковре"""
        if not self.tournament_data:
            QMessageBox.warning(self, "Внимание", "Сначала загрузите турнир")
            return
        
        # Если mat_number не указан, берем из настроек устройства
        if mat_number is None:
            mat_number = self.settings.get("network", "mat_number", 1)
            
        if not self.tab_exists("Расписание на ковре"):
            mat_schedule = MatScheduleWindow(self.tournament_data, self, self.network_manager, default_mat=mat_number)
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
        """Обновляет окно расписания если оно открыто (вызывается из главного потока)"""
        if not self.tournament_data:
            return
        
        try:
            # Обновляем отдельное окно расписания, если оно открыто
            # Используем список, чтобы избежать проблем при изменении списка виджетов
            try:
                top_level_widgets = list(QApplication.topLevelWidgets())
                for window in top_level_widgets:
                    try:
                        if isinstance(window, ScheduleMainWindow) and window.isVisible():
                            window.update_data(self.tournament_data)
                    except (RuntimeError, AttributeError) as e:
                        # Виджет может быть удален или находиться в другом потоке
                        pass
                    except Exception as e:
                        print(f"[ERROR] Ошибка обновления окна расписания: {e}")
            except RuntimeError:
                # QApplication может быть недоступен
                pass
            
            # Обновляем вкладки расписания на ковре
            if hasattr(self, 'tab_widget') and self.tab_widget:
                try:
                    tab_count = self.tab_widget.count()
                    for i in range(tab_count):
                        try:
                            widget = self.tab_widget.widget(i)
                            if widget and isinstance(widget, MatScheduleWindow):
                                widget.update_data(self.tournament_data)
                        except (RuntimeError, AttributeError):
                            # Виджет может быть удален или находиться в другом потоке
                            pass
                        except Exception as e:
                            print(f"[ERROR] Ошибка обновления вкладки расписания: {e}")
                except RuntimeError:
                    # tab_widget может быть недоступен
                    pass
        except Exception as e:
            print(f"[ERROR] Критическая ошибка при обновлении расписания: {e}")

    def closeEvent(self, event):
        """Обработчик закрытия приложения"""
        logger = get_logger()
        if logger:
            logger.log_info("Приложение закрывается", {"is_secondary": self.is_secondary})
        
        try:
            if hasattr(self, 'tournament_data') and self.tournament_data:
                self.save_tournament_data()
        except Exception as e:
            if logger:
                logger.log_error("Ошибка при сохранении данных при закрытии", e)
        
        try:
            if hasattr(self, 'network_manager'):
                self.network_manager.stop()
        except Exception as e:
            if logger:
                logger.log_error("Ошибка при остановке network_manager", e)

        try:
            if hasattr(self, 'schedule_sync_service'):
                self.schedule_sync_service.stop()
        except Exception as e:
            if logger:
                logger.log_error("Ошибка при остановке schedule_sync_service", e)
        
        event.accept()
    
    def _send_log_to_coordinator(self, log_entry):
        """Отправляет лог на coordinator через schedule_sync_service"""
        # Проверяем, что сервис инициализирован и запущен
        if not hasattr(self, 'schedule_sync_service'):
            return
        if not self.schedule_sync_service:
            return
        if not hasattr(self.schedule_sync_service, 'running'):
            return
        if not self.schedule_sync_service.running:
            return
        if not hasattr(self.schedule_sync_service, 'send_log'):
            return
        
        try:
            # Дополнительная проверка - убеждаемся, что сокет создан
            if not hasattr(self.schedule_sync_service, '_sock') or not self.schedule_sync_service._sock:
                return
            self.schedule_sync_service.send_log(log_entry)
        except AttributeError:
            # Сервис еще не полностью инициализирован
            pass
        except Exception as e:
            # Не логируем ошибки отправки логов, чтобы избежать рекурсии
            try:
                print(f"Ошибка отправки лога на coordinator: {e}")
            except:
                pass
    
    def _on_log_received(self, log_data):
        """Обработчик получения лога от другого устройства (только для coordinator)"""
        logger = get_logger()
        if not logger:
            return
        
        try:
            # Записываем лог в файл coordinator для всех устройств
            if logger.coordinator_log_file:
                log_line = json.dumps(log_data, ensure_ascii=False) + "\n"
                with open(logger.coordinator_log_file, 'a', encoding='utf-8') as f:
                    f.write(log_line)
                    f.flush()  # Принудительная запись в реальном времени
            
            # Также записываем в отдельный файл для конкретного устройства
            device_name = log_data.get("device", "unknown")
            device_id = log_data.get("device_id", "unknown")
            device_log_file = logger.log_dir / f"{device_name}_{device_id}.log"
            if device_log_file:
                log_line = json.dumps(log_data, ensure_ascii=False) + "\n"
                with open(device_log_file, 'a', encoding='utf-8') as f:
                    f.write(log_line)
                    f.flush()  # Принудительная запись в реальном времени
        except Exception as e:
            print(f"Ошибка записи лога от устройства: {e}")

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