import json
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QGroupBox, QListWidget, QComboBox, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog, 
                             QTabWidget, QLineEdit, QTextEdit, QInputDialog, QApplication)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor
from core.utils import create_bracket, generate_schedule
from core.settings import get_settings
from ui.dialogs.wrestler_dialogs import AddWrestlerDialog, MoveWrestlerDialog
from ui.dialogs.category_dialogs import CategoryEditDialog
from ui.widgets.network_sync_tab import NetworkSyncTab

class SecretaryWindow(QMainWindow):
    def __init__(self, tournament_data, network_manager, schedule_sync=None, parent=None):
        super().__init__(parent)
        self.tournament_data = tournament_data
        self.network_manager = network_manager
        self.schedule_sync = schedule_sync
        self.setWindowTitle("Секретариат — Главный секретарь")
        self.setGeometry(200, 100, 1100, 750)
        self.setup_ui()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # === Заголовок ===
        title = QLabel("СЕКРЕТАРИАТ — РЕДАКТИРОВАНИЕ ТУРНИРА")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px; background-color: #4CAF50; color: white;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # === Вкладки ===
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # --- Вкладка: Категории ---
        cat_tab = QWidget()
        cat_layout = QVBoxLayout(cat_tab)
        self.setup_categories_tab(cat_layout)
        tabs.addTab(cat_tab, "Категории")

        # --- Вкладка: Участники ---
        part_tab = QWidget()
        part_layout = QVBoxLayout(part_tab)
        self.setup_participants_tab(part_layout)
        tabs.addTab(part_tab, "Участники")

        # --- Вкладка: Сетевой модуль ---
        self.network_tab = NetworkSyncTab(
            self.tournament_data,
            self.schedule_sync,
            on_schedule_apply=self.apply_remote_schedule,
            parent=self,
        )
        tabs.addTab(self.network_tab, "Сетевой модуль")

        # --- Кнопки сохранения ---
        save_layout = QHBoxLayout()
        save_btn = QPushButton("💾 Сохранить турнир")
        save_btn.clicked.connect(self.save_tournament)
        save_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        save_layout.addWidget(save_btn)

        regenerate_btn = QPushButton("🔄 Пересоздать сетку и расписание")
        regenerate_btn.clicked.connect(self.regenerate_all)
        regenerate_btn.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold; padding: 10px;")
        save_layout.addWidget(regenerate_btn)

        layout.addLayout(save_layout)

    def open_categories_manager(self):
        main_window = self.parent()
        if not main_window:
            return
        tab_name = "Редактор категорий"
        if main_window.tab_exists(tab_name):
            return
        manager = CategoriesManagerTab(self.tournament_data, self.network_manager, main_window)
        main_window.tab_widget.addTab(manager, tab_name)
        main_window.tab_widget.setCurrentIndex(main_window.tab_widget.count() - 1)
    
    def setup_categories_tab(self, layout):
        # Убираем старый список — всё будет в отдельной вкладке
        open_btn = QPushButton("Открыть редактор категорийн")
        open_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 10px;")
        open_btn.clicked.connect(self.open_categories_manager)
        layout.addWidget(open_btn)



    def setup_participants_tab(self, layout):
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Категория:"))
        self.part_cat_combo = QComboBox()
        top_layout.addWidget(self.part_cat_combo)
        layout.addLayout(top_layout)

        self.part_list = QListWidget()
        layout.addWidget(self.part_list)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self.add_wrestler)
        btn_layout.addWidget(add_btn)

        move_btn = QPushButton("Переместить")
        move_btn.clicked.connect(self.move_wrestler)
        btn_layout.addWidget(move_btn)

        layout.addLayout(btn_layout)

        self.part_cat_combo.currentTextChanged.connect(self.update_participants_list)
        self.update_categories_combo()

    def update_categories_list(self):
        self.cat_list.clear()
        for name, data in self.tournament_data['categories'].items():
            count = len(data.get('participants', []))
            item = f"{name} — {count} участников"
            self.cat_list.addItem(item)

    def update_categories_combo(self):
        self.part_cat_combo.clear()
        for name in self.tournament_data['categories'].keys():
            self.part_cat_combo.addItem(name)
        if self.part_cat_combo.count() > 0:
            self.update_participants_list()

    def update_participants_list(self):
        cat = self.part_cat_combo.currentText()
        self.part_list.clear()
        if cat and cat in self.tournament_data['categories']:
            for p in self.tournament_data['categories'][cat]['participants']:
                self.part_list.addItem(p['name'])

    def add_category(self):
        dialog = CategoryEditDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            name = data['name']
            if name in self.tournament_data['categories']:
                QMessageBox.warning(self, "Ошибка", "Категория уже существует")
                return
            self.tournament_data['categories'][name] = {
                'gender': data['gender'],
                'age_min': data['age_min'],
                'age_max': data['age_max'],
                'weight_min': data['weight_min'],
                'weight_max': data['weight_max'],
                'participants': [],
                'matches': []
            }
            self.update_categories_list()
            self.update_categories_combo()

    def edit_category(self):
        item = self.cat_list.currentItem()
        if not item:
            return
        old_name = item.text().split(' — ')[0]
        cat = self.tournament_data['categories'][old_name]

        dialog = CategoryEditDialog(self, old_name, cat)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            new_name = data['name']
            if new_name != old_name and new_name in self.tournament_data['categories']:
                QMessageBox.warning(self, "Ошибка", "Категория уже существует")
                return
            if new_name != old_name:
                self.tournament_data['categories'][new_name] = self.tournament_data['categories'].pop(old_name)
            self.tournament_data['categories'][new_name].update({
                'gender': data['gender'],
                'age_min': data['age_min'],
                'age_max': data['age_max'],
                'weight_min': data['weight_min'],
                'weight_max': data['weight_max']
            })
            self.update_categories_list()
            self.update_categories_combo()

    def delete_category(self):
        item = self.cat_list.currentItem()
        if not item:
            return
        name = item.text().split(' — ')[0]
        reply = QMessageBox.question(self, "Удалить", f"Удалить категорию '{name}' и всех участников?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            del self.tournament_data['categories'][name]
            self.tournament_data['participants'] = [p for p in self.tournament_data['participants'] if p.get('category') != name]
            self.regenerate_all()
            self.update_categories_list()
            self.update_categories_combo()

    def add_wrestler(self):
        cat = self.part_cat_combo.currentText()
        if not cat:
            return
        dialog = AddWrestlerDialog(self.tournament_data['date'], self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            data['category'] = cat
            self.tournament_data['participants'].append(data)
            self.tournament_data['categories'][cat]['participants'].append(data)
            self.regenerate_bracket(cat)
            self.update_participants_list()

    def move_wrestler(self):
        cat = self.part_cat_combo.currentText()
        item = self.part_list.currentItem()
        if not cat or not item:
            return
        name = item.text()
        dialog = MoveWrestlerDialog(self.tournament_data['categories'], cat, self)
        if dialog.exec_() == QDialog.Accepted:
            target = dialog.get_target()
            if target == cat:
                return
            # Перемещение
            wrestler = None
            for i, p in enumerate(self.tournament_data['categories'][cat]['participants']):
                if p['name'] == name:
                    wrestler = self.tournament_data['categories'][cat]['participants'].pop(i)
                    break
            if wrestler:
                wrestler['category'] = target
                self.tournament_data['categories'][target]['participants'].append(wrestler)
                for p in self.tournament_data['participants']:
                    if p['name'] == name:
                        p['category'] = target
                        break
                self.regenerate_bracket(cat)
                self.regenerate_bracket(target)
                self.update_participants_list()

    def regenerate_bracket(self, cat):
        wrestlers = self.tournament_data['categories'][cat]['participants']
        bracket = create_bracket(wrestlers, cat)
        self.tournament_data['categories'][cat]['matches'] = bracket['matches']
        self.tournament_data['categories'][cat]['type'] = bracket['type']

    def regenerate_all(self):
        for cat in self.tournament_data['categories']:
            self.regenerate_bracket(cat)
        self.generate_schedule()
        self.broadcast_update()

    def generate_schedule(self):
        try:
            settings = get_settings()
            # Перезагружаем настройки перед генерацией
            settings.load_settings()
            n_mats = settings.get("tournament", "number_of_mats", 2)
            print(f"[DEBUG secretary.generate_schedule] Прочитано n_mats={n_mats} (тип: {type(n_mats).__name__})")
            if n_mats < 1:
                n_mats = 2  # Минимум 2 ковра
                settings.set("tournament", "number_of_mats", n_mats)
                print(f"[WARNING] Количество ковров было меньше 1, установлено значение {n_mats}")
            schedule = generate_schedule(self.tournament_data, start_time="10:00", match_duration=8, n_mats=n_mats)
            self.tournament_data['schedule'] = schedule
            print(f"[INFO] Расписание сгенерировано для {n_mats} ковров")
        except Exception as e:
            print("Ошибка генерации расписания:", e)
            import traceback
            traceback.print_exc()

    def broadcast_update(self):
        """Отправляет обновлённые данные турнира всем клиентам"""
        if self.network_manager and self.network_manager.is_server:
            self.network_manager.send_message('tournament_update', self.tournament_data)
        if self.schedule_sync:
            self.schedule_sync.push_schedule(self.tournament_data)
        if hasattr(self, "network_tab") and self.network_tab:
            self.network_tab.update_data(self.tournament_data)

    def apply_remote_schedule(self, schedule):
        """Применяет расписание, пришедшее по сети."""
        if not schedule:
            return
        # Объединяем расписание, чтобы не терять данные других ковров
        def make_key(m):
            mid = m.get('match_id')
            if mid:
                return ('id', mid)
            return (
                'tuple',
                m.get('category', ''),
                m.get('wrestler1', ''),
                m.get('wrestler2', ''),
                m.get('mat', 0),
                m.get('time', ''),
                m.get('round', 0),
            )

        existing = self.tournament_data.get('schedule', []) if isinstance(self.tournament_data, dict) else []
        merged = {}
        for m in existing:
            merged[make_key(m)] = m
        for m in schedule:
            merged[make_key(m)] = m
        merged_list = list(merged.values())
        merged_list.sort(key=lambda x: (
            x.get('time', ''),
            x.get('mat', 0),
            x.get('round', 0),
            x.get('match_id', '')
        ))
        self.tournament_data['schedule'] = merged_list
        # уведомляем главное окно о смене данных
        if self.parent() and hasattr(self.parent(), 'update_schedule_tab'):
            self.parent().update_schedule_tab()
        QMessageBox.information(self, "Синхронизация", "Расписание обновлено из сети.")

    def save_tournament(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Сохранить", "", "JSON (*.json)")
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(self.tournament_data, f, ensure_ascii=False, indent=2, default=str)
                QMessageBox.information(self, "Успех", "Турнир сохранён")
                self.broadcast_update()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", str(e))

class CategoriesManagerTab(QWidget):
    def __init__(self, tournament_data, network_manager, parent=None):
        super().__init__(parent)
        self.tournament_data = tournament_data
        self.network_manager = network_manager
        self.expanded_category = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Заголовок
        title = QLabel("РЕДАКТОР КАТЕГОРИЙ")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px; background-color: #4CAF50; color: white;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Список категорий
        self.cat_list = QListWidget()
        self.cat_list.itemClicked.connect(self.toggle_category)
        layout.addWidget(self.cat_list)

        # Кнопки управления
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Добавить категорию")
        add_btn.clicked.connect(self.add_category)
        btn_layout.addWidget(add_btn)

        edit_btn = QPushButton("Редактировать")
        edit_btn.clicked.connect(self.edit_category)
        btn_layout.addWidget(edit_btn)

        delete_btn = QPushButton("Удалить")
        delete_btn.clicked.connect(self.delete_category)
        btn_layout.addWidget(delete_btn)

        layout.addLayout(btn_layout)

                # Поиск по ФИО
        search_layout = QHBoxLayout()
        search_label = QLabel("Поиск по ФИО:")
        search_label.setStyleSheet("font-weight: bold;")
        search_layout.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Введите ФИО участника...")
        self.search_input.textChanged.connect(self.on_search)
        search_layout.addWidget(self.search_input)

        clear_btn = QPushButton("X")
        clear_btn.setFixedWidth(30)
        clear_btn.clicked.connect(self.clear_search)
        search_layout.addWidget(clear_btn)

        layout.addLayout(search_layout)

        # Контейнер для раскрытой категории
        self.expanded_container = QWidget()
        self.expanded_layout = QVBoxLayout(self.expanded_container)
        self.expanded_layout.setContentsMargins(20, 10, 20, 10)
        self.expanded_container.setStyleSheet("background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 8px;")
        layout.addWidget(self.expanded_container)
        self.expanded_container.hide()

        self.update_categories_list()

    def update_categories_list(self):
        self.cat_list.clear()
        for name, data in self.tournament_data['categories'].items():
            count = len(data.get('participants', []))
            item_text = f"{name} — {count} участников"
            self.cat_list.addItem(item_text)

    def toggle_category(self, item):
        category_name = item.text().split(' — ')[0]
        if self.expanded_category == category_name:
            self.expanded_container.hide()
            self.expanded_category = None
        else:
            self.expanded_category = category_name
            self.show_category_details(category_name)
            self.expanded_container.show()

    def show_category_details(self, category_name):
        # Очищаем предыдущее содержимое
        for i in reversed(range(self.expanded_layout.count())):
            child = self.expanded_layout.itemAt(i).widget()
            if child:
                try:
                    # Используем deleteLater вместо setParent для безопасности
                    if child.isWidgetType():
                        child.deleteLater()
                except (RuntimeError, AttributeError):
                    # Виджет уже удален
                    pass

        cat_data = self.tournament_data['categories'][category_name]

        # === ЗАЩИТА: добавляем недостающие поля, если их нет ===
        defaults = {
            'gender': 'Мужской',
            'age_min': 0,
            'age_max': 99,
            'weight_min': 0,
            'weight_max': 200,
            'participants': [],
            'matches': []
        }
        for key, default in defaults.items():
            if key not in cat_data:
                cat_data[key] = default

        # Заголовок категории
        header = QLabel(f"Категория: {category_name}")
        header.setStyleSheet("font-size: 16px; font-weight: bold; margin: 5px 0;")
        self.expanded_layout.addWidget(header)

        # Информация — теперь безопасно
        info = f"Пол: {cat_data['gender']} | Возраст: {cat_data['age_min']}–{cat_data['age_max']} | Вес: {cat_data['weight_min']}–{cat_data['weight_max']} кг"
        info_label = QLabel(info)
        info_label.setStyleSheet("color: #555; margin-bottom: 10px;")
        self.expanded_layout.addWidget(info_label)

        # Таблица участников
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["ФИО", "Клуб", "ДР", "Вес", "Разряд", "Действия"])
        participants = cat_data.get('participants', [])
        table.setRowCount(len(participants))

        search_text = self.search_input.text().strip().lower() if hasattr(self, 'search_input') else ""

        for i, p in enumerate(participants):
            name_item = QTableWidgetItem(p.get('name', ''))
            club_item = QTableWidgetItem(p.get('club', ''))
            birth_item = QTableWidgetItem(p.get('birth_date', ''))
            weight_item = QTableWidgetItem(str(p.get('weight', '')))
            rank_item = QTableWidgetItem(p.get('rank', ''))

            # Подсветка, если совпадает с поиском
            if search_text and search_text in p.get('name', '').lower():
                for item in [name_item, club_item, birth_item, weight_item, rank_item]:
                    item.setBackground(QBrush(QColor(255, 255, 0, 100)))

            table.setItem(i, 0, name_item)
            table.setItem(i, 1, club_item)
            table.setItem(i, 2, birth_item)
            table.setItem(i, 3, weight_item)
            table.setItem(i, 4, rank_item)  # Правильно: колонка 4

            # Кнопка "Переместить"
            move_btn = QPushButton("Переместить")
            move_btn.clicked.connect(lambda _, name=p.get('name', ''): self.move_wrestler(name))
            table.setCellWidget(i, 5, move_btn)

        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.expanded_layout.addWidget(table)

        # Кнопка "Добавить участника"
        add_wrestler_btn = QPushButton("Добавить участника в эту категорию")
        add_wrestler_btn.clicked.connect(lambda: self.add_wrestler_to_category(category_name))
        self.expanded_layout.addWidget(add_wrestler_btn)

    def on_search(self, text):
        search_text = text.strip().lower()
        if not search_text:
            self.clear_search()
            return

        found = False
        for cat_name, cat_data in self.tournament_data['categories'].items():
            for participant in cat_data.get('participants', []):
                if search_text in participant.get('name', '').lower():
                    # Раскрываем категорию
                    if self.expanded_category != cat_name:
                        self.expanded_category = cat_name
                        self.show_category_details(cat_name)
                        self.expanded_container.show()

                    # Прокручиваем таблицу к участнику
                    table = self.expanded_container.findChild(QTableWidget)
                    if table:
                        for row in range(table.rowCount()):
                            item = table.item(row, 0)
                            if item and search_text in item.text().lower():
                                table.selectRow(row)
                                table.scrollToItem(item)
                                found = True
                                break
                    if found:
                        break
            if found:
                break

        if not found:
            QMessageBox.information(self, "Поиск", f"Участник с ФИО, содержащим '{text}', не найден.")

    def clear_search(self):
        self.search_input.clear()
        if self.expanded_category:
            self.show_category_details(self.expanded_category)  # Перерисовываем без выделения

    def add_category(self):
        dialog = CategoryEditDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            name = data['name']
            if name in self.tournament_data['categories']:
                QMessageBox.warning(self, "Ошибка", "Категория уже существует")
                return
            self.tournament_data['categories'][name] = {
                'gender': data['gender'],
                'age_min': data['age_min'],
                'age_max': data['age_max'],
                'weight_min': data['weight_min'],
                'weight_max': data['weight_max'],
                'participants': [],
                'matches': []
            }
            self.update_categories_list()
            self.broadcast_update()

    def edit_category(self):
        if not self.expanded_category:
            QMessageBox.warning(self, "Ошибка", "Выберите категорию")
            return
        old_name = self.expanded_category
        cat = self.tournament_data['categories'][old_name]
        dialog = CategoryEditDialog(self, old_name, cat)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            new_name = data['name']
            if new_name != old_name and new_name in self.tournament_data['categories']:
                QMessageBox.warning(self, "Ошибка", "Категория уже существует")
                return
            if new_name != old_name:
                self.tournament_data['categories'][new_name] = self.tournament_data['categories'].pop(old_name)
            self.tournament_data['categories'][new_name].update({
                'gender': data['gender'],
                'age_min': data['age_min'],
                'age_max': data['age_max'],
                'weight_min': data['weight_min'],
                'weight_max': data['weight_max']
            })
            self.expanded_category = new_name
            self.update_categories_list()
            self.show_category_details(new_name)
            self.broadcast_update()

    def delete_category(self):
        if not self.expanded_category:
            QMessageBox.warning(self, "Ошибка", "Выберите категорию")
            return
        name = self.expanded_category
        reply = QMessageBox.question(self, "Удалить", f"Удалить категорию '{name}' и всех участников?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            del self.tournament_data['categories'][name]
            self.tournament_data['participants'] = [p for p in self.tournament_data['participants'] if p.get('category') != name]
            self.expanded_container.hide()
            self.expanded_category = None
            self.update_categories_list()
            self.broadcast_update()

    def add_wrestler_to_category(self, category_name):
        dialog = AddWrestlerDialog(self.tournament_data.get('date', ''), self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            data['category'] = category_name
            self.tournament_data['participants'].append(data)
            self.tournament_data['categories'][category_name]['participants'].append(data)
            self.show_category_details(category_name)
            self.broadcast_update()

    def move_wrestler(self, wrestler_name):
        dialog = MoveWrestlerDialog(self.tournament_data['categories'], self.expanded_category, self)
        if dialog.exec_() == QDialog.Accepted:
            target = dialog.get_target()
            if target == self.expanded_category:
                return
            # Перемещение
            for i, p in enumerate(self.tournament_data['categories'][self.expanded_category]['participants']):
                if p['name'] == wrestler_name:
                    moved = self.tournament_data['categories'][self.expanded_category]['participants'].pop(i)
                    break
            moved['category'] = target
            self.tournament_data['categories'][target]['participants'].append(moved)
            for p in self.tournament_data['participants']:
                if p['name'] == wrestler_name:
                    p['category'] = target
                    break
            self.show_category_details(self.expanded_category)
            self.broadcast_update()

    def broadcast_update(self):
        if self.network_manager and self.network_manager.is_server:
            self.network_manager.send_message('tournament_update', self.tournament_data)