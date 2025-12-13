import sys
import argparse
import socket
import time
from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QMetaType
from PyQt5.QtGui import QTextCursor
from ui.main_window import EnhancedControlPanel
from core.utils import get_local_ip
from core.logger import init_logger, get_logger
from core.settings import get_settings

# Сохраняем оригинальные методы QMessageBox
_original_question = QMessageBox.question
_original_warning = QMessageBox.warning
_original_critical = QMessageBox.critical

def main():
    app = QApplication(sys.argv)
    
    # Регистрация мета-типов для устранения предупреждений
    try:
        # Регистрируем QTextCursor для queued-сигналов
        QtCore.qRegisterMetaType(QTextCursor)
        # Регистрируем QVector<int> как строку (C++ шаблонный тип)
        QtCore.qRegisterMetaType("QVector<int>")
        # Также регистрируем через QMetaType для совместимости
        try:
            from PyQt5.QtCore import QVariant
            # Регистрируем типы для использования в сигналах
            if not QMetaType.type("QVector<int>"):
                QMetaType.registerType("QVector<int>")
        except:
            pass
    except Exception as e:
        # Типы могут быть уже зарегистрированы или не поддерживаться
        # Это не критично, предупреждения не влияют на работу приложения
        pass
    
    # Аргументы командной строки
    parser = argparse.ArgumentParser(description='Система управления борьбой')
    parser.add_argument('--secondary', action='store_true', help='Запуск в режиме второго ПК')
    parser.add_argument('--server', type=str, help='IP адрес сервера для подключения', default=get_local_ip())
    args = parser.parse_args()
    
    # Инициализация логирования ДО создания главного окна
    settings = get_settings()
    device_name = settings.get("network", "device_name", socket.gethostname())
    device_id = f"{device_name}-{int(time.time()*1000)}"
    
    # Определяем роль на основе аргументов
    if args.secondary:
        role = "node"
        coordinator_host = args.server if args.server else settings.get("network", "coordinator_host", "")
    else:
        role = settings.get("network", "role", "coordinator")
        coordinator_host = settings.get("network", "coordinator_host", "")
    
    # Функция для отправки логов на coordinator (будет установлена после создания main_window)
    def log_send_handler(log_entry):
        # Эта функция будет установлена в main_window после создания schedule_sync_service
        pass
    
    # Инициализируем логгер
    logger = init_logger(
        device_name=device_name,
        device_id=device_id,
        role=role,
        coordinator_host=coordinator_host if coordinator_host else None,
        log_dir="logs",
        on_log_send=log_send_handler
    )
    
    logger.log_info("Приложение запущено", {"argv": sys.argv, "role": role, "is_secondary": args.secondary})
    
    # Перехватываем QMessageBox для логирования окон завершения
    def patched_question(parent, title, text, buttons=QMessageBox.Yes | QMessageBox.No, defaultButton=QMessageBox.NoButton):
        """Перехватывает QMessageBox.question и логирует окна завершения"""
        logger = get_logger()
        
        # Проверяем, является ли это окном завершения программы
        is_exit_dialog = any(keyword in text.lower() for keyword in ['закрыть', 'exit', 'quit', 'завершить', 'выйти', 'close'])
        
        if logger and is_exit_dialog:
            logger.log_exit_dialog("question", f"{title}: {text}", result=None)
        
        result = _original_question(parent, title, text, buttons, defaultButton)
        
        if logger and is_exit_dialog:
            result_text = "Yes" if result == QMessageBox.Yes else "No" if result == QMessageBox.No else str(result)
            logger.log_exit_dialog("question", f"{title}: {text}", result=result_text)
        
        return result
    
    def patched_warning(parent, title, text, buttons=QMessageBox.Ok, defaultButton=QMessageBox.NoButton):
        """Перехватывает QMessageBox.warning"""
        logger = get_logger()
        if logger:
            logger.log_warning(f"{title}: {text}")
        return _original_warning(parent, title, text, buttons, defaultButton)
    
    def patched_critical(parent, title, text, buttons=QMessageBox.Ok, defaultButton=QMessageBox.NoButton):
        """Перехватывает QMessageBox.critical"""
        logger = get_logger()
        if logger:
            logger.log_error(f"{title}: {text}")
        return _original_critical(parent, title, text, buttons, defaultButton)
    
    # Применяем патчи
    QMessageBox.question = staticmethod(patched_question)
    QMessageBox.warning = staticmethod(patched_warning)
    QMessageBox.critical = staticmethod(patched_critical)
    
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
    
    try:
        exit_code = app.exec_()
        logger = get_logger()
        if logger:
            logger.log_info("Приложение завершено нормально", {"exit_code": exit_code})
        sys.exit(exit_code)
    except Exception as e:
        logger = get_logger()
        if logger:
            import traceback
            logger.log_crash("Неожиданное завершение приложения", traceback.format_exc())
        raise

if __name__ == "__main__":
    main()