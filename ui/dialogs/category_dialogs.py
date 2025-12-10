from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit, QComboBox, QVBoxLayout, 
                             QLabel, QDialogButtonBox, QHBoxLayout)
from PyQt5.QtCore import Qt

class CategoryEditDialog(QDialog):
    def __init__(self, parent=None, category_name="", category_data=None):
        super().__init__(parent)
        self.category_name = category_name
        self.category_data = category_data or {}
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("Редактирование категории" if self.category_name else "Добавление категории")
        self.setGeometry(300, 300, 400, 300)
        layout = QFormLayout(self)
        
        self.name_edit = QLineEdit(self.category_name)
        layout.addRow("Название категории:", self.name_edit)
        
        self.gender_combo = QComboBox()
        self.gender_combo.addItems(["М", "Ж", "Смешанная"])
        if self.category_data.get('gender'):
            self.gender_combo.setCurrentText(self.category_data['gender'])
        else:
            self.gender_combo.setCurrentText("М")
        layout.addRow("Пол:", self.gender_combo)
        
        age_layout = QHBoxLayout()
        self.age_min_edit = QLineEdit(str(self.category_data.get('age_min', 0)))
        self.age_min_edit.setPlaceholderText("0")
        age_layout.addWidget(self.age_min_edit)
        
        age_layout.addWidget(QLabel(" - "))
        
        self.age_max_edit = QLineEdit(str(self.category_data.get('age_max', 99)))
        self.age_max_edit.setPlaceholderText("99")
        age_layout.addWidget(self.age_max_edit)
        
        age_layout.addWidget(QLabel("лет"))
        layout.addRow("Возрастной диапазон:", age_layout)
        
        weight_layout = QHBoxLayout()
        self.weight_min_edit = QLineEdit(str(self.category_data.get('weight_min', 0)))
        self.weight_min_edit.setPlaceholderText("0")
        weight_layout.addWidget(self.weight_min_edit)
        
        weight_layout.addWidget(QLabel(" - "))
        
        self.weight_max_edit = QLineEdit(str(self.category_data.get('weight_max', 999)))
        self.weight_max_edit.setPlaceholderText("999")
        weight_layout.addWidget(self.weight_max_edit)
        
        weight_layout.addWidget(QLabel("кг"))
        layout.addRow("Весовая категория:", weight_layout)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def get_data(self):
        return {
            'name': self.name_edit.text().strip(),
            'gender': self.gender_combo.currentText(),
            'age_min': int(self.age_min_edit.text() or 0),
            'age_max': int(self.age_max_edit.text() or 99),
            'weight_min': float(self.weight_min_edit.text() or 0),
            'weight_max': float(self.weight_max_edit.text() or 999)
        }