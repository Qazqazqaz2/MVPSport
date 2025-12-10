# ui/widgets/schedule.py
import json
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QMenu, QAction,
    QMessageBox, QHeaderView, QGroupBox, QTextEdit, QApplication,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QMainWindow,
    QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QFont, QTextDocument, QAbstractTextDocumentLayout, QBrush, QColor, QKeyEvent

from core.utils import get_wrestler_club


# ===================================================================
#  ДЕЛЕГАТ: HTML + компактные строки
# ===================================================================
class HtmlDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)

        painter.save()
        style = option.widget.style() if option.widget else QApplication.style()

        # Рисуем фон ячейки (включая установленный через setBackground)
        brush = options.backgroundBrush
        if brush and brush.style() != Qt.NoBrush:
            painter.fillRect(option.rect, brush)
        
        # Рисуем стандартный фон элемента
        style.drawPrimitive(QStyle.PE_PanelItemViewItem, options, painter, option.widget)

        # HTML
        doc = QTextDocument()
        doc.setHtml(options.text)

        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, options, option.widget)
        painter.translate(text_rect.topLeft())
        painter.setClipRect(text_rect.translated(-text_rect.topLeft()))

        ctx = QAbstractTextDocumentLayout.PaintContext()
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def sizeHint(self, option, index):
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        doc = QTextDocument()
        doc.setHtml(options.text)
        doc.setTextWidth(options.rect.width())
        # Минимальная высота — как у обычного текста
        return QSize(int(doc.idealWidth()), int(doc.size().height()) + 4)  # +4 на отступы


def filter_schedule_items(schedule, query="", mat_filter=None):
    """Фильтрация списка матчей по поисковому запросу и номеру ковра."""
    if not schedule:
        return []
    query = (query or "").strip().lower()

    def matches_query(item):
        if not query:
            return True
        fields = [
            item.get("category", ""),
            item.get("wrestler1", ""),
            item.get("wrestler2", ""),
            item.get("club1", ""),
            item.get("club2", ""),
            str(item.get("time", "")),
            str(item.get("mat", "")),
        ]
        return any(query in str(f).lower() for f in fields)

    result = []
    for item in schedule:
        if mat_filter is not None and item.get("mat") != mat_filter:
            continue
        if matches_query(item):
            result.append(item)
    return result


