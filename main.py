import sys
import argparse
from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QMetaType
from PyQt5.QtGui import QTextCursor
from ui.main_window import EnhancedControlPanel
from core.utils import get_local_ip

def main():
    app = QApplication(sys.argv)
    
    # Регистрация мета-типов для устранения предупреждений
    try:
        # Регистрируем QTextCursor (нужен для queued-сигналов)
        QMetaType.registerType(QTextCursor.__name__)
        # Для QVector<int> регистрируем строкой
        QMetaType.registerType("QVector<int>")
        # Дополнительно через qRegisterMetaType, если доступен
        if hasattr(QtCore, "qRegisterMetaType"):
            QtCore.qRegisterMetaType(QTextCursor)
            QtCore.qRegisterMetaType("QVector<int>")
    except Exception:
        pass  # Если уже зарегистрированы или не поддерживаются
    
    # Аргументы командной строки
    parser = argparse.ArgumentParser(description='Система управления борьбой')
    parser.add_argument('--secondary', action='store_true', help='Запуск в режиме второго ПК')
    parser.add_argument('--server', type=str, help='IP адрес сервера для подключения', default=get_local_ip())
    args = parser.parse_args()
    
    # Стиль приложения
    app.setStyleSheet("""
        QMainWindow {
            background-color: #f0f0f0;
        }
        QGroupBox {
            font-weight: bold;
            border: 2px solid #cccccc;
            border-radius: 8px;
            margin-top: 1ex;
            padding-top: 12px;
            font-size: 14px;
            background-color: white;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 8px 0 8px;
            background-color: white;
        }
        QPushButton {
            background-color: #e0e0e0;
            border: 1px solid #aaaaaa;
            border-radius: 5px;
            padding: 8px 12px;
            font-weight: bold;
            font-size: 14px;
        }
        QPushButton:hover {
            background-color: #d0d0d0;
        }
        QPushButton:pressed {
            background-color: #c0c0c0;
        }
        QTextEdit {
            border: 1px solid #aaaaaa;
            border-radius: 5px;
            font-size: 14px;
            padding: 5px;
        }
        QLineEdit {
            border: 1px solid #aaaaaa;
            border-radius: 5px;
            padding: 6px;
            font-size: 14px;
            background-color: white;
        }
        QLabel {
            font-size: 14px;
        }
        QTabWidget::pane {
            border: 1px solid #aaaaaa;
            border-radius: 5px;
        }
        QTabBar::tab {
            padding: 10px 14px;
            font-size: 14px;
        }
        QComboBox {
            font-size: 14px;
            padding: 5px;
            background-color: white;
        }
        QListWidget {
            font-size: 14px;
        }
        QTableWidget {
            font-size: 14px;
        }
        QHeaderView::section {
            font-size: 14px;
            font-weight: bold;
            padding: 8px;
        }
        QSplitter::handle {
            background-color: #cccccc;
            width: 4px;
        }
    """)
    
    # Запуск приложения в соответствующем режиме
    if args.secondary:
        print(f"Запуск в режиме второго ПК. Подключение к серверу: {args.server}")
        main_window = EnhancedControlPanel(is_secondary=True, server_host=args.server)
    else:
        local_ip = get_local_ip()
        print(f"Запуск в режиме основного ПК. IP сервера: {local_ip}")
        print(f"Для подключения второго ПК используйте: python main.py --secondary --server {local_ip}")
        main_window = EnhancedControlPanel(is_secondary=False)
    
    main_window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()