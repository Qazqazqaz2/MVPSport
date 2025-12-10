from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit, QComboBox, QVBoxLayout, 
                             QLabel, QDialogButtonBox, QHBoxLayout, QPushButton, QColorDialog)
from PyQt5.QtCore import Qt

class AddWrestlerDialog(QDialog):
    def __init__(self, tournament_date, parent=None):
        super().__init__(parent)
        self.tournament_date = tournament_date
        self.setWindowTitle("Добавить нового участника")
        self.setGeometry(300, 300, 400, 300)
        layout = QFormLayout(self)
        
        self.name = QLineEdit()
        layout.addRow("Имя:", self.name)
        
        self.club = QLineEdit()
        layout.addRow("Клуб:", self.club)
        
        self.birth_date = QLineEdit()
        self.birth_date.setPlaceholderText("dd.mm.yyyy")
        layout.addRow("Дата рождения:", self.birth_date)
        
        self.weight = QLineEdit()
        layout.addRow("Вес (кг):", self.weight)
        
        self.gender = QComboBox()
        self.gender.addItems(["М", "Ж"])
        layout.addRow("Пол:", self.gender)
        
        self.rank = QLineEdit()
        layout.addRow("Разряд:", self.rank)

        # Цвет участника (для отображения в расписании)
        color_layout = QHBoxLayout()
        self.color = QLineEdit()
        self.color.setPlaceholderText("#dc3545")
        self.color.setReadOnly(True)
        pick_btn = QPushButton("Выбрать цвет")
        pick_btn.clicked.connect(self.choose_color)
        color_layout.addWidget(self.color)
        color_layout.addWidget(pick_btn)
        layout.addRow("Цвет:", color_layout)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def get_data(self):
        return {
            'name': self.name.text().strip(),
            'club': self.club.text().strip(),
            'birth_date': self.birth_date.text().strip(),
            'weight': float(self.weight.text() or 0),
            'gender': self.gender.currentText(),
            'rank': self.rank.text().strip(),
            'color': self.color.text().strip()
        }

    def choose_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.color.setText(color.name())

class MoveWrestlerDialog(QDialog):
    def __init__(self, categories, current_cat, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Переместить участника")
        self.setGeometry(300, 300, 300, 150)
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel(f"Переместить из категории: {current_cat}"))
        
        self.target_combo = QComboBox()
        self.target_combo.addItems(list(categories.keys()))
        self.target_combo.setCurrentText(current_cat)
        layout.addWidget(QLabel("В категорию:"))
        layout.addWidget(self.target_combo)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_target(self):
        return self.target_combo.currentText()