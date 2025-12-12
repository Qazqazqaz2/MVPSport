# control_panel.py
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QGroupBox, QGridLayout, QLineEdit, QTextEdit, QFileDialog,
                             QMessageBox, QSplitter, QApplication, QMainWindow, QShortcut,
                             QHeaderView, QInputDialog, QTimeEdit, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QTime
from PyQt5.QtGui import QKeySequence, QFont, QKeyEvent
from PyQt5.QtGui import QIntValidator
import json
import time
import re

class DummyWinsound:
    @staticmethod
    def Beep(frequency, duration):
        print(f"Beep: {frequency}Hz for {duration}ms")
        pass

try:
    import winsound
except ImportError:
    winsound = DummyWinsound()

from datetime import datetime
from core.constants import *
from core.models import Wrestler, MatchHistory
from core.network import NetworkManager
from core.db import save_match_result
from core.settings import get_settings
from ui.widgets.scoreboard import ScoreboardWindow
from ui.widgets.schedule import ScheduleWindow, filter_schedule_items
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QMessageBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush

class BracketTab(QWidget):
    def __init__(self, tournament_data, control_panel, parent=None):
        super().__init__(parent)
        self.tournament_data = tournament_data
        self.control_panel = control_panel
        self.setup_ui()
       
    def setup_ui(self):
        layout = QVBoxLayout(self)
       
        # Кнопка обновления
        refresh_btn = QPushButton("Обновить сетку")
        refresh_btn.clicked.connect(self.refresh_bracket)
        layout.addWidget(refresh_btn)
       
        # Таблица сетки
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.load_match_from_bracket)  # Автоматическая загрузка при двойном клике
        self.table.cellClicked.connect(self.update_wrestlers_info_on_click)
        layout.addWidget(self.table)
       
        self.refresh_bracket()
   
    def refresh_bracket(self):
        """Обновляет отображение сетки"""
        if not self.tournament_data:
            return
           
        categories = self.tournament_data.get('categories', {})
       
        # Для простоты отображаем первую категорию
        if not categories:
            return
           
        first_category = list(categories.keys())[0]
        category = categories[first_category]
       
        # Определяем тип турнира: круговая или олимпийская система
        is_round_robin = category.get('type') == 'round_robin'
       
        if is_round_robin:
            self.setup_round_robin_table(category)
        else:
            self.setup_olympic_bracket(category)
   
    def setup_round_robin_table(self, category):
        """Настройка таблицы для круговой системы"""
        matches = category.get('matches', [])
        # В актуальной структуре турнира участники категории лежат в 'participants'.
        # Поддерживаем также старое поле 'wrestlers', если оно есть.
        wrestlers = category.get('wrestlers') or category.get('participants', [])
       
        num_wrestlers = len(wrestlers)
        if num_wrestlers == 0:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return
        
        # Сначала вычисляем статистику для всех участников
        participant_names = [w.get('name', '') for w in wrestlers]
        index_by_name = {name: idx for idx, name in enumerate(participant_names)}
        results = [["" for _ in range(num_wrestlers)] for _ in range(num_wrestlers)]
        stats = {name: {"wins": 0, "losses": 0, "points": 0} for name in participant_names}
        
        for m in matches:
            w1 = m.get('wrestler1')
            w2 = m.get('wrestler2')
            if w1 not in index_by_name or w2 not in index_by_name:
                continue
            
            i = index_by_name[w1]
            j = index_by_name[w2]
            
            s1 = int(m.get('score1', 0) or 0)
            s2 = int(m.get('score2', 0) or 0)
            completed = m.get('completed', False)
            winner = m.get('winner')
            
            if completed:
                if s1 > s2 or winner == w1:
                    results[i][j] = "1"
                    results[j][i] = "0"
                    stats[w1]["wins"] += 1
                    stats[w2]["losses"] += 1
                    stats[w1]["points"] += 1
                elif s2 > s1 or winner == w2:
                    results[i][j] = "0"
                    results[j][i] = "1"
                    stats[w2]["wins"] += 1
                    stats[w1]["losses"] += 1
                    stats[w2]["points"] += 1
                else:
                    results[i][j] = "0"
                    results[j][i] = "0"
        
        # Вычисляем места участников
        def calculate_place(name1, name2):
            """Сравнивает двух участников для определения места"""
            stats1 = stats.get(name1, {"wins": 0, "losses": 0, "points": 0})
            stats2 = stats.get(name2, {"wins": 0, "losses": 0, "points": 0})
            
            # Сначала по количеству побед
            if stats1["wins"] > stats2["wins"]:
                return -1
            elif stats1["wins"] < stats2["wins"]:
                return 1
            
            # Если одинаковое количество побед, проверяем личную встречу
            i1 = index_by_name.get(name1)
            i2 = index_by_name.get(name2)
            if i1 is not None and i2 is not None:
                head_to_head_1 = results[i1][i2]  # Результат name1 против name2
                head_to_head_2 = results[i2][i1]  # Результат name2 против name1
                if head_to_head_1 == "1":
                    return -1  # name1 победил name2
                elif head_to_head_2 == "1":
                    return 1   # name2 победил name1
            
            # Если личная встреча не состоялась или ничья, сортируем по очкам
            if stats1["points"] > stats2["points"]:
                return -1
            elif stats1["points"] < stats2["points"]:
                return 1
            
            # В крайнем случае - по алфавиту
            return -1 if name1 < name2 else 1
        
        # Сортируем участников по местам
        from functools import cmp_to_key
        sorted_names = sorted(participant_names, key=cmp_to_key(calculate_place))
        
        # Вычисляем места (с учетом одинаковых результатов)
        places = {}
        current_place = 1
        for idx, name in enumerate(sorted_names):
            if idx > 0:
                prev_name = sorted_names[idx - 1]
                prev_stats = stats.get(prev_name, {"wins": 0, "points": 0})
                curr_stats = stats.get(name, {"wins": 0, "points": 0})
                
                should_increment = False
                if prev_stats["wins"] != curr_stats["wins"]:
                    should_increment = True
                else:
                    i_prev = index_by_name.get(prev_name)
                    i_curr = index_by_name.get(name)
                    if i_prev is not None and i_curr is not None:
                        h2h_prev = results[i_prev][i_curr]
                        h2h_curr = results[i_curr][i_prev]
                        if h2h_prev == "1" or h2h_curr == "1":
                            should_increment = True
                        elif prev_stats["points"] != curr_stats["points"]:
                            should_increment = True
                
                if should_increment:
                    current_place = idx + 1
            
            places[name] = current_place
        
        # Создаем отсортированный список участников
        sorted_wrestlers = []
        for name in sorted_names:
            for w in wrestlers:
                if w.get('name') == name:
                    sorted_wrestlers.append(w)
                    break
        
        # Создаем таблицу NxN, где N = количество участников + 1 (для заголовков)
        self.table.setRowCount(num_wrestlers)
        self.table.setColumnCount(num_wrestlers + 5) # +5 для Место, Имя, Клуб, Очки, Сумма
       
        # Заголовки
        headers = ['Место', 'Имя', 'Клуб', 'Очки', 'Сумма']
        for i in range(num_wrestlers):
            headers.append(f"{i+1}")
        self.table.setHorizontalHeaderLabels(headers)
       
        # Заполняем данные участников в отсортированном порядке
        for i, wrestler in enumerate(sorted_wrestlers):
            name = wrestler.get('name', '')
            
            # Место
            place_item = QTableWidgetItem(str(places[name]))
            place_item.setTextAlignment(Qt.AlignCenter)
            place_font = QFont()
            place_font.setBold(True)
            place_item.setFont(place_font)
            self.table.setItem(i, 0, place_item)
            
            # Имя
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.UserRole, wrestler) # Сохраняем данные борца
            self.table.setItem(i, 1, name_item)
           
            # Клуб
            club_item = QTableWidgetItem(wrestler.get('club', ''))
            self.table.setItem(i, 2, club_item)
           
            # Очки
            st = stats.get(name, {"wins": 0, "losses": 0, "points": 0})
            points_item = QTableWidgetItem(str(st["wins"]))
            points_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, points_item)
           
            # Сумма (для круговой - количество побед)
            total_item = QTableWidgetItem(str(st["wins"]))
            total_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, total_item)
           
            # Заполняем матчи
            orig_idx = index_by_name[name]
            for j in range(num_wrestlers):
                if orig_idx == j:
                    # Диагональ - пустая
                    item = QTableWidgetItem('—')
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setBackground(QBrush(QColor(240, 240, 240)))
                    self.table.setItem(i, j + 5, item)
                else:
                    # Ищем матч между этими борцами
                    opp_name = participant_names[j]
                    match = self.find_match(matches, name, opp_name)
                    if match:
                        score1 = match.get('score1', '')
                        score2 = match.get('score2', '')
                        completed = match.get('completed', False)
                       
                        # Показываем результат в формате "1" или "0" для победителя
                        if completed:
                            if results[orig_idx][j] == "1":
                                display_text = "1"
                            elif results[j][orig_idx] == "1":
                                display_text = "0"
                            else:
                                display_text = "0"
                        else:
                            display_text = f"{score1}-{score2}" if score1 or score2 else ""
                        
                        item = QTableWidgetItem(display_text)
                        item.setTextAlignment(Qt.AlignCenter)
                       
                        # Сохраняем данные матча
                        item.setData(Qt.UserRole, {
                            'match_id': match.get('id'),
                            'wrestler1': match.get('wrestler1'),
                            'wrestler2': match.get('wrestler2'),
                            'score1': score1,
                            'score2': score2,
                            'completed': completed,
                            'category': list(self.tournament_data['categories'].keys())[0]
                        })
                       
                        # Если матч завершен - закрашиваем в #9ba6bd
                        if completed:
                            item.setBackground(QBrush(QColor(155, 166, 189))) # #9ba6bd
                    else:
                        item = QTableWidgetItem('')
                        item.setTextAlignment(Qt.AlignCenter)
                   
                    self.table.setItem(i, j + 5, item)
       
        # Настраиваем ширину столбцов
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
   
    def get_wrestler_name(self, wrestlers, index):
        """Получает имя борца по индексу"""
        if 0 <= index < len(wrestlers):
            return wrestlers[index].get('name', '')
        return ''
   
    def find_match(self, matches, wrestler1, wrestler2):
        """Ищет матч между двумя борцами"""
        for match in matches:
            if ((match.get('wrestler1') == wrestler1 and match.get('wrestler2') == wrestler2) or
                (match.get('wrestler1') == wrestler2 and match.get('wrestler2') == wrestler1)):
                return match
        return None
   
    def update_wrestler_points(self, wrestler_name, points):
        """Обновляет очки борца в таблице (аккумулирует сумму)"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)  # Столбец "Имя" теперь на позиции 1
            if item and item.text() == wrestler_name:
                points_item = self.table.item(row, 3)  # Столбец "Очки" теперь на позиции 3
                if points_item:
                    current_points = int(points_item.text()) if points_item.text() else 0
                    points_item.setText(str(current_points + points))
                break
   
    def update_total_points(self):
        """Обновляет сумму очков для каждого участника (сумма баллов)"""
        for row in range(self.table.rowCount()):
            total = 0
            # Суммируем очки из столбца "Очки" (столбец 3)
            points_item = self.table.item(row, 3)
            if points_item and points_item.text():
                total += int(points_item.text())
           
            total_item = self.table.item(row, 4)  # Столбец "Сумма" теперь на позиции 4
            if total_item:
                total_item.setText(str(total))
   
    def setup_olympic_bracket(self, category):
        """Настройка таблицы для олимпийской системы"""
        # Реализация для олимпийской системы
        matches = category.get('matches', [])
       
        # Определяем количество раундов
        max_round = max((m.get('round', 0) for m in matches), default=0)
       
        self.table.setRowCount(len(matches))
        self.table.setColumnCount(6) # Раунд, Борец 1, Счет 1, Счет 2, Борец 2, Статус
       
        headers = ['Раунд', 'Борец 1', 'Счет 1', 'Счет 2', 'Борец 2', 'Статус']
        self.table.setHorizontalHeaderLabels(headers)
       
        for i, match in enumerate(matches):
            # Раунд
            round_item = QTableWidgetItem(str(match.get('round', '')))
            self.table.setItem(i, 0, round_item)
           
            # Борец 1
            wrestler1_item = QTableWidgetItem(match.get('wrestler1', ''))
            self.table.setItem(i, 1, wrestler1_item)
           
            # Счет 1
            score1 = match.get('score1', '')
            score1_item = QTableWidgetItem(str(score1) if score1 != '' else '')
            score1_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, score1_item)
           
            # Счет 2
            score2 = match.get('score2', '')
            score2_item = QTableWidgetItem(str(score2) if score2 != '' else '')
            score2_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, score2_item)
           
            # Борец 2
            wrestler2_item = QTableWidgetItem(match.get('wrestler2', ''))
            self.table.setItem(i, 4, wrestler2_item)
           
            # Статус
            completed = match.get('completed', False)
            status_item = QTableWidgetItem('Завершен' if completed else 'Ожидается')
            status_item.setTextAlignment(Qt.AlignCenter)
           
            # Сохраняем данные матча
            match_data = {
                'match_id': match.get('id'),
                'wrestler1': match.get('wrestler1'),
                'wrestler2': match.get('wrestler2'),
                'score1': score1,
                'score2': score2,
                'completed': completed,
                'category': list(self.tournament_data['categories'].keys())[0]
            }
            # Сохраняем данные матча во все ячейки строки для удобства клика
            status_item.setData(Qt.UserRole, match_data)
            wrestler1_item.setData(Qt.UserRole, match_data)
            wrestler2_item.setData(Qt.UserRole, match_data)
            score1_item.setData(Qt.UserRole, match_data)
            score2_item.setData(Qt.UserRole, match_data)
            round_item.setData(Qt.UserRole, match_data)
           
            # Закрашиваем если завершен
            if completed:
                status_item.setBackground(QBrush(QColor(155, 166, 189))) # #9ba6bd
                wrestler1_item.setBackground(QBrush(QColor(155, 166, 189)))
                wrestler2_item.setBackground(QBrush(QColor(155, 166, 189)))
                score1_item.setBackground(QBrush(QColor(155, 166, 189)))
                score2_item.setBackground(QBrush(QColor(155, 166, 189)))
                round_item.setBackground(QBrush(QColor(155, 166, 189)))
               
                # Определяем победителя и начисляем баллы: 1 победителю, 0 проигравшему
                if score1 > score2:
                    winner = match.get('wrestler1')
                    self.update_wrestler_points_olympic(winner, 1)
                    self.update_wrestler_points_olympic(match.get('wrestler2'), 0)
                elif score2 > score1:
                    winner = match.get('wrestler2')
                    self.update_wrestler_points_olympic(winner, 1)
                    self.update_wrestler_points_olympic(match.get('wrestler1'), 0)
                else:
                    self.update_wrestler_points_olympic(match.get('wrestler1'), 0)
                    self.update_wrestler_points_olympic(match.get('wrestler2'), 0)
           
            self.table.setItem(i, 5, status_item)
       
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
   
    def update_wrestler_points_olympic(self, wrestler_name, points):
        """Обновляет очки борца в олимпийской системе (аккумулирует сумму)"""
        # Аналогично update_wrestler_points, но для олимпийской таблицы
        # Здесь можно добавить столбцы для очков, если их нет, или хранить в данных
        categories = self.tournament_data.get('categories', {})
        first_category = list(categories.keys())[0]
        category = categories[first_category]
        wrestlers = category.get('wrestlers', [])
        for wrestler in wrestlers:
            if wrestler.get('name') == wrestler_name:
                wrestler['points'] = wrestler.get('points', 0) + points
                break
   
    def load_match_from_bracket(self, row, column):
        """Загружает матч из сетки в панель управления"""
        if column < 4: # Не кликабельные столбцы
            return
           
        item = self.table.item(row, column)
        if not item:
            return
           
        match_data = item.data(Qt.UserRole)
        if not match_data:
            return
           
        # Если матч уже завершен, спрашиваем подтверждение
        if match_data.get('completed'):
            reply = QMessageBox.question(self, 'Загрузка матча',
                                        'Этот матч уже завершен. Загрузить его для редактирования?',
                                        QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return
       
        # Загружаем данные борцов
        category = self.tournament_data['categories'][match_data['category']]
        wrestler1_info = self.find_wrestler_info(category['wrestlers'], match_data['wrestler1'])
        wrestler2_info = self.find_wrestler_info(category['wrestlers'], match_data['wrestler2'])
       
        if wrestler1_info and wrestler2_info:
            # Загружаем в панель управления
            self.control_panel.set_match_competitors(
                {'name': wrestler1_info['name'], 'club': wrestler1_info.get('club', '')},
                {'name': wrestler2_info['name'], 'club': wrestler2_info.get('club', '')}
            )
           
            # Устанавливаем информацию о текущем матче
            self.control_panel.set_current_match_info(
                match_data['category'],
                match_data['wrestler1'],
                match_data['wrestler2'],
                match_data.get('match_id')
            )
           
            # Если матч уже был сыгран, загружаем счет
            if match_data.get('completed'):
                self.control_panel.red.points = match_data.get('score1', 0)
                self.control_panel.blue.points = match_data.get('score2', 0)
               
                # Определяем кто красный, кто синий
                if match_data['wrestler1'] == wrestler1_info['name']:
                    self.control_panel.red.points = match_data.get('score1', 0)
                    self.control_panel.blue.points = match_data.get('score2', 0)
                else:
                    self.control_panel.red.points = match_data.get('score2', 0)
                    self.control_panel.blue.points = match_data.get('score1', 0)
               
                self.control_panel.update_display()
   
    def find_wrestler_info(self, wrestlers, name):
        """Находит информацию о борце по имени"""
        for wrestler in wrestlers:
            if wrestler.get('name') == name:
                return wrestler
        return None
   
    def update_wrestlers_info_on_click(self, row, column):
        """Обновляет информацию о бойцах при клике на ячейку таблицы сетки"""
        try:
            # Определяем тип турнира
            categories = self.tournament_data.get('categories', {})
            if not categories:
                return
           
            first_category = list(categories.keys())[0]
            category = categories[first_category]
            is_round_robin = category.get('type') == 'round_robin'
           
            wrestler1_name = None
            wrestler2_name = None
            category_name = first_category
            match_data = None
           
            if is_round_robin:
                # Для круговой системы: кликабельные столбцы начинаются с 4
                if column < 4:
                    # Если клик по столбцам с информацией о борце, берем имя из этой строки
                    if column == 0: # Столбец "Имя"
                        name_item = self.table.item(row, 0)
                        if name_item:
                            wrestler_data = name_item.data(Qt.UserRole)
                            if wrestler_data:
                                wrestler1_name = wrestler_data.get('name', name_item.text())
                                wrestler1_info = wrestler_data
                                # Обновляем только одного борца
                                self.control_panel.red_name_edit.setText(wrestler1_info.get('name', ''))
                                self.control_panel.red_region_edit.setText(wrestler1_info.get('club', ''))
                                self.control_panel.red.name = wrestler1_info.get('name', 'КРАСНЫЙ')
                                self.control_panel.red.region = wrestler1_info.get('club', '')
                                self.control_panel.send_scoreboard_update()
                    return
               
                # Получаем имя первого борца из строки
                name_item = self.table.item(row, 0)
                if name_item:
                    wrestler1_data = name_item.data(Qt.UserRole)
                    if wrestler1_data:
                        wrestler1_name = wrestler1_data.get('name', name_item.text())
                    else:
                        wrestler1_name = name_item.text()
           
                # Получаем имя второго борца из заголовка столбца или из данных матча
                item = self.table.item(row, column)
                if item:
                    match_data = item.data(Qt.UserRole)
           
                if match_data:
                    # Если есть данные матча, используем их
                    wrestler1_name = match_data.get('wrestler1')
                    wrestler2_name = match_data.get('wrestler2')
                    category_name = match_data.get('category', first_category)
                else:
                    # Если матча еще нет, определяем второго борца по заголовку столбца
                    # Столбцы матчей начинаются с 4
                    header_item = self.table.horizontalHeaderItem(column)
                    if header_item:
                        # Заголовок может быть числом (индекс + 1) или именем
                        header_text = header_item.text()
                        try:
                            opponent_index = int(header_text) - 1
                            if 0 <= opponent_index < len(category.get('wrestlers', [])):
                                wrestler2_name = category['wrestlers'][opponent_index].get('name', '')
                        except ValueError:
                            # Если заголовок не число, пробуем найти по имени
                            for w in category.get('wrestlers', []):
                                if w.get('name') == header_text:
                                    wrestler2_name = header_text
                                    break
            else:
                # Для олимпийской системы: данные матча хранятся во всех ячейках строки
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    if item:
                        match_data = item.data(Qt.UserRole)
                        if match_data:
                            wrestler1_name = match_data.get('wrestler1')
                            wrestler2_name = match_data.get('wrestler2')
                            category_name = match_data.get('category', first_category)
                            break
           
            # Если не удалось определить борцов, выходим
            if not wrestler1_name or not wrestler2_name:
                return
           
            # Загружаем данные борцов
            category = self.tournament_data['categories'].get(category_name)
            if not category:
                return
           
            wrestler1_info = self.find_wrestler_info(category['wrestlers'], wrestler1_name)
            wrestler2_info = self.find_wrestler_info(category['wrestlers'], wrestler2_name)
           
            if wrestler1_info and wrestler2_info:
                # Обновляем информацию о бойцах в панели управления
                self.control_panel.red_name_edit.setText(wrestler1_info.get('name', ''))
                self.control_panel.red_region_edit.setText(wrestler1_info.get('club', ''))
                self.control_panel.blue_name_edit.setText(wrestler2_info.get('name', ''))
                self.control_panel.blue_region_edit.setText(wrestler2_info.get('club', ''))
               
                # Обновляем объекты борцов
                self.control_panel.red.name = wrestler1_info.get('name', 'КРАСНЫЙ')
                self.control_panel.red.region = wrestler1_info.get('club', '')
                self.control_panel.blue.name = wrestler2_info.get('name', 'СИНИЙ')
                self.control_panel.blue.region = wrestler2_info.get('club', '')
               
                # Устанавливаем информацию о текущем матче (если есть match_data)
                if match_data:
                    self.control_panel.set_current_match_info(
                        category_name,
                        wrestler1_name,
                        wrestler2_name,
                        match_data.get('match_id')
                    )
               
                # Отправляем обновление на табло
                self.control_panel.send_scoreboard_update()
        except Exception as e:
            print(f"Ошибка при обновлении информации о бойцах: {e}")
            import traceback
            traceback.print_exc()
   
    def setup_olympic_bracket(self, category):
        """Настройка таблицы для олимпийской системы"""
        # Реализация для олимпийской системы
        matches = category.get('matches', [])
       
        # Определяем количество раундов
        max_round = max((m.get('round', 0) for m in matches), default=0)
       
        self.table.setRowCount(len(matches))
        self.table.setColumnCount(6) # Раунд, Борец 1, Счет 1, Счет 2, Борец 2, Статус
       
        headers = ['Раунд', 'Борец 1', 'Счет 1', 'Счет 2', 'Борец 2', 'Статус']
        self.table.setHorizontalHeaderLabels(headers)
       
        for i, match in enumerate(matches):
            # Раунд
            round_item = QTableWidgetItem(str(match.get('round', '')))
            self.table.setItem(i, 0, round_item)
           
            # Борец 1
            wrestler1_item = QTableWidgetItem(match.get('wrestler1', ''))
            self.table.setItem(i, 1, wrestler1_item)
           
            # Счет 1
            score1 = match.get('score1', '')
            score1_item = QTableWidgetItem(str(score1) if score1 != '' else '')
            score1_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, score1_item)
           
            # Счет 2
            score2 = match.get('score2', '')
            score2_item = QTableWidgetItem(str(score2) if score2 != '' else '')
            score2_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, score2_item)
           
            # Борец 2
            wrestler2_item = QTableWidgetItem(match.get('wrestler2', ''))
            self.table.setItem(i, 4, wrestler2_item)
           
            # Статус
            completed = match.get('completed', False)
            status_item = QTableWidgetItem('Завершен' if completed else 'Ожидается')
            status_item.setTextAlignment(Qt.AlignCenter)
           
            # Сохраняем данные матча
            match_data = {
                'match_id': match.get('id'),
                'wrestler1': match.get('wrestler1'),
                'wrestler2': match.get('wrestler2'),
                'score1': score1,
                'score2': score2,
                'completed': completed,
                'category': list(self.tournament_data['categories'].keys())[0]
            }
            # Сохраняем данные матча во все ячейки строки для удобства клика
            status_item.setData(Qt.UserRole, match_data)
            wrestler1_item.setData(Qt.UserRole, match_data)
            wrestler2_item.setData(Qt.UserRole, match_data)
            score1_item.setData(Qt.UserRole, match_data)
            score2_item.setData(Qt.UserRole, match_data)
            round_item.setData(Qt.UserRole, match_data)
           
            # Закрашиваем если завершен
            if completed:
                status_item.setBackground(QBrush(QColor(155, 166, 189))) # #9ba6bd
               
                # Определяем победителя
                if score1 > score2:
                    winner = match.get('wrestler1')
                elif score2 > score1:
                    winner = match.get('wrestler2')
                else:
                    winner = None
               
                # Обновляем очки участников (для олимпийской системы - 1 за победу)
                if winner:
                    self.update_wrestler_points_olympic(winner, 1)
           
            self.table.setItem(i, 5, status_item)
       
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)


class InlineMatScheduleWidget(QWidget):
    """Компактное расписание ковра внутри панели управления."""

    def __init__(self, tournament_data, mat_number, parent=None):
        super().__init__(parent)
        self.tournament_data = tournament_data
        self.mat_number = mat_number
        self.table = None
        self._placeholder = QWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.title = QLabel("Расписание ковра")
        self.title.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.title)
        layout.addWidget(self._placeholder)
        self.update_data(tournament_data, mat_number)

    def update_data(self, tournament_data, mat_number):
        self.tournament_data = tournament_data
        self.mat_number = mat_number
        if not tournament_data or "schedule" not in tournament_data:
            if self.table:
                self.table.setRowCount(0)
            return

        mat_matches = filter_schedule_items(
            tournament_data.get("schedule", []), query="", mat_filter=mat_number
        )
        new_table = ScheduleWindow.build_schedule_table(
            mat_matches, [mat_number], on_double_click=None, parent=self
        )
        if self.table:
            self.layout().replaceWidget(self.table, new_table)
            self.table.setParent(None)
            self.table.deleteLater()
        else:
            self.layout().replaceWidget(self._placeholder, new_table)
            self._placeholder.setParent(None)
        self.table = new_table
class ControlPanel(QWidget):
    update_display_signal = pyqtSignal()
    
    def __init__(self, tournament_data, network_manager, mat_number, parent=None, is_secondary=False, schedule_sync=None):
        super().__init__(parent)
        self.red = Wrestler("Красный")
        self.blue = Wrestler("Синий")
        self.current_period = 1
        self.technical_superiority = 10
        self.settings = get_settings()
        self.period_base_duration = self.settings.get("timers", "period_duration", PERIOD_DURATION)
        self.break_base_duration = self.settings.get("timers", "break_duration", BREAK_DURATION)
        self.opponent_wait_duration = self.settings.get("timers", "opponent_wait_duration", 60)
        self.remaining_time = self.period_base_duration
        self.timer_running = False
        self.history = MatchHistory()
        self.winner = None
        self.tournament_date = None
        self.tournament_data = tournament_data
        self.network_manager = network_manager
        self.mat_number = mat_number  # Убедитесь, что этот атрибут установлен
        self.is_secondary = is_secondary
        self.schedule_sync = schedule_sync
        if self.schedule_sync:
            self.schedule_sync.update_mat_number(self.mat_number)
        # Информация о текущем матче в данных турнира
        self.current_match_category = None
        self.current_match_w1 = None
        self.current_match_w2 = None
        self.current_match_id = None
       
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)
       
        # Таймер перерыва
        self.break_timer = QTimer()
        self.break_timer.timeout.connect(self.update_break_timer)
        self.break_time_remaining = self.break_base_duration
        self.break_timer_running = False
        
        # Таймер ожидания соперника (обратный отсчет)
        self.opponent_wait_timer = QTimer()
        self.opponent_wait_timer.timeout.connect(self.update_opponent_wait_timer)
        self.opponent_wait_time_remaining = self.opponent_wait_duration
        self.opponent_wait_timer_running = False
        self.opponent_wait_duration = self.opponent_wait_duration  # Длительность таймера (для сброса)
        # Сохраняем отредактированное время для каждого периода
        self.period_times = {1: self.period_base_duration, 2: self.period_base_duration, 3: self.period_base_duration}
       
        # Таймер для постоянной отправки данных на табло
        self.scoreboard_update_timer = QTimer()
        self.scoreboard_update_timer.timeout.connect(self.send_scoreboard_update)
        self.scoreboard_update_timer.start(500)  # Отправляем обновления каждые 500 мс
        self.setup_ui()
       
        # Регистрация обработчиков сетевых сообщений
        if self.network_manager:
            self.network_manager.register_handler('match_control', self.handle_match_control)
        
        # Горячие клавиши
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo_action)
        QShortcut(QKeySequence("Ctrl+Space"), self, self.add_point_shortcut)
        
        # Устанавливаем фокус для обработки клавиш
        self.setFocusPolicy(Qt.StrongFocus)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)  # Добавляем отступы для предотвращения съезжания UI
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
       
        # Индикатор режима
        if self.is_secondary:
            mode_label = QLabel("РЕЖИМ: ВТОРОЙ ПК (УПРАВЛЕНИЕ СХВАТКОЙ)")
            mode_label.setStyleSheet("font-size: 16px; font-weight: bold; background-color: #FFA500; color: black; padding: 10px; text-align: center;")
            layout.addWidget(mode_label)
       
        # Управление турниром (только для основного ПК)
        # if not self.is_secondary:
            # tournament_group = QGroupBox("Управление турниром")
            # tournament_layout = QHBoxLayout(tournament_group)
        #    
            # schedule_btn = QPushButton("Показать расписание")
            # schedule_btn.clicked.connect(self.show_schedule)
            # tournament_layout.addWidget(schedule_btn)
        #    
            # show_scoreboard_btn = QPushButton("Показать табло")
            # show_scoreboard_btn.clicked.connect(self.show_scoreboard)
            # show_scoreboard_btn.setStyleSheet("background-color: #FFFFCC; font-weight: bold;")
            # tournament_layout.addWidget(show_scoreboard_btn)
        #    
            # layout.addWidget(tournament_group)
       
        # Управление временем
        time_group = QGroupBox("Управление временем")
        time_layout = QHBoxLayout(time_group)
       
        self.start_btn = QPushButton("СТАРТ")
        self.start_btn.clicked.connect(self.start_timer)
        self.start_btn.setStyleSheet("font-size: 16px; font-weight: bold; background-color: #90EE90;")
        time_layout.addWidget(self.start_btn)
       
        self.pause_btn = QPushButton("ПАУЗА")
        self.pause_btn.clicked.connect(self.pause_timer)
        self.pause_btn.setStyleSheet("font-size: 16px; font-weight: bold; background-color: #FFB6C1;")
        time_layout.addWidget(self.pause_btn)
       
        reset_btn = QPushButton("Сброс периода")
        reset_btn.clicked.connect(self.reset_period)
        time_layout.addWidget(reset_btn)
       
        next_period_btn = QPushButton("Следующий период")
        next_period_btn.clicked.connect(self.next_period)
        time_layout.addWidget(next_period_btn)
       
        full_reset_btn = QPushButton("СБРОС")
        full_reset_btn.setStyleSheet("font-size: 16px; font-weight: bold; background-color: #FFD700;")
        full_reset_btn.clicked.connect(self.reset_all_data)
        time_layout.addWidget(full_reset_btn)
       
        # Отображение времени
        self.current_time_label = QLabel("03:00")
        self.current_time_label.setStyleSheet("font-size: 20px; font-weight: bold; padding: 5px;")
        time_layout.addWidget(self.current_time_label)
       
        
        self.period_label = QLabel("Период: 1")
        self.period_label.setStyleSheet("font-size: 16px; padding: 5px;")
        time_layout.addWidget(self.period_label)
       
        # Управление таймером перерыва
        break_group = QGroupBox("Таймер перерыва")
        break_layout = QHBoxLayout(break_group)
       
        self.break_start_btn = QPushButton("СТАРТ ПЕРЕРЫВА")
        self.break_start_btn.clicked.connect(self.start_break_timer)
        self.break_start_btn.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #90EE90;")
        break_layout.addWidget(self.break_start_btn)
       
        self.break_pause_btn = QPushButton("ПАУЗА ПЕРЕРЫВА")
        self.break_pause_btn.clicked.connect(self.pause_break_timer)
        self.break_pause_btn.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #FFB6C1;")
        self.break_pause_btn.setEnabled(False)
        break_layout.addWidget(self.break_pause_btn)
       
        self.break_time_label = QLabel(f"{self.break_base_duration // 60:02d}:{self.break_base_duration % 60:02d}")
        self.break_time_label.setStyleSheet("font-size: 18px; font-weight: bold; padding: 5px;")
        break_layout.addWidget(self.break_time_label)
        self.break_toggle_btn = QPushButton("ВКЛ")
        self.break_toggle_btn.clicked.connect(self.toggle_break_timer)
        self.break_toggle_btn.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #87CEEB;")
        break_layout.addWidget(self.break_toggle_btn)
        break_layout.addStretch()
       
        # Таймер ожидания соперника
        opponent_wait_group = QGroupBox("Таймер ожидания соперника")
        opponent_wait_layout = QHBoxLayout(opponent_wait_group)
        
        self.opponent_wait_start_btn = QPushButton("СТАРТ")
        self.opponent_wait_start_btn.clicked.connect(self.start_opponent_wait_timer)
        self.opponent_wait_start_btn.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #90EE90;")
        opponent_wait_layout.addWidget(self.opponent_wait_start_btn)
        
        self.opponent_wait_pause_btn = QPushButton("ПАУЗА")
        self.opponent_wait_pause_btn.clicked.connect(self.pause_opponent_wait_timer)
        self.opponent_wait_pause_btn.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #FFB6C1;")
        self.opponent_wait_pause_btn.setEnabled(False)
        opponent_wait_layout.addWidget(self.opponent_wait_pause_btn)
        
        self.opponent_wait_time_label = QLabel(f"{self.opponent_wait_duration // 60:02d}:{self.opponent_wait_duration % 60:02d}")
        self.opponent_wait_time_label.setStyleSheet("font-size: 18px; font-weight: bold; padding: 5px;")
        opponent_wait_layout.addWidget(self.opponent_wait_time_label)
        
        reset_wait_btn = QPushButton("Сброс")
        reset_wait_btn.clicked.connect(self.reset_opponent_wait_timer)
        opponent_wait_layout.addWidget(reset_wait_btn)
        
        opponent_wait_layout.addStretch()
       
        timers_row = QHBoxLayout()
        timers_row.addWidget(time_group)
        timers_row.addWidget(break_group)
        timers_row.addWidget(opponent_wait_group)
        layout.addLayout(timers_row)

        # Встроенное расписание ковра
        schedule_toggle_row = QHBoxLayout()
        self.schedule_toggle_btn = QPushButton("Показать расписание ковра")
        self.schedule_toggle_btn.setCheckable(True)
        self.schedule_toggle_btn.toggled.connect(self.toggle_inline_schedule)
        schedule_toggle_row.addWidget(self.schedule_toggle_btn)
        schedule_toggle_row.addStretch()
        layout.addLayout(schedule_toggle_row)

        self.inline_schedule_widget = InlineMatScheduleWidget(self.tournament_data, self.mat_number)
        self.inline_schedule_widget.setVisible(False)
        layout.addWidget(self.inline_schedule_widget)

        # Настройки матча
        tech_sup_group = QGroupBox("Настройки матча")
        tech_sup_layout = QHBoxLayout(tech_sup_group)
        tech_sup_layout.addWidget(QLabel("Техн. превосходство:"))
        self.tech_sup_edit = QLineEdit("10")
        self.tech_sup_edit.setValidator(QIntValidator(1, 100))
        self.tech_sup_edit.setMaximumWidth(60)
        self.tech_sup_edit.editingFinished.connect(self.update_technical_superiority)
        tech_sup_layout.addWidget(self.tech_sup_edit)
        layout.addWidget(tech_sup_group)
        self.opponent_wait_group = opponent_wait_group
        
        # Применяем настройки видимости таймера ожидания
        self.apply_settings_visibility()
       
        # Разделение на половины для управления
        splitter = QSplitter(Qt.Horizontal)
        splitter.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
        layout.addWidget(splitter)
       
        # Левая половина - Красный
        red_group = QGroupBox("Управление КРАСНЫМ")
        red_group.setStyleSheet("QGroupBox { background-color: #FFE0E0; }")
        red_group.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
        red_layout = QVBoxLayout(red_group)
       
        # Информация о красном борце
        red_info_layout = QVBoxLayout()
        red_info_layout.setSpacing(5)
        red_info_label = QLabel("Красный борец:")
        red_info_layout.addWidget(red_info_label)
        self.red_name_edit = QLineEdit()
        self.red_name_edit.setPlaceholderText("Имя красного борца")
        self.red_name_edit.setMinimumHeight(30)
        self.red_name_edit.setMaximumHeight(30)
        self.red_name_edit.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.red_name_edit.textChanged.connect(self.live_update_red)
        red_info_layout.addWidget(self.red_name_edit)
       
        red_region_label = QLabel("Регион/Клуб/Тренер:")
        red_info_layout.addWidget(red_region_label)
        self.red_region_edit = QLineEdit()
        self.red_region_edit.setPlaceholderText("Регион, клуб или тренер")
        self.red_region_edit.setMinimumHeight(30)
        self.red_region_edit.setMaximumHeight(30)
        self.red_region_edit.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.red_region_edit.textChanged.connect(self.live_update_red)
        red_info_layout.addWidget(self.red_region_edit)
       
        update_red_btn = QPushButton("Обновить")
        update_red_btn.clicked.connect(self.update_names)
        red_info_layout.addWidget(update_red_btn)
       
        red_layout.addLayout(red_info_layout)
       
        # Набор очков для красного
        red_scoring_layout = QGridLayout()
       
        red_buttons = [
            ("1", lambda: self.add_points(self.red, 1, "1 очко"), 0, 0),
            ("2", lambda: self.add_points(self.red, 2, "2 очка"), 0, 1),
            ("3", lambda: self.add_points(self.red, 3, "3 очка"), 0, 2),
            ("4", lambda: self.add_points(self.red, 4, "4 очка"), 1, 0),
            ("ПРЕДУПРЕЖДЕНИЕ", lambda: self.add_caution(self.red, "Предупреждение"), 1, 1),
            ("ПАССИВНОСТЬ", lambda: self.add_passivity(self.red, "Пассивность"), 1, 2)
        ]
       
        self.red_caution_btn = None
        self.red_passivity_btn = None
        for text, slot, row, col in red_buttons:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #ffcccc;
                    color: black;
                    font-weight: bold;
                    padding: 5px;
                    border: 2px solid #cc0000;
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background-color: #ffaaaa;
                }
            """)
            btn.setMinimumHeight(30)
            red_scoring_layout.addWidget(btn, row, col)
            if text == "ПРЕДУПРЕЖДЕНИЕ":
                self.red_caution_btn = btn
            elif text == "ПАССИВНОСТЬ":
                self.red_passivity_btn = btn
       
        red_layout.addLayout(red_scoring_layout)
       
        # История красного
        red_history_label = QLabel("История действий КРАСНОГО:")
        red_history_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        red_layout.addWidget(red_history_label)
       
        self.red_history_text = QTextEdit()
        self.red_history_text.setMaximumHeight(150)
        self.red_history_text.setStyleSheet("background-color: #f8f8f8; color: black;")
        red_layout.addWidget(self.red_history_text)
       
        splitter.addWidget(red_group)
       
        # Правая половина - Синий
        blue_group = QGroupBox("Управление СИНИМ")
        blue_group.setStyleSheet("QGroupBox { background-color: #E0E0FF; }")
        blue_group.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
        blue_layout = QVBoxLayout(blue_group)

        # Информация о синем борце
        blue_info_layout = QVBoxLayout()
        blue_info_layout.setSpacing(5)

        blue_info_label = QLabel("Синий борец:")
        blue_info_layout.addWidget(blue_info_label)

        self.blue_name_edit = QLineEdit()
        self.blue_name_edit.setPlaceholderText("Имя синего борца")
        self.blue_name_edit.setMinimumHeight(30)
        self.blue_name_edit.setMaximumHeight(30)
        self.blue_name_edit.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.blue_name_edit.textChanged.connect(self.live_update_blue)
        blue_info_layout.addWidget(self.blue_name_edit)

        blue_region_label = QLabel("Регион/Клуб/Тренер:")
        blue_info_layout.addWidget(blue_region_label)

        self.blue_region_edit = QLineEdit()
        self.blue_region_edit.setPlaceholderText("Регион, клуб или тренер")
        self.blue_region_edit.setMinimumHeight(30)
        self.blue_region_edit.setMaximumHeight(30)
        self.blue_region_edit.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.blue_region_edit.textChanged.connect(self.live_update_blue)
        blue_info_layout.addWidget(self.blue_region_edit)

        update_blue_btn = QPushButton("Обновить")
        update_blue_btn.clicked.connect(self.update_names)
        blue_info_layout.addWidget(update_blue_btn)

        blue_layout.addLayout(blue_info_layout)

        # Набор очков для синего
        blue_scoring_layout = QGridLayout()

        blue_buttons = [
            ("1", lambda: self.add_points(self.blue, 1, "1 очко"), 0, 0),
            ("2", lambda: self.add_points(self.blue, 2, "2 очка"), 0, 1),
            ("3", lambda: self.add_points(self.blue, 3, "3 очка"), 0, 2),
            ("4", lambda: self.add_points(self.blue, 4, "4 очка"), 1, 0),
            ("ПРЕДУПРЕЖДЕНИЕ", lambda: self.add_caution(self.blue, "Предупреждение"), 1, 1),
            ("ПАССИВНОСТЬ", lambda: self.add_passivity(self.blue, "Пассивность"), 1, 2)
        ]

        self.blue_caution_btn = None
        self.blue_passivity_btn = None

        for text, slot, row, col in blue_buttons:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #ccccff;
                    color: black;
                    font-weight: bold;
                    padding: 5px;
                    border: 2px solid #0000cc;
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background-color: #aaaaff;
                }
            """)
            btn.setMinimumHeight(30)
            blue_scoring_layout.addWidget(btn, row, col)

            if text == "ПРЕДУПРЕЖДЕНИЕ":
                self.blue_caution_btn = btn
            elif text == "ПАССИВНОСТЬ":
                self.blue_passivity_btn = btn

        # Применяем настройки видимости кнопок
        self.apply_settings_visibility()

        blue_layout.addLayout(blue_scoring_layout)

        # История синего
        blue_history_label = QLabel("История действий СИНЕГО:")
        blue_history_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        blue_layout.addWidget(blue_history_label)

        self.blue_history_text = QTextEdit()
        self.blue_history_text.setMaximumHeight(150)
        self.blue_history_text.setStyleSheet("background-color: #f8f8f8; color: black;")
        blue_layout.addWidget(self.blue_history_text)

        splitter.addWidget(blue_group)

       
        # Установка равных размеров для разделенных панелей
        splitter.setSizes([600, 600])
       
        # Управление матчем
        match_group = QGroupBox("Управление матчем")
        match_layout = QHBoxLayout(match_group)
        # Кнопка: Открыть табло на втором экране
        show_scoreboard_btn = QPushButton("ТАБЛО НА 2-Й ЭКРАН")
        show_scoreboard_btn.setStyleSheet("background-color: #00FF00; color: black; font-weight: bold; font-size: 14px;")
        show_scoreboard_btn.setMinimumHeight(50)
        show_scoreboard_btn.clicked.connect(self.open_external_scoreboard)
        match_layout.addWidget(show_scoreboard_btn)
        undo_btn = QPushButton("ОТМЕНИТЬ")
        undo_btn.clicked.connect(self.undo_action)
        undo_btn.setStyleSheet("background-color: #FFFFCC; font-weight: bold;")
        match_layout.addWidget(undo_btn)
        fall_red_btn = QPushButton("ТУШЕ КРАСНЫЙ")
        fall_red_btn.clicked.connect(lambda: self.end_match("ТУШЕ Красным"))
        fall_red_btn.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold;")
        match_layout.addWidget(fall_red_btn)
        fall_blue_btn = QPushButton("ТУШЕ СИНИЙ")
        fall_blue_btn.clicked.connect(lambda: self.end_match("ТУШЕ Синим"))
        fall_blue_btn.setStyleSheet("background-color: #4444ff; color: white; font-weight: bold;")
        match_layout.addWidget(fall_blue_btn)
        load_next_btn = QPushButton("📋 Загрузить следующий матч")
        load_next_btn.clicked.connect(self.load_next_match)
        load_next_btn.setStyleSheet("background-color: #90EE90; font-weight: bold;")
        match_layout.addWidget(load_next_btn)
       
        layout.addWidget(match_group)
       
        # Файлы (только для основного ПК)
        if not self.is_secondary:
            files_group = QGroupBox("Файлы")
            files_layout = QHBoxLayout(files_group)
           
            save_btn = QPushButton("💾 Сохранить матч")
            save_btn.clicked.connect(self.save_match)
            save_btn.setStyleSheet("background-color: #90EE90; font-weight: bold;")
            files_layout.addWidget(save_btn)
           
            load_btn = QPushButton("📂 Загрузить матч")
            load_btn.clicked.connect(self.load_match)
            load_btn.setStyleSheet("background-color: #87CEEB; font-weight: bold;")
            files_layout.addWidget(load_btn)
           
            layout.addWidget(files_group)

    def update_technical_superiority(self):
        try:
            self.technical_superiority = int(self.tech_sup_edit.text())
        except:
            self.technical_superiority = 10
            self.tech_sup_edit.setText("10")

    def check_technical_superiority(self):
        diff = abs(self.red.points - self.blue.points)
        if diff >= self.technical_superiority:
            winner = self.red if self.red.points > self.blue.points else self.blue
            self.end_match(f"Техническое превосходство {winner.color}")

    def open_external_scoreboard(self):
        main_window = self.window()
        if not hasattr(main_window, 'external_scoreboard') or main_window.external_scoreboard is None:
            scoreboard = ScoreboardWindow(self.network_manager, main_window)
            main_window.external_scoreboard = scoreboard
            # === КРИТИЧНО: Очищаем ссылку при закрытии ===
            def on_close():
                main_window.external_scoreboard = None
                print("[ТАБЛО 2] Окно закрыто и очищено")
            scoreboard.closed.connect(on_close)
            scoreboard.destroyed.connect(on_close)
            scoreboard.show()
            QMessageBox.information(self, "Табло", "Табло открыто на втором экране")
        else:
            main_window.external_scoreboard.activateWindow()
            main_window.external_scoreboard.raise_()

    def send_scoreboard_update(self):
        """Безопасная отправка данных на табло - вызывается постоянно"""
        if not hasattr(self, 'red') or not hasattr(self, 'blue'):
            return
        if not self.network_manager:
            return
        
        # ЗАЩИТА: Проверяем, что это панель управления для реального ковра (mat > 0)
        if self.mat_number <= 0:
            return
        
        # ЗАЩИТА: Проверяем, что имена не пустые
        red_name = getattr(self.red, 'name', 'КРАСНЫЙ')
        blue_name = getattr(self.blue, 'name', 'СИНИЙ')
        
        if red_name.strip() == '' or blue_name.strip() == '':
            # Если имена пустые, используем значения по умолчанию
            red_name = 'КРАСНЫЙ' if red_name.strip() == '' else red_name
            blue_name = 'СИНИЙ' if blue_name.strip() == '' else blue_name

        # Если регионы пока пустые, пробуем подтянуть их из данных турнира
        # (это гарантирует корректную загрузку Регион/Клуб/Тренер уже при первом клике).
        if self.tournament_data and self.current_match_category:
            try:
                cat = self.tournament_data.get('categories', {}).get(self.current_match_category, {})
                participants = cat.get('participants', []) or cat.get('wrestlers', [])
                global_participants = self.tournament_data.get('participants', [])

                def find_club(name: str) -> str:
                    for p in participants:
                        if p.get('name') == name:
                            return p.get('club', '')
                    for p in global_participants:
                        if p.get('name') == name:
                            return p.get('club', '')
                    return ''

                if not getattr(self.red, 'region', '').strip():
                    self.red.region = find_club(red_name)
                if not getattr(self.blue, 'region', '').strip():
                    self.blue.region = find_club(blue_name)
            except Exception as e:
                print(f"[ТУРНИР] Ошибка при попытке подтянуть клубы из данных турнира: {e}")
        
        # Если идет перерыв, показываем время перерыва, иначе время периода
        if getattr(self, 'break_timer_running', False):
            time_remaining = getattr(self, 'break_time_remaining', self.break_base_duration)
            period = getattr(self, 'current_period', 1) # Показываем текущий период, но время - перерыва
            is_break = True
        else:
            time_remaining = getattr(self, 'remaining_time', self.period_base_duration)
            period = getattr(self, 'current_period', 1)
            is_break = False
        
        # Убедимся, что time_remaining - целое число
        try:
            time_remaining = int(time_remaining)
        except:
            time_remaining = self.period_base_duration
        
        data = {
            'type': 'scoreboard_update',
            'mat': self.mat_number,
            'red': {
                'name': red_name,
                'region': getattr(self.red, 'region', ''),
                'points': getattr(self.red, 'points', 0),
                'cautions': getattr(self.red, 'cautions', 0),
                'passivity': getattr(self.red, 'passivity', 0)
            },
            'blue': {
                'name': blue_name,
                'region': getattr(self.blue, 'region', ''),
                'points': getattr(self.blue, 'points', 0),
                'cautions': getattr(self.blue, 'cautions', 0),
                'passivity': getattr(self.blue, 'passivity', 0)
            },
            'period': period,
            'time_remaining': time_remaining,
            'is_break': is_break,
            'break_time_remaining': getattr(self, 'break_time_remaining', 0) if is_break else 0,
            # Название категории для отображения на табло
            'category': self.current_match_category or "",
            # Таймер ожидания соперника (оставшееся время)
            'opponent_wait_time': getattr(self, 'opponent_wait_time_remaining', 0) if self.settings.get_scoreboard_setting("show_opponent_wait_timer") else 0
        }
    
        # === 1. Отправляем в сеть (для вкладки "Табло") ===
        try:
            self.network_manager.send_message('scoreboard_update', data)
        except Exception as e:
            print(f"[ОШИБКА] Не удалось отправить в сеть: {e}")
        
        # === 2. Отправляем напрямую в открытое внешнее табло ===
        main_window = self.window()
        if hasattr(main_window, 'external_scoreboard') and main_window.external_scoreboard:
            try:
                main_window.external_scoreboard.handle_scoreboard_update({'data': data})
            except Exception as e:
                print(f"[ОШИБКА] Не удалось обновить внешнее табло: {e}")
   
    def handle_match_control(self, message, client_socket):
        """Обработка команд управления матчем из сети"""
        if self.is_secondary:
            return # Второстепенный ПК не обрабатывает команды управления
           
        data = message['data']
        command = data['command']
       
        if command == 'start_timer':
            self.start_timer()
        elif command == 'pause_timer':
            self.pause_timer()
        elif command == 'reset_period':
            self.reset_period()
        elif command == 'next_period':
            self.next_period()
        elif command == 'add_points':
            wrestler = self.red if data['wrestler'] == 'red' else self.blue
            self.add_points(wrestler, data['points'], data['description'])
        elif command == 'add_caution':
            wrestler = self.red if data['wrestler'] == 'red' else self.blue
            self.add_caution(wrestler, data['description'])
        elif command == 'add_passivity':
            wrestler = self.red if data['wrestler'] == 'red' else self.blue
            self.add_passivity(wrestler, data['description'])
        elif command == 'end_match':
            self.end_match(data['reason'])
        elif command == 'undo_action':
            self.undo_action()
   
    def send_match_control(self, command, **kwargs):
        """Отправка команды управления матчем в сеть"""
        if self.network_manager and self.is_secondary:
            data = {'command': command, **kwargs}
            self.network_manager.send_message('match_control', data)
   
    def show_scoreboard(self):
        """Открывает или активирует вкладку табло"""
        main_window = self.window()
        if hasattr(main_window, 'open_scoreboard_tab'):
            main_window.open_scoreboard_tab()
   
    def show_schedule(self):
        if not self.tournament_data:
            QMessageBox.warning(self, "Внимание", "Сначала загрузите турнир")
            return
       
        main_window = self.window()
        if hasattr(main_window, 'open_schedule_tab'):
            main_window.open_schedule_tab()
   
    def set_match_competitors(self, wrestler1, wrestler2):
        """
        Установка борцов для текущей схватки (вызывается из менеджера турнира/сетки).
        Поле «Регион/Клуб/Тренер» на табло берётся из ключа `club` данных турнира.
        """
        print(f"[DEBUG] set_match_competitors вызван: {wrestler1} vs {wrestler2}")

        # Получаем данные, проверяя разные возможные ключи
        red_name = wrestler1.get('name', 'КРАСНЫЙ')
        red_region = wrestler1.get('club', '') or wrestler1.get('region', '') or wrestler1.get('тренер', '')
        blue_name = wrestler2.get('name', 'СИНИЙ')
        blue_region = wrestler2.get('club', '') or wrestler2.get('region', '') or wrestler2.get('тренер', '')
        
        # Устанавливаем значения в объекты борцов
        self.red.name = red_name
        self.red.region = red_region
        self.blue.name = blue_name
        self.blue.region = blue_region
    
        # Временно отключаем сигналы, чтобы избежать циклических обновлений
        self.red_name_edit.blockSignals(True)
        self.red_region_edit.blockSignals(True)
        self.blue_name_edit.blockSignals(True)
        self.blue_region_edit.blockSignals(True)
        
        # Устанавливаем текст в поля редактирования
        self.red_name_edit.setText(self.red.name)
        self.red_region_edit.setText(self.red.region)
        self.blue_name_edit.setText(self.blue.name)
        self.blue_region_edit.setText(self.blue.region)
        
        # Включаем сигналы обратно
        self.red_name_edit.blockSignals(False)
        self.red_region_edit.blockSignals(False)
        self.blue_name_edit.blockSignals(False)
        self.blue_region_edit.blockSignals(False)
        
        # Убеждаемся, что значения сохранены в объектах (на случай, если сигналы все же сработали)
        self.red.name = red_name
        self.red.region = red_region
        self.blue.name = blue_name
        self.blue.region = blue_region
    
        # Сброс очков при загрузке
        self.red.points = 0
        self.blue.points = 0
        self.red.cautions = 0
        self.blue.cautions = 0
        self.red.passivity = 0
        self.blue.passivity = 0
        self.current_period = 1

        # Время периода берется из настроек
        self.remaining_time = self.period_base_duration
        for period in range(1, PERIODS + 1):
            self.period_times[period] = self.period_base_duration
    
        # Обновляем локальный интерфейс
        self.update_display()
    
        # Немедленная отправка на табло
        self.send_scoreboard_update()

    def set_current_match_info(self, category_name, wrestler1_name, wrestler2_name, match_id=None):
        """Запоминает, какой именно матч из турнирных данных сейчас проводится."""
        self.current_match_category = category_name
        self.current_match_w1 = wrestler1_name
        self.current_match_w2 = wrestler2_name
        self.current_match_id = match_id
   
    def live_update_red(self):
        """Мгновенное обновление данных красного борца при редактировании полей"""
        self.red.name = self.red_name_edit.text().strip() or "КРАСНЫЙ"
        self.red.region = self.red_region_edit.text().strip()
        self.send_scoreboard_update() # ← мгновенно отправляем на табло

    def live_update_blue(self):
        """Мгновенное обновление данных синего борца при редактировании полей"""
        self.blue.name = self.blue_name_edit.text().strip() or "СИНИЙ"
        self.blue.region = self.blue_region_edit.text().strip()
        self.send_scoreboard_update() # ← мгновенно отправляем на табло
   
    def update_names(self):
        self.red.name = self.red_name_edit.text() or "КРАСНЫЙ"
        self.red.region = self.red_region_edit.text()
        self.blue.name = self.blue_name_edit.text() or "СИНИЙ"
        self.blue.region = self.blue_region_edit.text()
        self.update_display()
        # Немедленная отправка на табло при изменении имен
        self.send_scoreboard_update()
   
    def start_timer(self):
        self.send_scoreboard_update()
        if self.is_secondary or not self.window().is_secondary:
            self.open_external_scoreboard()
        if not self.timer_running:
            self.timer_running = True
            self.timer.start(1000)
            self.start_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            if self.is_secondary:
                self.send_match_control('start_timer')
   
    def pause_timer(self):
        self.timer_running = False
        self.timer.stop()
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        if self.is_secondary:
            self.send_match_control('pause_timer')
   
    def reset_period(self):
        # Используем сохраненное время для текущего периода, если есть, иначе базовое из настроек
        saved_time = self.period_times.get(self.current_period)
        if saved_time is not None:
            self.remaining_time = saved_time
        else:
            self.remaining_time = self.period_base_duration
            self.period_times[self.current_period] = self.period_base_duration
       
        # Обновляем отображение времени
        minutes = self.remaining_time // 60
        secs = self.remaining_time % 60
        self.current_time_label.setText(f"{minutes:02d}:{secs:02d}")
        self.update_display()
        # Немедленная отправка на табло
        self.send_scoreboard_update()
        if self.is_secondary:
            self.send_match_control('reset_period')
    
    def next_period(self):
        """Переходит к следующему периоду через перерыв"""
        if self.current_period < PERIODS:
            # Останавливаем таймер периода, если он работает
            self.pause_timer()
           
            # Сохраняем текущее отредактированное время для предыдущего периода
            self.period_times[self.current_period] = self.remaining_time
           
            # Запускаем таймер перерыва
            self.break_time_remaining = self.break_base_duration
            self.break_timer_running = True
            self.break_timer.start(1000)
            self.break_start_btn.setEnabled(False)
            self.break_pause_btn.setEnabled(True)
            self.break_toggle_btn.setText("ВЫКЛ")
            self.break_toggle_btn.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #FF6B6B;")
           
            # Обновляем отображение перерыва
            self.update_display()
            self.send_scoreboard_update()
           
            if self.is_secondary:
                self.send_match_control('next_period')
   
    def update_timer(self):
        if self.remaining_time > 0:
            self.remaining_time -= 1
            minutes = self.remaining_time // 60
            seconds = self.remaining_time % 60
            self.current_time_label.setText(f"{minutes:02d}:{seconds:02d}")
            self.period_label.setText(f"Период: {self.current_period}")
            if self.remaining_time == 30:
                winsound.Beep(1000, 500)
            elif self.remaining_time == 10:
                winsound.Beep(1000, 200)
                winsound.Beep(1000, 200)
            elif self.remaining_time == 0:
                winsound.Beep(2000, 1000)
                self.pause_timer()
                if self.current_period < PERIODS:
                    # Автоматически запускаем перерыв между периодами
                    self.next_period()
                else:
                    self.determine_winner()
            # Обновляем отображение и отправляем на табло
            self.update_display()
            self.send_scoreboard_update()
   
    def start_break_timer(self):
        """Запускает таймер перерыва"""
        if not self.break_timer_running:
            self.break_timer_running = True
            self.break_timer.start(1000)
            self.break_start_btn.setEnabled(False)
            self.break_pause_btn.setEnabled(True)
            if self.is_secondary:
                self.send_match_control('start_break_timer')
   
    def pause_break_timer(self):
        """Останавливает таймер перерыва"""
        self.break_timer_running = False
        self.break_timer.stop()
        self.break_start_btn.setEnabled(True)
        self.break_pause_btn.setEnabled(False)
        if self.is_secondary:
            self.send_match_control('pause_break_timer')
   
    def toggle_break_timer(self):
        """Включает/выключает таймер перерыва"""
        if self.break_timer_running:
            self.pause_break_timer()
            self.break_toggle_btn.setText("ВКЛ")
            self.break_toggle_btn.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #87CEEB;")
        else:
            self.start_break_timer()
            self.break_toggle_btn.setText("ВЫКЛ")
            self.break_toggle_btn.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #FF6B6B;")
   
    def update_break_timer(self):
        """Обновляет таймер перерыва"""
        if self.break_time_remaining > 0:
            self.break_time_remaining -= 1
            minutes = self.break_time_remaining // 60
            seconds = self.break_time_remaining % 60
            self.break_time_label.setText(f"{minutes:02d}:{seconds:02d}")
           
            # Обновляем табло с информацией о перерыве
            self.send_scoreboard_update()
           
            if self.break_time_remaining == 0:
                winsound.Beep(2000, 1000)
                self.pause_break_timer()
                self.break_toggle_btn.setText("ВКЛ")
                self.break_toggle_btn.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #87CEEB;")
               
                # Автоматически переходим к следующему периоду
                if self.current_period < PERIODS:
                    self.current_period += 1
                    self.remaining_time = self.period_times.get(self.current_period, self.period_base_duration)
                   
                    # Обновляем таймер времени для нового периода
                    minutes = self.remaining_time // 60
                    secs = self.remaining_time % 60
                    self.current_time_label.setText(f"{minutes:02d}:{secs:02d}")
                    self.period_label.setText(f"Период: {self.current_period}")
                   
                    # Обновляем отображение
                    self.update_display()
                    self.send_scoreboard_update()
   
    def add_points(self, wrestler, points, description):
        wrestler.points += points
        wrestler.last_scored = True
       
        opponent = self.blue if wrestler == self.red else self.red
        opponent.last_scored = False
       
        timestamp = time.strftime("%H:%M:%S")
        wrestler.action_history.append(f"{timestamp} - {description} (+{points})")
       
        self.update_history_text()
        self.update_display()
        self.check_technical_superiority()
       
        # Немедленная отправка на табло
        self.send_scoreboard_update()
        # Обновляем сетку в реальном времени при изменении очков
        self.update_bracket_realtime()
       
        if self.is_secondary:
            self.send_match_control('add_points',
                                  wrestler='red' if wrestler == self.red else 'blue',
                                  points=points,
                                  description=description)
   
    def add_caution(self, wrestler, description):
        wrestler.cautions += 1
        opponent = self.blue if wrestler == self.red else self.red
        opponent.points += 1
        opponent.last_scored = True
        wrestler.last_scored = False
       
        timestamp = time.strftime("%H:%M:%S")
        wrestler.action_history.append(f"{timestamp} - {description}")
        opponent.action_history.append(f"{timestamp} - Соперник получил {description.lower()} (+1 вам)")
       
        self.update_history_text()
        self.update_display()
        self.check_cautions(wrestler)
       
        # Немедленная отправка на табло
        self.send_scoreboard_update()
       
        if self.is_secondary:
            self.send_match_control('add_caution',
                                  wrestler='red' if wrestler == self.red else 'blue',
                                  description=description)
   
    def add_passivity(self, wrestler, description):
        wrestler.passivity += 1
        opponent = self.blue if wrestler == self.red else self.red
       
        if wrestler.passivity <= 2:
            opponent.points += 1
            opponent.last_scored = True
            wrestler.last_scored = False
           
            timestamp = time.strftime("%H:%M:%S")
            wrestler.action_history.append(f"{timestamp} - {description}")
            opponent.action_history.append(f"{timestamp} - Соперник проявил пассивность (+1 вам)")
        else:
            timestamp = time.strftime("%H:%M:%S")
            wrestler.action_history.append(f"{timestamp} - {description}")
           
        self.update_history_text()
        self.update_display()
       
        # Немедленная отправка на табло
        self.send_scoreboard_update()
       
        if self.is_secondary:
            self.send_match_control('add_passivity',
                                  wrestler='red' if wrestler == self.red else 'blue',
                                  description=description)
   
    def check_technical_superiority(self):
        """
        Проверка технического превосходства с учётом значения,
        введённого пользователем в поле «Техн. превосходство».
        """
        diff = abs(self.red.points - self.blue.points)
        if diff >= self.technical_superiority:
            winner = self.red if self.red.points > self.blue.points else self.blue
            self.end_match(f"Техническое превосходство {winner.color}")
   
    def check_cautions(self, wrestler):
        if wrestler.cautions >= CAUTION_LIMIT:
            opponent = self.blue if wrestler == self.red else self.red
            self.end_match(f"Дисквалификация {wrestler.color} (3 предупреждения). Победа {opponent.color}")
   
    def end_match(self, reason):
        self.pause_timer()
       
        timestamp = time.strftime("%H:%M:%S")
        self.red.action_history.append(f"{timestamp} - {reason}")
        self.blue.action_history.append(f"{timestamp} - {reason}")
       
        self.update_history_text()
        self.determine_winner()
        # После определения победителя сохраняем результат в турнирные данные
        self.update_tournament_match_result()
        QMessageBox.information(self, "Конец матча", reason)
       
        if self.is_secondary:
            self.send_match_control('end_match', reason=reason)
   
    def determine_winner(self):
        if self.winner:
            return
       
        if self.red.points > self.blue.points:
            self.winner = "Красный"
        elif self.blue.points > self.red.points:
            self.winner = "Синий"
        else:
            if self.red.cautions < self.blue.cautions:
                self.winner = "Красный"
            elif self.blue.cautions < self.red.cautions:
                self.winner = "Синий"
            elif self.red.last_scored:
                self.winner = "Красный"
            elif self.blue.last_scored:
                self.winner = "Синий"
            else:
                self.winner = "Ничья"
       
        winner_text = f"ПОБЕДИТЕЛЬ: {self.winner}" if self.winner != "Ничья" else "НИЧЬЯ"
       
        timestamp = time.strftime("%H:%M:%S")
        self.red.action_history.append(f"{timestamp} - {winner_text}")
        self.blue.action_history.append(f"{timestamp} - {winner_text}")
       
        self.update_history_text()
        QMessageBox.information(self, "Результат", winner_text)

    def save_current_match_result(self):
        """Сохраняет результат текущего матча перед переходом к следующему"""
        if not self.tournament_data:
            return
        
        # Ищем матч в расписании
        schedule = self.tournament_data.get('schedule', [])
        target_schedule_match = None
        
        if self.current_match_id:
            for s_match in schedule:
                if s_match.get('match_id') == self.current_match_id:
                    target_schedule_match = s_match
                    break
        
        if target_schedule_match:
            # Обновляем статус в расписании
            target_schedule_match['status'] = 'Завершен'
            target_schedule_match['completed_at'] = datetime.now().strftime("%H:%M")
            target_schedule_match['score1'] = self.red.points
            target_schedule_match['score2'] = self.blue.points
            if self.red.points > self.blue.points:
                target_schedule_match['winner'] = self.red.name
            elif self.blue.points > self.red.points:
                target_schedule_match['winner'] = self.blue.name
        
        # Обновляем матч в категории
        if self.current_match_category:
            self.update_tournament_match_result(save_to_db=True, show_message=False)

    def update_tournament_match_result(self, save_to_db=True, show_message=True):
        """Обновляет результат матча в структуре tournament_data и сетке"""
        if not self.tournament_data or not self.current_match_category:
            return

        categories = self.tournament_data.get('categories', {})
        cat = categories.get(self.current_match_category)
        if not cat:
            return

        matches = cat.get('matches', [])
        target_match = None

        # Поиск матча
        if self.current_match_id:
            for m in matches:
                if m.get('id') == self.current_match_id:
                    target_match = m
                    break

        if target_match is None:
            # Поиск по именам борцов
            for m in matches:
                w1 = m.get('wrestler1')
                w2 = m.get('wrestler2')
                if (w1 == self.current_match_w1 and w2 == self.current_match_w2) or \
                   (w1 == self.current_match_w2 and w2 == self.current_match_w1):
                    target_match = m
                    break

        if target_match is None:
            return

        # Записываем счет
        red_name = self.red.name
        blue_name = self.blue.name

        # Определяем, кто в матче был wrestler1, а кто wrestler2
        if target_match.get('wrestler1') == red_name and target_match.get('wrestler2') == blue_name:
            target_match['score1'] = self.red.points
            target_match['score2'] = self.blue.points
        elif target_match.get('wrestler1') == blue_name and target_match.get('wrestler2') == red_name:
            target_match['score1'] = self.blue.points
            target_match['score2'] = self.red.points
        else:
            # Если имена не совпадают, записываем как есть
            target_match['score1'] = self.red.points
            target_match['score2'] = self.blue.points

        # Помечаем матч как завершенный
        target_match['completed'] = True

        # Определяем победителя (1 балл за победу, 0 за поражение)
        if self.red.points > self.blue.points:
            target_match['winner'] = red_name
            target_match['winner_points'] = 1
            target_match['loser_points'] = 0
        elif self.blue.points > self.red.points:
            target_match['winner'] = blue_name
            target_match['winner_points'] = 1
            target_match['loser_points'] = 0
        else:
            # Ничья
            target_match['winner'] = None
            target_match['winner_points'] = 0
            target_match['loser_points'] = 0

        # Обновляем расписание
        if 'schedule' in self.tournament_data:
            for s_match in self.tournament_data['schedule']:
                if s_match.get('match_id') == target_match.get('id'):
                    s_match['winner'] = target_match.get('winner')
                    s_match['status'] = 'Завершен'
                    s_match['completed_at'] = datetime.now().strftime("%H:%M")
                    break

        # Синхронизируем статус ковра
        if self.schedule_sync:
            self.schedule_sync.send_mat_status("completed", target_match.get('id'))
        self.refresh_inline_schedule()

        # Сохраняем результат матча в БД (безопасно, с перехватом ошибок)
        if save_to_db:
            try:
                save_match_result(self.tournament_data, self.current_match_category, target_match)
            except Exception as e:
                print(f"[DB] Ошибка при сохранении результата матча: {e}")

        # Обновляем вкладку сетки, если она открыта
        main_window = self.window()
        if hasattr(main_window, 'bracket_window') and main_window.bracket_window:
            main_window.bracket_window.update_bracket(self.current_match_category)
        
        # Обновляем все открытые окна сеток в реальном времени
        from ui.widgets.tournament_manager import BracketWindow
        for widget in QApplication.allWidgets():
            if isinstance(widget, BracketWindow):
                if hasattr(widget, 'current_category') and widget.current_category == self.current_match_category:
                    widget.update_bracket(self.current_match_category)
        
        if show_message:
            # Предлагаем загрузить следующий матч
            reply = QMessageBox.question(self, "Матч завершен", 
                                        "Загрузить следующий матч?",
                                        QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                QTimer.singleShot(500, self.load_next_match)  # Небольшая задержка для завершения обновлений

    def update_category_points(self, category, match):
        """Обновляет общие очки участников в категории"""
        wrestlers = category.get('wrestlers', [])
   
        # Проверяем, не были ли уже начислены очки за этот матч
        if match.get('points_awarded', False):
            return
   
        # Находим участников матча
        w1_found = w2_found = False
   
        for wrestler in wrestlers:
            if wrestler['name'] == match.get('wrestler1'):
                w1_found = True
                # Обновляем классификационные очки (победы)
                if match.get('winner') == wrestler['name']:
                    wrestler['classification_points'] = wrestler.get('classification_points', 0) + 1
                    wrestler['tournament_points'] = wrestler.get('tournament_points', 0) + 1
                # Технические очки (сумма набранных очков в матчах)
                wrestler['technical_points'] = wrestler.get('technical_points', 0) + match.get('score1', 0)
           
            elif wrestler['name'] == match.get('wrestler2'):
                w2_found = True
                if match.get('winner') == wrestler['name']:
                    wrestler['classification_points'] = wrestler.get('classification_points', 0) + 1
                    wrestler['tournament_points'] = wrestler.get('tournament_points', 0) + 1
                wrestler['technical_points'] = wrestler.get('technical_points', 0) + match.get('score2', 0)
   
        # Помечаем, что очки за этот матч начислены
        match['points_awarded'] = True
   
        # Обновляем отображение в сетке
        self.update_bracket_display()

    def undo_action(self):
        """Отменяет последнее действие, обрабатывая предупреждения и пассивность"""
        undone = False
       
        try:
            # Проверяем историю красного борца
            if self.red.action_history:
                last_red = self.red.action_history[-1] # Смотрим последнее действие без удаления
               
                # Если это предупреждение (не "Соперник получил...")
                if ("Предупреждение" in last_red or "предупреждение" in last_red) and "Соперник" not in last_red:
                    self.red.action_history.pop()
                    if self.red.cautions > 0:
                        self.red.cautions -= 1
                    # Отменяем очко, которое было дано синему
                    if self.blue.points > 0:
                        self.blue.points -= 1
                    # Удаляем соответствующую запись из истории синего
                    if self.blue.action_history and "Соперник получил" in self.blue.action_history[-1]:
                        self.blue.action_history.pop()
                    undone = True
                # Если это пассивность (не "Соперник проявил...")
                elif ("Пассивность" in last_red or "пассивность" in last_red) and "Соперник" not in last_red:
                    self.red.action_history.pop()
                    old_passivity = self.red.passivity
                    if self.red.passivity > 0:
                        self.red.passivity -= 1
                    # Отменяем очко, которое было дано синему (только если было <= 2 пассивности до отмены)
                    if old_passivity <= 2 and self.blue.points > 0:
                        self.blue.points -= 1
                    # Удаляем соответствующую запись из истории синего
                    if self.blue.action_history and "Соперник проявил" in self.blue.action_history[-1]:
                        self.blue.action_history.pop()
                    undone = True
           
            # Проверяем историю синего борца, если еще ничего не было отменено
            if not undone and self.blue.action_history:
                last_blue = self.blue.action_history[-1]
               
                # Если это предупреждение (не "Соперник получил...")
                if ("Предупреждение" in last_blue or "предупреждение" in last_blue) and "Соперник" not in last_blue:
                    self.blue.action_history.pop()
                    if self.blue.cautions > 0:
                        self.blue.cautions -= 1
                    # Отменяем очко, которое было дано красному
                    if self.red.points > 0:
                        self.red.points -= 1
                    # Удаляем соответствующую запись из истории красного
                    if self.red.action_history and "Соперник получил" in self.red.action_history[-1]:
                        self.red.action_history.pop()
                    undone = True
                # Если это пассивность (не "Соперник проявил...")
                elif ("Пассивность" in last_blue or "пассивность" in last_blue) and "Соперник" not in last_blue:
                    self.blue.action_history.pop()
                    old_passivity = self.blue.passivity
                    if self.blue.passivity > 0:
                        self.blue.passivity -= 1
                    # Отменяем очко, которое было дано красному (только если было <= 2 пассивности до отмены)
                    if old_passivity <= 2 and self.red.points > 0:
                        self.red.points -= 1
                    # Удаляем соответствующую запись из истории красного
                    if self.red.action_history and "Соперник проявил" in self.red.action_history[-1]:
                        self.red.action_history.pop()
                    undone = True
           
            # Если это не предупреждение/пассивность, обрабатываем как обычные очки
            if not undone:
                if self.red.action_history:
                    last_red = self.red.action_history.pop()
                    if "+" in last_red:
                        points_match = re.search(r'\(\+(\d+)\)', last_red)
                        if points_match:
                            points = int(points_match.group(1))
                            if self.red.points >= points:
                                self.red.points -= points
                            undone = True
               
                if not undone and self.blue.action_history:
                    last_blue = self.blue.action_history.pop()
                    if "+" in last_blue:
                        points_match = re.search(r'\(\+(\d+)\)', last_blue)
                        if points_match:
                            points = int(points_match.group(1))
                            if self.blue.points >= points:
                                self.blue.points -= points
        except (IndexError, AttributeError, ValueError) as e:
            print(f"[UNDO] Ошибка при отмене действия: {e}")
            QMessageBox.warning(self, "Ошибка", "Не удалось отменить последнее действие")
            return
           
        self.update_history_text()
        self.update_display()
        # Немедленная отправка на табло для обновления предупреждений и пассивности
        self.send_scoreboard_update()
       
        if self.is_secondary:
            self.send_match_control('undo_action')
   
    def update_display(self):
        main_window = self.window()
        if hasattr(main_window, 'find_scoreboard_tab'):
            scoreboard = main_window.find_scoreboard_tab()
            if scoreboard:
                # Определяем, идет ли перерыв
                is_break = getattr(self, 'break_timer_running', False)
                time_to_show = getattr(self, 'break_time_remaining', 0) if is_break else self.remaining_time
               
                # Используем новый формат вызова с отдельными параметрами,
                # включая название категории для отображения под периодом.
                opponent_wait_time = getattr(self, 'opponent_wait_time_remaining', 0) if self.settings.get_scoreboard_setting("show_opponent_wait_timer") else 0
                scoreboard.update_display(
                    self.red.name, self.red.region, self.red.points, self.red.cautions, self.red.passivity,
                    self.blue.name, self.blue.region, self.blue.points, self.blue.cautions, self.blue.passivity,
                    self.current_period, time_to_show, is_break, self.current_match_category or "", opponent_wait_time
                )
        # Отправка обновления в сеть
        self.send_scoreboard_update()
   
    def update_history_text(self):
        self.red_history_text.clear()
        for event in self.red.action_history[-10:]:
            self.red_history_text.append(event)
           
        self.blue_history_text.clear()
        for event in self.blue.action_history[-10:]:
            self.blue_history_text.append(event)
   
    def save_match(self):
        data = {
            "red": {
                "name": self.red.name,
                "region": self.red.region,
                "points": self.red.points,
                "cautions": self.red.cautions,
                "passivity": self.red.passivity,
                "action_history": self.red.action_history
            },
            "blue": {
                "name": self.blue.name,
                "region": self.blue.region,
                "points": self.blue.points,
                "cautions": self.blue.cautions,
                "passivity": self.blue.passivity,
                "action_history": self.blue.action_history
            },
            "period": self.current_period,
            "time": self.remaining_time,
            "history": self.history.events
        }
       
        filename, _ = QFileDialog.getSaveFileName(self, "Сохранить матч", "", "JSON files (*.json)")
        if filename:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
   
    def load_match(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Загрузить матч", "", "JSON files (*.json)")
        if filename:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
           
            self.red.name = data["red"]["name"]
            self.red.region = data["red"]["region"]
            self.red.points = data["red"]["points"]
            self.red.cautions = data["red"]["cautions"]
            self.red.passivity = data["red"]["passivity"]
            self.red.action_history = data["red"].get("action_history", [])
           
            self.blue.name = data["blue"]["name"]
            self.blue.region = data["blue"]["region"]
            self.blue.points = data["blue"]["points"]
            self.blue.cautions = data["blue"]["cautions"]
            self.blue.passivity = data["blue"]["passivity"]
            self.blue.action_history = data["blue"].get("action_history", [])
           
            self.current_period = data["period"]
            self.remaining_time = data["time"]
            self.history.events = data["history"]
           
            self.red_name_edit.setText(self.red.name)
            self.red_region_edit.setText(self.red.region)
            self.blue_name_edit.setText(self.blue.name)
            self.blue_region_edit.setText(self.blue.region)
           
            self.update_display()
            self.update_history_text()

    def toggle_inline_schedule(self, checked: bool):
        if self.inline_schedule_widget:
            self.inline_schedule_widget.setVisible(checked)
            if checked:
                self.refresh_inline_schedule()

    def refresh_inline_schedule(self):
        if self.inline_schedule_widget:
            self.inline_schedule_widget.update_data(self.tournament_data, self.mat_number)

    def handle_time_edit(self, qtime):
        seconds = qtime.minute() * 60 + qtime.second()
        self.remaining_time = seconds
        # Сохраняем отредактированное время для текущего периода и всех будущих периодов
        for period in range(self.current_period, PERIODS + 1):
            self.period_times[period] = seconds
        self.current_time_label.setText(f"{qtime.minute():02d}:{qtime.second():02d}")
        self.update_display()
        self.send_scoreboard_update()

    def load_next_match(self):
        """Загружает следующий несыгранный матч по расписанию для текущего ковра"""
        if not self.tournament_data:
            QMessageBox.warning(self, "Внимание", "Нет данных о турнире")
            return
        
        # Сохраняем результат текущего матча перед переходом к следующему
        if self.current_match_id or (self.current_match_w1 and self.current_match_w2):
            self.save_current_match_result()
        
        # Очищаем историю и сбрасываем данные для нового матча
        self.reset_all_data()
        
        # Сначала пытаемся использовать расписание
        schedule = self.tournament_data.get('schedule', [])
        if schedule:
            # Фильтруем матчи для текущего ковра и сортируем по времени и раунду
            mat_matches = [m for m in schedule if m.get('mat') == self.mat_number]
            mat_matches.sort(key=lambda x: (x.get('time', ''), x.get('round', 0)))
            
            # Находим следующий несыгранный матч
            next_match = None
            current_match_found = False
            
            for match in mat_matches:
                is_completed = match.get('status') == 'Завершен' or match.get('completed', False)
                is_in_progress = match.get('status') == 'В процессе'
                
                # Если нашли текущий матч, следующий будет следующим несыгранным
                if current_match_found and not is_completed and not is_in_progress:
                    next_match = match
                    break
                
                # Проверяем, это ли текущий матч
                if self.current_match_id and match.get('match_id') == self.current_match_id:
                    current_match_found = True
                elif (match.get('wrestler1') == self.current_match_w1 and 
                      match.get('wrestler2') == self.current_match_w2):
                    current_match_found = True
            
            # Если не нашли после текущего, ищем первый несыгранный
            if not next_match:
                for match in mat_matches:
                    is_completed = match.get('status') == 'Завершен' or match.get('completed', False)
                    is_in_progress = match.get('status') == 'В процессе'
                    if not is_completed and not is_in_progress:
                        next_match = match
                        break
            
            if next_match:
                # Обновляем статус матча в расписании
                next_match['status'] = 'В процессе'
                next_match['started_at'] = datetime.now().strftime("%H:%M")
                self.refresh_inline_schedule()
                if self.schedule_sync:
                    self.schedule_sync.send_mat_status("in_progress", next_match.get('match_id'))
                
                # Загружаем следующий матч
                w1_data = {
                    'name': next_match.get('wrestler1', ''),
                    'club': next_match.get('club1', ''),
                    'category': next_match.get('category', '')
                }
                w2_data = {
                    'name': next_match.get('wrestler2', ''),
                    'club': next_match.get('club2', ''),
                    'category': next_match.get('category', '')
                }
                
                # Устанавливаем борцов
                self.set_match_competitors(w1_data, w2_data)
                
                # Обновляем информацию о текущем матче
                if hasattr(self, 'set_current_match_info'):
                    self.set_current_match_info(
                        next_match.get('category', ''),
                        w1_data['name'],
                        w2_data['name'],
                        next_match.get('match_id')
                    )
                
                # Отправляем обновление на табло
                self.send_scoreboard_update()
                
                # Обновляем расписание в главном окне
                main_window = self.window()
                if main_window and hasattr(main_window, 'update_schedule_tab'):
                    main_window.update_schedule_tab()
                
                return
        
        # Если расписания нет, используем старый метод по категориям
        if not self.current_match_category:
            QMessageBox.warning(self, "Внимание", "Нет данных о текущей категории")
            return
        
        categories = self.tournament_data.get('categories', {})
        cat = categories.get(self.current_match_category)
        if not cat:
            QMessageBox.warning(self, "Внимание", "Категория не найдена")
            return
        
        matches = cat.get('matches', [])
        
        # Сортируем матчи по раундам для правильного порядка (алгоритм round-robin)
        matches_sorted = sorted(matches, key=lambda m: (
            m.get('round', 1),  # Сначала по раунду
            m.get('id', '')     # Потом по ID для стабильной сортировки
        ))
        
        # Находим следующий несыгранный матч
        next_match = None
        current_match_found = False
        
        for match in matches_sorted:
            # Если нашли текущий матч, следующий будет следующим несыгранным
            if current_match_found and not match.get('completed', False):
                next_match = match
                break
            
            # Проверяем, это ли текущий матч
            if self.current_match_id and match.get('id') == self.current_match_id:
                current_match_found = True
            elif (match.get('wrestler1') == self.current_match_w1 and 
                  match.get('wrestler2') == self.current_match_w2):
                current_match_found = True
        
        # Если не нашли после текущего, ищем первый несыгранный
        if not next_match:
            for match in matches_sorted:
                if not match.get('completed', False):
                    next_match = match
                    break
        
        if not next_match:
            QMessageBox.information(self, "Информация", "Все матчи в категории завершены")
            return
        
        # Загружаем следующий матч
        w1_name = next_match.get('wrestler1', '')
        w2_name = next_match.get('wrestler2', '')
        
        # Получаем данные участников
        participants = cat.get('participants', []) or cat.get('wrestlers', [])
        w1_data = None
        w2_data = None
        
        for p in participants:
            if p.get('name') == w1_name:
                w1_data = {'name': w1_name, 'club': p.get('club', '')}
            if p.get('name') == w2_name:
                w2_data = {'name': w2_name, 'club': p.get('club', '')}
        
        if not w1_data or not w2_data:
            QMessageBox.warning(self, "Ошибка", "Не удалось найти данные участников")
            return
        
        # Устанавливаем борцов
        self.set_match_competitors(w1_data, w2_data)
        
        # Устанавливаем информацию о текущем матче
        self.set_current_match_info(
            self.current_match_category,
            w1_name,
            w2_name,
            next_match.get('id')
        )
        self.refresh_inline_schedule()
        if self.schedule_sync:
            self.schedule_sync.send_mat_status("in_progress", next_match.get('id'))
        
        # Отправляем обновление на табло
        self.send_scoreboard_update()
        
        QMessageBox.information(self, "Матч загружен", f"Загружен матч:\n{w1_name} vs {w2_name}")
    
    def reset_all_data(self):
        self.red = Wrestler("Красный")
        self.blue = Wrestler("Синий")
        self.red_name_edit.setText("")
        self.red_region_edit.setText("")
        self.blue_name_edit.setText("")
        self.blue_region_edit.setText("")
        self.current_period = 1
        self.period_label.setText("Период: 1")
        self.remaining_time = self.period_base_duration
        self.period_times = {1: self.period_base_duration, 2: self.period_base_duration, 3: self.period_base_duration}
        self.current_time_label.setText(f"{self.period_base_duration // 60:02d}:{self.period_base_duration % 60:02d}")
        self.timer_running = False
        self.timer.stop()
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.history = MatchHistory()
        self.winner = None
        self.red_history_text.clear()
        self.blue_history_text.clear()
        # Сбрасываем таймер перерыва
        self.break_timer_running = False
        self.break_timer.stop()
        self.break_time_remaining = self.break_base_duration
        minutes = self.break_base_duration // 60
        secs = self.break_base_duration % 60
        self.break_time_label.setText(f"{minutes:02d}:{secs:02d}")
        self.break_start_btn.setEnabled(True)
        self.break_pause_btn.setEnabled(False)
        self.break_toggle_btn.setText("ВКЛ")
        self.break_toggle_btn.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #87CEEB;")
        self.update_display()
        self.send_scoreboard_update()
        self.refresh_inline_schedule()
        if self.schedule_sync:
            self.schedule_sync.send_mat_status("idle", None)
    
    def apply_settings_visibility(self):
        """Применяет настройки видимости элементов"""
        if not hasattr(self, 'settings'):
            self.settings = get_settings()
        
        # Скрываем/показываем кнопки предупреждений и пассивности
        show_cautions = self.settings.get_scoreboard_setting("show_cautions")
        show_passivity = self.settings.get_scoreboard_setting("show_passivity")
        show_opponent_wait = self.settings.get_scoreboard_setting("show_opponent_wait_timer")
        
        if hasattr(self, 'red_caution_btn') and self.red_caution_btn:
            self.red_caution_btn.setVisible(show_cautions)
        if hasattr(self, 'red_passivity_btn') and self.red_passivity_btn:
            self.red_passivity_btn.setVisible(show_passivity)
        if hasattr(self, 'blue_caution_btn') and self.blue_caution_btn:
            self.blue_caution_btn.setVisible(show_cautions)
        if hasattr(self, 'blue_passivity_btn') and self.blue_passivity_btn:
            self.blue_passivity_btn.setVisible(show_passivity)
        
        # Скрываем/показываем таймер ожидания соперника
        if hasattr(self, 'opponent_wait_group'):
            self.opponent_wait_group.setVisible(show_opponent_wait)
    
    def keyPressEvent(self, event: QKeyEvent):
        """Обработка горячих клавиш"""
        # Ctrl+Space для добавления очков
        if event.key() == Qt.Key_Space and (event.modifiers() & Qt.ControlModifier):
            # Пытаемся определить, какой Ctrl нажат (левый или правый)
            # В Windows: левый Ctrl имеет scan code 0x1D, правый Ctrl имеет scan code 0x1D + 0x80
            try:
                # Используем nativeScanCode для определения левого/правого Ctrl
                scan_code = event.nativeScanCode() if hasattr(event, 'nativeScanCode') else 0
                # В Windows: левый Ctrl = 0x1D (29), правый Ctrl = 0x11D (285) или проверяем через модификаторы
                # Альтернативный способ: проверяем через nativeModifiers
                native_mods = event.nativeModifiers() if hasattr(event, 'nativeModifiers') else 0
                # В Windows: левый Ctrl = 0x0002, правый Ctrl = 0x0004 (но это может не работать)
                # Используем проверку через scan code
                # Левый Ctrl обычно имеет scan code 29, правый Ctrl - 285 (29 + 256)
                if scan_code == 285 or (native_mods & 0x0004):  # Правый Ctrl
                    self.add_points(self.blue, 1, "Очко (Ctrl+Space)")
                else:  # Левый Ctrl или по умолчанию
                    self.add_points(self.red, 1, "Очко (Ctrl+Space)")
            except:
                # Если не удалось определить, добавляем красному (левый Ctrl по умолчанию)
                self.add_points(self.red, 1, "Очко (Ctrl+Space)")
            event.accept()
            return
        super().keyPressEvent(event)
    
    def add_point_shortcut(self):
        """Обработчик Ctrl+Space - добавляет очко красному участнику (левый Ctrl)"""
        # По умолчанию добавляем красному (левый Ctrl)
        self.add_points(self.red, 1, "Очко (Ctrl+Space)")
    
    def start_opponent_wait_timer(self):
        """Запускает таймер ожидания соперника (обратный отсчет)"""
        if not self.opponent_wait_timer_running:
            self.opponent_wait_time_remaining = self.opponent_wait_duration
            
            # Обновляем отображение времени
            minutes = self.opponent_wait_time_remaining // 60
            secs = self.opponent_wait_time_remaining % 60
            self.opponent_wait_time_label.setText(f"{minutes:02d}:{secs:02d}")
            
            if self.opponent_wait_time_remaining > 0:
                self.opponent_wait_timer_running = True
                self.opponent_wait_timer.start(1000)
                self.opponent_wait_start_btn.setEnabled(False)
                self.opponent_wait_pause_btn.setEnabled(True)
                self.send_scoreboard_update()
    
    def pause_opponent_wait_timer(self):
        """Останавливает таймер ожидания соперника"""
        self.opponent_wait_timer_running = False
        self.opponent_wait_timer.stop()
        self.opponent_wait_start_btn.setEnabled(True)
        self.opponent_wait_pause_btn.setEnabled(False)
        self.send_scoreboard_update()
    
    def reset_opponent_wait_timer(self):
        """Сбрасывает таймер ожидания соперника"""
        self.pause_opponent_wait_timer()
        self.opponent_wait_time_remaining = self.opponent_wait_duration
        minutes = self.opponent_wait_time_remaining // 60
        secs = self.opponent_wait_time_remaining % 60
        self.opponent_wait_time_label.setText(f"{minutes:02d}:{secs:02d}")
        self.send_scoreboard_update()
    
    def update_opponent_wait_timer(self):
        """Обновляет таймер ожидания соперника (обратный отсчет)"""
        if self.opponent_wait_time_remaining > 0:
            self.opponent_wait_time_remaining -= 1
            minutes = self.opponent_wait_time_remaining // 60
            seconds = self.opponent_wait_time_remaining % 60
            self.opponent_wait_time_label.setText(f"{minutes:02d}:{seconds:02d}")
            self.send_scoreboard_update()
            
            if self.opponent_wait_time_remaining == 0:
                winsound.Beep(2000, 1000)
                self.pause_opponent_wait_timer()
    
    def update_bracket_realtime(self):
        """Обновляет сетку в реальном времени при изменении очков"""
        if not self.tournament_data or not self.current_match_category:
            return
        
        # Обновляем все открытые окна сеток
        from ui.widgets.tournament_manager import BracketWindow
        for widget in QApplication.allWidgets():
            if isinstance(widget, BracketWindow):
                if hasattr(widget, 'current_category') and widget.current_category == self.current_match_category:
                    # Обновляем только таблицу, не перезагружая весь матч
                    widget.update_round_robin_table(self.current_match_category)