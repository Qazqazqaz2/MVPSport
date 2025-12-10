import socket
import threading
import json
import time
from core.constants import NETWORK_PORT

class NetworkManager:
    def __init__(self):
        self.server_socket = None
        self.client_sockets = []
        self.is_server = False
        self.running = False
        self.message_handlers = {}
        # Добавляем обработчик запросов обновления
        self.register_handler('request_scoreboard_update', self.handle_request_update)
        self.register_handler('scoreboard_update', self.handle_scoreboard_update)

    def handle_request_update(self, message, client_socket):
        """Обрабатывает запросы обновления от клиентов"""
        print(f"[СЕРВЕР] Получен запрос обновления от клиента")
        
    def handle_scoreboard_update(self, message, client_socket):
        """Обрабатывает обновления табло"""
        print(f"[СЕРВЕР] Получено обновление табло: {message}")
        # Пересылаем сообщение всем клиентам
        if self.is_server:
            message_bytes = json.dumps(message).encode('utf-8')
            for client in self.client_sockets[:]:
                try:
                    if client != client_socket:
                        client.send(message_bytes)
                        print(f"[СЕРВЕР] Сообщение переслано клиенту")
                except:
                    self.client_sockets.remove(client)

    def start_server(self, host='0.0.0.0'):
        """Запуск сервера"""
        try:
            self.is_server = True
            self.running = True
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((host, NETWORK_PORT))
            self.server_socket.listen(5)
            
            # Запуск потока для принятия подключений
            accept_thread = threading.Thread(target=self._accept_connections)
            accept_thread.daemon = True
            accept_thread.start()
            print(f"Сервер запущен на {host}:{NETWORK_PORT}")
            return True
        except Exception as e:
            print(f"Ошибка запуска сервера: {e}")
            return False
    
    def connect_to_server(self, host):
        """Подключение к серверу"""
        try:
            self.is_server = False
            self.running = True
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((host, NETWORK_PORT))
            self.client_sockets.append(client_socket)
            
            # Запуск потока для приема сообщений
            receive_thread = threading.Thread(target=self._receive_messages, args=(client_socket,))
            receive_thread.daemon = True
            receive_thread.start()
            print(f"Успешно подключено к серверу {host}:{NETWORK_PORT}")
            return True
        except Exception as e:
            print(f"Ошибка подключения к серверу {host}:{NETWORK_PORT}: {e}")
            return False
    
    def _accept_connections(self):
        """Принятие входящих подключений"""
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                print(f"Подключен клиент: {addr}")
                self.client_sockets.append(client_socket)
                
                # Запуск потока для приема сообщений от клиента
                receive_thread = threading.Thread(target=self._receive_messages, args=(client_socket,))
                receive_thread.daemon = True
                receive_thread.start()
            except:
                break
    
    def _receive_messages(self, client_socket):
        """Прием сообщений от клиента"""
        while self.running:
            try:
                data = client_socket.recv(4096)
                if not data:
                    break
                
                message = json.loads(data.decode('utf-8'))
                self._handle_message(message, client_socket)
            except:
                break
        
        # Удаляем отключившегося клиента
        if client_socket in self.client_sockets:
            self.client_sockets.remove(client_socket)
            print("Клиент отключен")
    
    def _handle_message(self, message, client_socket):
        """Обработка входящих сообщений"""
        message_type = message.get('type')
        if message_type in self.message_handlers:
            self.message_handlers[message_type](message, client_socket)
    
    def send_message(self, message_type, data):
        """Отправка сообщения"""
        message = {
            'type': message_type,
            'data': data,
            'timestamp': time.time()
        }
        
        try:
            message_bytes = json.dumps(message).encode('utf-8')
            
            if self.is_server:
                # Сервер рассылает всем клиентам
                for client in self.client_sockets[:]:
                    try:
                        client.send(message_bytes)
                    except:
                        self.client_sockets.remove(client)
            elif self.client_sockets:
                # Клиент отправляет серверу
                self.client_sockets[0].send(message_bytes)
        except Exception as e:
            print(f"Ошибка отправки сообщения: {e}")
    
    def register_handler(self, message_type, handler):
        """Регистрация обработчика сообщений"""
        self.message_handlers[message_type] = handler
    
    def stop(self):
        """Остановка сетевого менеджера"""
        self.running = False
        for client in self.client_sockets:
            try:
                client.close()
            except:
                pass
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass