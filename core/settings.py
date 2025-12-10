"""
Модуль для управления настройками приложения
"""
import json
import os
from typing import Dict, Any

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "scoreboard": {
        "show_passivity": True,
        "show_cautions": True,
        "show_period": True,
        "show_opponent_wait_timer": False
    },
    "tournament": {
        "number_of_mats": 2
    },
    "timers": {
        "period_duration": 180,
        "break_duration": 30,
        "opponent_wait_duration": 60
    },
    "network": {
        "role": "coordinator",          # coordinator | node | relay
        "mat_number": 1,
        "device_name": "Устройство",
        "coordinator_host": "",
        "allow_relay": True,
        "auto_start": True
    }
}

class Settings:
    """Класс для управления настройками приложения"""
    
    def __init__(self):
        self.settings = DEFAULT_SETTINGS.copy()
        self.load_settings()
    
    def load_settings(self):
        """Загружает настройки из файла"""
        # Сначала сбрасываем настройки на значения по умолчанию
        self.settings = DEFAULT_SETTINGS.copy()
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # Объединяем с настройками по умолчанию
                    self._merge_settings(self.settings, loaded)
            except Exception as e:
                print(f"Ошибка загрузки настроек: {e}")
                self.settings = DEFAULT_SETTINGS.copy()
    
    def _merge_settings(self, default: Dict[str, Any], loaded: Dict[str, Any]):
        """Рекурсивно объединяет настройки"""
        for key, value in loaded.items():
            if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                self._merge_settings(default[key], value)
            else:
                default[key] = value
    
    def save_settings(self):
        """Сохраняет настройки в файл"""
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения настроек: {e}")
    
    def get(self, section: str, key: str, default=None):
        """Получает значение настройки"""
        return self.settings.get(section, {}).get(key, default)
    
    def set(self, section: str, key: str, value: Any):
        """Устанавливает значение настройки"""
        if section not in self.settings:
            self.settings[section] = {}
        self.settings[section][key] = value
        self.save_settings()
    
    def get_scoreboard_setting(self, key: str) -> bool:
        """Получает настройку табло"""
        return self.get("scoreboard", key, DEFAULT_SETTINGS["scoreboard"].get(key, True))

# Глобальный экземпляр настроек
_settings_instance = None

def get_settings() -> Settings:
    """Получает глобальный экземпляр настроек"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