# ===================================================================
#  ScheduleWindow
# ===================================================================
class ScheduleWindow(QWidget):
    def __init__(self, tournament_data, parent=None, network_manager=None):
        super().__init__(parent)
        self.tournament_data = tournament_data
        self.network_manager = network_manager
        self.search_query = ""
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        if not self.tournament_data:
            layout.addWidget(QLabel("Турнир не загружен"))
            return

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск по имени, категории, клубу или ковру...")
        self.search_input.textChanged.connect(self.on_search_changed)
        search_row.addWidget(self.search_input)
        clear_btn = QPushButton("Очистить")
        clear_btn.clicked.connect(lambda: self.search_input.clear())
        search_row.addWidget(clear_btn)
        layout.addLayout(search_row)

        title = QLabel(
            f"{self.tournament_data.get('name','')} - "
            f"{self.tournament_data.get('date','')} - "
            f"{self.tournament_data.get('location','')}"
        )
        title.setStyleSheet("""
            font-size: 24px; 
            font-weight: bold; 
            padding: 15px; 
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                stop:0 #2c3e50, stop:1 #34495e);
            color: white;
            border-radius: 8px;
            margin-bottom: 10px;
        """)
        layout.addWidget(title)

        self.schedule_table = self.create_schedule_table()
        layout.addWidget(self.schedule_table)

        total = len(self.tournament_data.get('schedule', []))
        stats = QLabel(f"Всего матчей: {total}")
        stats.setStyleSheet("font-weight: bold; margin: 10px; font-size: 16px;")
        layout.addWidget(stats)

    def on_search_changed(self, text):
        self.search_query = text
        self.update_data(self.tournament_data)

    @staticmethod
    def build_schedule_table(schedule, mats, on_double_click):
        """Общая сборка таблицы расписания (используется также расписанием на ковре)."""
        if not schedule:
            empty = QTableWidget()
            empty.setRowCount(1)
            empty.setColumnCount(1)
            empty.setItem(0, 0, QTableWidgetItem("Расписание не сгенерировано"))
            return empty

        n_mats = len(mats)

        table = QTableWidget()
        # Максимум строк — количество матчей (по всем коврам); заполняем динамически по матовым счётчикам
        table.setRowCount(len(schedule) or 1)
        table.setColumnCount(1 + n_mats)

        headers = ['№ схватки']
        headers.extend([f'Ковёр {m}' for m in mats])
        table.setHorizontalHeaderLabels(headers)

        # === РАЗМЕРЫ ===
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        table.setColumnWidth(0, 70)

        # === ДЕЛЕГАТ ===
        delegate = HtmlDelegate(table)
        table.setItemDelegate(delegate)

        # === СТИЛИ ===
        table.setShowGrid(True)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setStyleSheet("""
            QTableWidget {
                font-size: 16px; 
                gridline-color: #d0d0d0;
                background-color: #ffffff;
                alternate-background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
            QTableWidget::item {
                padding: 8px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #007bff;
                color: white;
            }
            QHeaderView::section {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #495057, stop:1 #343a40);
                color: white;
                font-weight: bold;
                padding: 12px;
                border: 1px solid #212529;
                font-size: 16px;
                border-radius: 0px;
            }
            QTableCornerButton::section {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #495057, stop:1 #343a40);
                border: 1px solid #212529;
            }
        """)
        
        # Включаем альтернативные цвета строк
        table.setAlternatingRowColors(True)
        
        if on_double_click:
            table.itemDoubleClicked.connect(on_double_click)

        # === НУМЕРАЦИЯ ===
        num_font = QFont()
        num_font.setPointSize(20)
        num_font.setBold(True)

        # === ЗАПОЛНЕНИЕ ===
        # Счётчик строк для каждого ковра, чтобы матчи не затирали друг друга
        row_by_mat = {m: 0 for m in mats}
        
        for match in schedule:
            mat = match['mat']
            col = mats.index(mat) + 1
            row = row_by_mat.get(mat, 0)
            row_by_mat[mat] = row + 1

            # Убедимся, что хватает строк
            if row >= table.rowCount():
                table.setRowCount(row + 1)

            # № схватки
            if table.item(row, 0) is None:
                num_item = QTableWidgetItem(str(row + 1))
                num_item.setFont(num_font)
                num_item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, 0, num_item)

            # HTML с улучшенным дизайном
            time_str = match.get('time', '')
            time_html = f'<div style="color:#6c757d; font-size:12px; margin-bottom:4px;">{time_str}</div>' if time_str else ''
            
            html = f"""
            <div style="text-align:center; font-family:'Segoe UI', Arial, sans-serif; padding: 4px;">
                {time_html}
                <div style="font-weight:bold; color:#212529; font-size:16px; margin-bottom:4px; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    background-clip: text;">
                    {match['category']}
                </div>
                <div style="color:{match.get('color1') or '#dc3545'}; font-weight:bold; font-size:17px; margin-bottom:2px;">
                    {match['wrestler1']}
                </div>
                <div style="color:{match.get('color1') or '#dc3545'}; font-weight:normal; font-size:13px; margin-bottom:6px; opacity:0.8;">
                    {match['club1']}
                </div>
                <div style="color:{match.get('color2') or '#0066cc'}; font-weight:bold; font-size:17px; margin-bottom:2px;">
                    {match['wrestler2']}
                </div>
                <div style="color:{match.get('color2') or '#0066cc'}; font-weight:normal; font-size:13px; opacity:0.8;">
                    {match['club2']}
                </div>
            </div>
            """
            item = QTableWidgetItem()
            item.setData(Qt.DisplayRole, html)
            item.setData(Qt.UserRole, match)
            item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, col, item)

        # Выделяем прошедшие бои фоновым цветом
        completed_color = QBrush(QColor(200, 220, 240))  # Более яркий голубой для завершенных матчей
        
        for match in schedule:
            mat = match['mat']
            col = mats.index(mat) + 1
            row = match['round'] - 1
            
            # Проверяем, завершен ли этот конкретный матч (несколько способов проверки)
            status = match.get('status', '')
            completed_at = match.get('completed_at')
            completed = match.get('completed', False)
            
            is_completed = (
                status == 'Завершен' or 
                (completed_at is not None and completed_at != '') or
                completed is True
            )
            
            if is_completed:
                # Выделяем ячейку с завершенным матчем
                item = table.item(row, col)
                if item:
                    item.setBackground(completed_color)
                else:
                    # Если item еще не создан, создаем его с фоном
                    empty_item = QTableWidgetItem()
                    empty_item.setBackground(completed_color)
                    table.setItem(row, col, empty_item)
                
                # Также выделяем номер схватки
                num_item = table.item(row, 0)
                if num_item:
                    num_item.setBackground(completed_color)

        return table

    def get_filtered_schedule(self, mat_filter=None):
        return filter_schedule_items(self.tournament_data.get('schedule', []), self.search_query, mat_filter)

    def create_schedule_table(self, mat_filter=None):
        schedule = self.get_filtered_schedule(mat_filter)
        if not schedule:
            empty = QTableWidget()
            empty.setRowCount(1)
            empty.setColumnCount(1)
            empty.setItem(0, 0, QTableWidgetItem("Расписание не сгенерировано"))
            return empty
        mats = sorted({m['mat'] for m in schedule}) if not mat_filter else [mat_filter]
        return self.build_schedule_table(schedule, mats, self.on_match_double_click)

    @staticmethod
    def _make_match_html(match, mat=None):
        cat = match.get('category', '')
        w1 = match.get('wrestler1', '')
        w1_plain = w1  # Чистое имя для ковра 1
        c1 = match.get('club1', '')
        w2 = match.get('wrestler2', '')
        w2_plain = w2  # Чистое имя для ковра 1
        c2 = match.get('club2', '')
        winner = match.get('winner')
        color1 = match.get('color1') or "#dc3545"
        color2 = match.get('color2') or "#0066cc"
        
        # Если не передан номер ковра, пытаемся получить из match
        if mat is None:
            mat = match.get('mat')

        if winner == w1:
            w1 = f"<b><u>{w1}</u></b>"
            c1 = f"<b>{c1}</b>"
        elif winner == w2:
            w2 = f"<b><u>{w2}</u></b>"
            c2 = f"<b>{c2}</b>"
        else:
            w1 = f"<b>{w1}</b>"
            w2 = f"<b>{w2}</b>"

        # Для ковра 1: "Категория, ФИО участников"
        if mat == 1:
            return f"""
            <div style="text-align:center; font-family:Arial;">
                <div style="font-weight:bold; color:#000; font-size:18px;">{cat}, {w1_plain}, {w2_plain}</div>
            </div>
            """
        
        # Улучшенный HTML с более красивым дизайном
        return f"""
            <div style="text-align:center; font-family:'Segoe UI', Arial, sans-serif; padding: 4px;">
            <div style="font-weight:bold; color:#212529; font-size:16px; margin-bottom:4px; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;">
                {cat}
            </div>
            <div style="color:{color1}; font-weight:bold; font-size:17px; margin-bottom:2px;">{w1}</div>
            <div style="color:{color1}; font-weight:normal; font-size:13px; margin-bottom:6px; opacity:0.8;">{c1}</div>
            <div style="color:{color2}; font-weight:bold; font-size:17px; margin-bottom:2px;">{w2}</div>
            <div style="color:{color2}; font-weight:normal; font-size:13px; opacity:0.8;">{c2}</div>
        </div>
        """

    def on_match_double_click(self, item):
        """Обработчик двойного клика по строке расписания"""
        if not item:
            return
        
        match = item.data(Qt.UserRole)
        # Если в текущей ячейке нет данных матча, ищем в других ячейках той же строки
        if not match:
            row = item.row()
            table = self.schedule_table
            # Проходим по всем колонкам в строке, начиная с колонки 1 (колонка 0 - номер схватки)
            for col in range(1, table.columnCount()):
                row_item = table.item(row, col)
                if row_item:
                    match = row_item.data(Qt.UserRole)
                    if match:
                        break
        
        if not match:
            return
        
        # Используем ту же логику, что и в MatScheduleWindow
        reply = QMessageBox.question(
            self, "Запуск схватки",
            f"Запустить схватку?\n\n"
            f"Ковёр: {match.get('mat')}\n"
            f"Категория: {match.get('category')}\n"
            f"Красный: {match.get('wrestler1')}\n"
            f"Синий: {match.get('wrestler2')}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        match['status'] = 'В процессе'
        match['started_at'] = datetime.now().strftime("%H:%M")

        match_data = {
            'wrestler1': {
                'name': match.get('wrestler1', 'Красный'),
                'club': get_wrestler_club(self.tournament_data, match.get('wrestler1', '')),
                'category': match.get('category', '')
            },
            'wrestler2': {
                'name': match.get('wrestler2', 'Синий'),
                'club': get_wrestler_club(self.tournament_data, match.get('wrestler2', '')),
                'category': match.get('category', '')
            },
            'mat': match.get('mat'),
            'category': match.get('category', ''),
            'match_id': match.get('match_id')
        }

        # Автооткрытие панели управления
        # Ищем главное окно приложения (может быть родителем или находиться через QApplication)
        main_window = None
        
        # Сначала проверяем родителя
        parent = self.parent()
        while parent:
            if hasattr(parent, 'open_control_panel_tab') and hasattr(parent, 'find_control_panel_by_mat'):
                main_window = parent
                break
            try:
                parent = parent.parent()
            except (AttributeError, RuntimeError):
                break
        
        # Если не нашли через родителя, ищем через QApplication
        if not main_window:
            for window in QApplication.topLevelWidgets():
                if hasattr(window, 'open_control_panel_tab') and hasattr(window, 'find_control_panel_by_mat'):
                    main_window = window
                    break
        
        if main_window:
            main_window.open_control_panel_tab(mat_number=match.get('mat'))
            cp = main_window.find_control_panel_by_mat(match.get('mat'))
            if cp:
                cp.set_match_competitors(match_data['wrestler1'], match_data['wrestler2'])
                if hasattr(cp, 'set_current_match_info'):
                    cp.set_current_match_info(
                        match_data['category'],
                        match_data['wrestler1']['name'],
                        match_data['wrestler2']['name'],
                        match_data.get('match_id')
                    )
                cp.send_scoreboard_update()

        # Обновляем расписание для отображения изменений
        self.update_data(self.tournament_data)

    def update_data(self, new_tournament_data):
        self.tournament_data = new_tournament_data
        if hasattr(self, 'schedule_table'):
            self.schedule_table.setParent(None)
            self.schedule_table.deleteLater()
        self.schedule_table = self.create_schedule_table()
        self.layout().insertWidget(2, self.schedule_table)


# ===================================================================
#  ScheduleMainWindow - отдельное окно для расписания
# ===================================================================
class ScheduleMainWindow(QMainWindow):
    closed = pyqtSignal()
    
    def __init__(self, tournament_data, parent=None, network_manager=None):
        super().__init__(parent)
        self.tournament_data = tournament_data
        self.network_manager = network_manager
        
        # Настройка окна
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowTitleHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setWindowTitle("Расписание турнира")
        
        # Создаем виджет расписания
        self.schedule_widget = ScheduleWindow(tournament_data, self, network_manager)
        self.setCentralWidget(self.schedule_widget)
        
        # Горячие клавиши
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        QShortcut(QKeySequence("Alt+C"), self, self.toggle_fullscreen)
        QShortcut(QKeySequence("F11"), self, self.toggle_fullscreen)
        
        # Размеры окна
        screen = QApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            self.setGeometry(
                screen_geometry.left() + 50,
                screen_geometry.top() + 50,
                min(1400, screen_geometry.width() - 100),
                min(900, screen_geometry.height() - 100)
            )
    
    def toggle_fullscreen(self):
        """Переключает полноэкранный режим"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
    
    def keyPressEvent(self, event: QKeyEvent):
        """Обработка нажатий клавиш, включая Alt+C"""
        if (event.modifiers() & Qt.AltModifier) and event.key() == Qt.Key_C:
            self.toggle_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        self.closed.emit()
        super().closeEvent(event)
    
    def update_data(self, new_tournament_data):
        """Обновление данных турнира"""
        self.tournament_data = new_tournament_data
        if self.schedule_widget:
            self.schedule_widget.update_data(new_tournament_data)


# ===================================================================
#  MatScheduleWindow
# ===================================================================
class MatScheduleWindow(QWidget):
    match_selected = pyqtSignal(dict)

    def __init__(self, tournament_data, parent=None, network_manager=None):
        super().__init__(parent)
        self.tournament_data = tournament_data
        self.network_manager = network_manager
        self.current_mat = 1
        self.search_query = ""
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        header_label = QLabel("РАСПИСАНИЕ НА КОВРЕ")
        header_label.setFont(QFont("", 20, QFont.Bold))
        header_label.setStyleSheet("""
            padding: 12px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                stop:0 #2c3e50, stop:1 #34495e);
            color: white;
            border-radius: 8px;
        """)
        header.addWidget(header_label)
        header.addStretch()
        mat_box = QHBoxLayout()
        mat_label = QLabel("Ковер:")
        mat_label.setFont(QFont("", 16))
        mat_box.addWidget(mat_label)
        self.mat_combo = QComboBox()
        self.mat_combo.setFont(QFont("", 16))
        self.mat_combo.addItems(["1", "2", "3", "4"])
        self.mat_combo.setStyleSheet("""
            QComboBox {
                padding: 8px;
                border: 2px solid #dee2e6;
                border-radius: 6px;
                background-color: white;
                font-size: 16px;
            }
            QComboBox:hover {
                border-color: #007bff;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        self.mat_combo.currentTextChanged.connect(self.update_mat_schedule)
        mat_box.addWidget(self.mat_combo)
        header.addLayout(mat_box)
        layout.addLayout(header)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск по имени, категории или клубу")
        self.search_input.textChanged.connect(self.on_search_changed)
        search_row.addWidget(self.search_input)
        clear_btn = QPushButton("Очистить")
        clear_btn.clicked.connect(lambda: self.search_input.clear())
        search_row.addWidget(clear_btn)
        layout.addLayout(search_row)

        self.schedule_table = None
        self._table_placeholder = QWidget()
        layout.addWidget(self._table_placeholder)

        btns = QHBoxLayout()
        start_btn = QPushButton("Запустить")
        start_btn.setFont(QFont("", 16))
        start_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
        """)
        start_btn.clicked.connect(self.start_selected_match)
        btns.addWidget(start_btn)
        btns.addStretch()
        layout.addLayout(btns)

        self.update_mat_schedule()

    def on_search_changed(self, text):
        self.search_query = text
        self.update_mat_schedule()

    def update_mat_schedule(self):
        if not self.tournament_data or 'schedule' not in self.tournament_data:
            if self.schedule_table:
                self.schedule_table.setRowCount(0)
            return

        self.current_mat = int(self.mat_combo.currentText())
        mat_matches = filter_schedule_items(self.tournament_data.get('schedule', []), self.search_query, self.current_mat)

        # Перестраиваем таблицу из общей функции, чтобы стили совпадали с расписанием турнира
        new_table = ScheduleWindow.build_schedule_table(mat_matches, [self.current_mat], self.on_match_double_click)
        new_table.setContextMenuPolicy(Qt.CustomContextMenu)
        new_table.customContextMenuRequested.connect(self.show_context_menu)
        new_table.itemDoubleClicked.connect(self.on_match_double_click)
        delegate = HtmlDelegate(new_table)
        new_table.setItemDelegate(delegate)

        if self.schedule_table:
            self.schedule_table.setParent(None)
            self.schedule_table.deleteLater()
        self.schedule_table = new_table

        layout = self.layout()
        if self._table_placeholder:
            layout.replaceWidget(self._table_placeholder, self.schedule_table)
            self._table_placeholder.setParent(None)
            self._table_placeholder = None
        else:
            layout.insertWidget(3, self.schedule_table)


    def show_context_menu(self, pos):
        row = self.schedule_table.rowAt(pos.y())
        if row < 0:
            return
        menu = QMenu(self)
        start_action = QAction("Запустить", self)
        start_action.triggered.connect(lambda: self.start_match(row))
        menu.addAction(start_action)

        complete_action = QAction("Завершить", self)
        complete_action.triggered.connect(lambda: self.complete_match(row))
        menu.addAction(complete_action)

        reset_action = QAction("Сбросить", self)
        reset_action.triggered.connect(lambda: self.reset_match(row))
        menu.addAction(reset_action)

        menu.exec_(self.schedule_table.mapToGlobal(pos))

    # --------------------------------------------------------------
    #  Двойной клик / запуск
    # --------------------------------------------------------------
    def on_match_double_click(self, index):
        row = index.row()
        self.start_match(row)

    def start_selected_match(self):
        sel = self.schedule_table.selectedIndexes()
        if sel:
            self.start_match(sel[0].row())

    def start_match(self, row):
        if not self.tournament_data or 'schedule' not in self.tournament_data:
            return
        item = self.schedule_table.item(row, 1) if self.schedule_table else None
        match = item.data(Qt.UserRole) if item else None
        if not match:
            return

        reply = QMessageBox.question(
            self, "Запуск схватки",
            f"Запустить?\n\n"
            f"Ковёр: {match.get('mat')}\n"
            f"Категория: {match.get('category')}\n"
            f"Красный: {match.get('wrestler1')}\n"
            f"Синий: {match.get('wrestler2')}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        match['status'] = 'В процессе'
        match['started_at'] = datetime.now().strftime("%H:%M")

        match_data = {
            'wrestler1': {
                'name': match.get('wrestler1', 'Красный'),
                'club': get_wrestler_club(self.tournament_data, match.get('wrestler1', '')),
                'category': match.get('category', '')
            },
            'wrestler2': {
                'name': match.get('wrestler2', 'Синий'),
                'club': get_wrestler_club(self.tournament_data, match.get('wrestler2', '')),
                'category': match.get('category', '')
            },
            'mat': match.get('mat'),
            'category': match.get('category', ''),
            'match_id': match.get('match_id')
        }

        # автооткрытие панели управления
        main_window = self.window()
        if main_window and hasattr(main_window, 'open_control_panel_tab'):
            main_window.open_control_panel_tab(mat_number=match.get('mat'))
            cp = main_window.find_control_panel_by_mat(match.get('mat'))
            if cp:
                cp.set_match_competitors(match_data['wrestler1'], match_data['wrestler2'])
                if hasattr(cp, 'set_current_match_info'):
                    cp.set_current_match_info(
                        match_data['category'],
                        match_data['wrestler1']['name'],
                        match_data['wrestler2']['name'],
                        match_data.get('match_id')
                    )
                cp.send_scoreboard_update()

        self.update_mat_schedule()

    # --------------------------------------------------------------
    #  Завершение / сброс
    # --------------------------------------------------------------
    def complete_match(self, row):
        item = self.schedule_table.item(row, 1) if self.schedule_table else None
        m = item.data(Qt.UserRole) if item else None
        if m:
            m['status'] = 'Завершен'
            m['completed_at'] = datetime.now().strftime("%H:%M")
            self.update_mat_schedule()

    def reset_match(self, row):
        item = self.schedule_table.item(row, 1) if self.schedule_table else None
        m = item.data(Qt.UserRole) if item else None
        if m:
            m['status'] = 'Ожидание'
            for k in ('started_at', 'completed_at'):
                m.pop(k, None)
            self.update_mat_schedule()

    # --------------------------------------------------------------
    #  Обновление данных
    # --------------------------------------------------------------
    def update_data(self, new_tournament_data):
        self.tournament_data = new_tournament_data
        self.update_mat_schedule()