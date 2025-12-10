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
        self.register_handler('request_scoreboard_update', self.handle_request_update)
        self.register_handler('scoreboard_update', self.handle_scoreboard_update)

    def register_handler(self, message_type, handler):
        self.message_handlers[message_type] = handler

    def handle_request_update(self, message, client_socket):
        print("[СЕРВЕР] Клиент запросил обновление")

    def handle_scoreboard_update(self, message, client_socket):
        print("[СЕРВЕР] Получено обновление табло:", message)
        if self.is_server:
            message_bytes = json.dumps(message).encode('utf-8')
            for client in self.client_sockets[:]:
                try:
                    if client != client_socket:
                        client.send(message_bytes)
                except:
                    self.client_sockets.remove(client)

    def start_server(self, host='0.0.0.0'):
        try:
            self.is_server = True
            self.running = True
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((host, NETWORK_PORT))
            self.server_socket.listen(5)
            threading.Thread(target=self._accept_connections, daemon=True).start()
            print(f"Сервер запущен на {host}:{NETWORK_PORT}")
            return True
        except Exception as e:
            print(f"Ошибка запуска сервера: {e}")
            return False

    def connect_to_server(self, host):
        try:
            self.is_server = False
            self.running = True
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((host, NETWORK_PORT))
            self.client_sockets.append(client_socket)
            threading.Thread(target=self._receive_messages, args=(client_socket,), daemon=True).start()
            print(f"Подключено к серверу {host}:{NETWORK_PORT}")
            return True
        except Exception as e:
            print(f"Ошибка подключения: {e}")
            return False

    def _accept_connections(self):
        while self.running:
            client_socket, addr = self.server_socket.accept()
            print(f"Подключен клиент: {addr}")
            self.client_sockets.append(client_socket)
            threading.Thread(target=self._receive_messages, args=(client_socket,), daemon=True).start()

    def _receive_messages(self, client_socket):
        while self.running:
            try:
                data = client_socket.recv(4096)
                if not data:
                    break
                message = json.loads(data.decode('utf-8'))
                self._handle_message(message, client_socket)
            except:
                break
        if client_socket in self.client_sockets:
            self.client_sockets.remove(client_socket)
            print("Клиент отключен")

    def _handle_message(self, message, client_socket):
        msg_type = message.get('type')
        if msg_type in self.message_handlers:
            self.message_handlers[msg_type](message, client_socket)

    def send_message(self, message_type, data):
        message = {'type': message_type, 'data': data, 'timestamp': time.time()}
        try:
            msg_bytes = json.dumps(message).encode('utf-8')
            if self.is_server:
                for c in self.client_sockets[:]:
                    try:
                        c.send(msg_bytes)
                    except:
                        self.client_sockets.remove(c)
            elif self.client_sockets:
                self.client_sockets[0].send(msg_bytes)
        except Exception as e:
            print(f"Ошибка отправки: {e}")

    def stop(self):
        self.running = False
        for c in self.client_sockets:
            c.close()
        if self.server_socket:
            self.server_socket.close()
