"""
Модуль централизованного логирования для отслеживания ошибок, вылетов, рекурсий и окон завершения.
Логи сохраняются в реальном времени для каждого устройства в отдельном файле на coordinator устройстве.
"""
import sys
import os
import traceback
import threading
import time
import json
import socket
from datetime import datetime
from typing import Optional, Callable, Dict, Any
from pathlib import Path
import re

# Глобальные переменные для логирования
_logger_instance = None
_log_lock = threading.Lock()


class DeviceLogger:
    """Централизованный логгер для устройства"""
    
    def __init__(
        self,
        device_name: str,
        device_id: str,
        role: str = "node",
        coordinator_host: Optional[str] = None,
        log_dir: str = "logs",
        on_log_send: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.device_name = device_name
        self.device_id = device_id
        self.role = role
        self.coordinator_host = coordinator_host
        self.log_dir = Path(log_dir)
        self.on_log_send = on_log_send
        
        # Создаем директорию для логов
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Локальный файл логов для этого устройства
        self.local_log_file = self.log_dir / f"{device_name}_{device_id}.log"
        
        # Файл логов на coordinator (если мы coordinator, то локальный)
        if self.role == "coordinator":
            self.coordinator_log_file = self.log_dir / f"coordinator_all_devices.log"
        else:
            # Для node устройств логи будут отправляться на coordinator
            self.coordinator_log_file = None
        
        # Паттерны для фильтрации ненужных сообщений
        self.filter_patterns = [
            r'@python\s*\(\d+\)',  # @python (1001)
            r'QApplication::\w+',  # QApplication сообщения
            r'qt\.qpa\.',  # Qt platform abstraction
            r'QWindowsContext::',  # Windows специфичные сообщения
        ]
        
        # Счетчик рекурсий для отслеживания
        self._recursion_depth = {}
        self._max_recursion_depth = 50
        
        # Оригинальные обработчики
        self._original_excepthook = sys.excepthook
        self._original_thread_excepthook = threading.excepthook if hasattr(threading, 'excepthook') else None
        
        # Установка обработчиков
        self._setup_exception_handlers()
        
    def _should_filter(self, message: str) -> bool:
        """Проверяет, нужно ли отфильтровать сообщение"""
        if not message:
            return True
        message_lower = message.lower()
        for pattern in self.filter_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True
        return False
    
    def _setup_exception_handlers(self):
        """Устанавливает глобальные обработчики исключений"""
        def custom_excepthook(exc_type, exc_value, exc_traceback):
            """Обработчик необработанных исключений"""
            if issubclass(exc_type, KeyboardInterrupt):
                # Не логируем KeyboardInterrupt
                self._original_excepthook(exc_type, exc_value, exc_traceback)
                return
            
            # Получаем полный traceback
            tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
            tb_text = ''.join(tb_lines)
            
            # Проверяем на рекурсию
            recursion_detected = self._check_recursion(tb_text)
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "device": self.device_name,
                "device_id": self.device_id,
                "type": "UNHANDLED_EXCEPTION",
                "exception_type": exc_type.__name__,
                "exception_message": str(exc_value),
                "traceback": tb_text,
                "recursion_detected": recursion_detected,
            }
            
            self._write_log(log_entry, level="ERROR")
            
            # Вызываем оригинальный обработчик
            self._original_excepthook(exc_type, exc_value, exc_traceback)
        
        sys.excepthook = custom_excepthook
        
        # Обработчик исключений в потоках (Python 3.8+)
        if hasattr(threading, 'excepthook'):
            def custom_thread_excepthook(args):
                """Обработчик исключений в потоках"""
                exc_type, exc_value, exc_tb = args.exc_type, args.exc_value, args.exc_traceback
                
                if exc_type is None:
                    return
                
                tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
                tb_text = ''.join(tb_lines)
                
                recursion_detected = self._check_recursion(tb_text)
                
                log_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "device": self.device_name,
                    "device_id": self.device_id,
                    "type": "THREAD_EXCEPTION",
                    "thread_name": getattr(args, 'thread', threading.current_thread()).name,
                    "exception_type": exc_type.__name__,
                    "exception_message": str(exc_value),
                    "traceback": tb_text,
                    "recursion_detected": recursion_detected,
                }
                
                self._write_log(log_entry, level="ERROR")
                
                if self._original_thread_excepthook:
                    self._original_thread_excepthook(args)
            
            threading.excepthook = custom_thread_excepthook
    
    def _check_recursion(self, traceback_text: str) -> bool:
        """Проверяет наличие рекурсии в traceback"""
        # Подсчитываем повторяющиеся вызовы функций
        lines = traceback_text.split('\n')
        call_stack = []
        
        for line in lines:
            # Ищем строки с вызовами функций (например, "File "...", line X, in function_name")
            match = re.search(r'in\s+(\w+)', line)
            if match:
                func_name = match.group(1)
                call_stack.append(func_name)
        
        # Проверяем на повторяющиеся последовательности
        if len(call_stack) > self._max_recursion_depth:
            return True
        
        # Проверяем на повторяющиеся вызовы одной функции подряд
        if len(call_stack) >= 3:
            for i in range(len(call_stack) - 2):
                if call_stack[i] == call_stack[i+1] == call_stack[i+2]:
                    return True
        
        return False
    
    def _write_log(self, log_entry: Dict[str, Any], level: str = "INFO"):
        """Записывает лог-запись в файл и отправляет на coordinator"""
        # Защита от рекурсии - не логируем ошибки логирования
        if "_logging_in_progress" in log_entry:
            return
        
        with _log_lock:
            try:
                # Добавляем уровень
                log_entry["level"] = level
                
                # Форматируем сообщение для файла
                log_line = json.dumps(log_entry, ensure_ascii=False) + "\n"
                
                # Записываем в локальный файл
                try:
                    with open(self.local_log_file, 'a', encoding='utf-8') as f:
                        f.write(log_line)
                        f.flush()  # Принудительная запись в реальном времени
                except Exception as e:
                    # Не логируем ошибки записи, чтобы избежать рекурсии
                    try:
                        print(f"Ошибка записи в локальный лог: {e}")
                    except:
                        pass
                
                # Если мы coordinator, записываем в общий файл
                if self.role == "coordinator" and self.coordinator_log_file:
                    try:
                        with open(self.coordinator_log_file, 'a', encoding='utf-8') as f:
                            f.write(log_line)
                            f.flush()
                    except Exception as e:
                        try:
                            print(f"Ошибка записи в coordinator лог: {e}")
                        except:
                            pass
                
                # Отправляем на coordinator через сеть (если мы не coordinator)
                # Проверяем, что on_log_send установлен и не вызывает рекурсию
                if self.role != "coordinator" and self.on_log_send is not None:
                    try:
                        # Проверяем, что это не вызов из самого on_log_send
                        if not hasattr(self, '_sending_log'):
                            self._sending_log = True
                            try:
                                self.on_log_send(log_entry)
                            except (AttributeError, RuntimeError) as e:
                                # Если функция еще не установлена правильно или объект удален
                                pass
                            finally:
                                self._sending_log = False
                    except Exception as e:
                        # Не логируем ошибки отправки, чтобы избежать рекурсии
                        try:
                            print(f"Ошибка отправки лога на coordinator: {e}")
                        except:
                            pass
                
            except Exception as e:
                # Критическая ошибка - выводим в консоль, но не логируем
                try:
                    print(f"КРИТИЧЕСКАЯ ОШИБКА ЛОГИРОВАНИЯ: {e}")
                except:
                    pass
    
    def log_error(self, message: str, exception: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None):
        """Логирует ошибку"""
        if self._should_filter(message):
            return
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "device": self.device_name,
            "device_id": self.device_id,
            "type": "ERROR",
            "message": message,
        }
        
        if exception:
            log_entry["exception_type"] = type(exception).__name__
            log_entry["exception_message"] = str(exception)
            log_entry["traceback"] = traceback.format_exc()
        
        if context:
            log_entry["context"] = context
        
        self._write_log(log_entry, level="ERROR")
    
    def log_warning(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Логирует предупреждение"""
        if self._should_filter(message):
            return
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "device": self.device_name,
            "device_id": self.device_id,
            "type": "WARNING",
            "message": message,
        }
        
        if context:
            log_entry["context"] = context
        
        self._write_log(log_entry, level="WARNING")
    
    def log_info(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Логирует информационное сообщение"""
        if self._should_filter(message):
            return
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "device": self.device_name,
            "device_id": self.device_id,
            "type": "INFO",
            "message": message,
        }
        
        if context:
            log_entry["context"] = context
        
        self._write_log(log_entry, level="INFO")
    
    def log_exit_dialog(self, dialog_type: str, message: str, result: Optional[str] = None):
        """Логирует появление окна завершения программы"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "device": self.device_name,
            "device_id": self.device_id,
            "type": "EXIT_DIALOG",
            "dialog_type": dialog_type,
            "message": message,
            "result": result,
        }
        
        self._write_log(log_entry, level="WARNING")
    
    def log_crash(self, reason: str, traceback_text: Optional[str] = None):
        """Логирует вылет приложения"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "device": self.device_name,
            "device_id": self.device_id,
            "type": "CRASH",
            "reason": reason,
        }
        
        if traceback_text:
            log_entry["traceback"] = traceback_text
            log_entry["recursion_detected"] = self._check_recursion(traceback_text)
        
        self._write_log(log_entry, level="CRITICAL")
    
    def log_recursion(self, function_name: str, depth: int, traceback_text: Optional[str] = None):
        """Логирует обнаруженную рекурсию"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "device": self.device_name,
            "device_id": self.device_id,
            "type": "RECURSION",
            "function_name": function_name,
            "depth": depth,
        }
        
        if traceback_text:
            log_entry["traceback"] = traceback_text
        
        self._write_log(log_entry, level="ERROR")


# Глобальная функция для получения экземпляра логгера
def get_logger() -> Optional[DeviceLogger]:
    """Возвращает глобальный экземпляр логгера"""
    return _logger_instance


def init_logger(
    device_name: str,
    device_id: str,
    role: str = "node",
    coordinator_host: Optional[str] = None,
    log_dir: str = "logs",
    on_log_send: Optional[Callable[[Dict[str, Any]], None]] = None
) -> DeviceLogger:
    """Инициализирует глобальный логгер"""
    global _logger_instance
    _logger_instance = DeviceLogger(
        device_name=device_name,
        device_id=device_id,
        role=role,
        coordinator_host=coordinator_host,
        log_dir=log_dir,
        on_log_send=on_log_send
    )
    return _logger_instance

