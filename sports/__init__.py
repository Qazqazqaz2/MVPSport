# sports/__init__.py
import os
from importlib import import_module

SPORTS = {}

def load_sports():
    sports_dir = os.path.dirname(__file__)
    for folder in os.listdir(sports_dir):
        path = os.path.join(sports_dir, folder)
        if os.path.isdir(path) and folder not in ['__pycache__']:
            try:
                mod = import_module(f"sports.{folder}.constants")
                name = getattr(mod, "SPORT_NAME", folder.replace('_', ' ').title())
                icon = getattr(mod, "SPORT_ICON", "🏃")
                SPORTS[folder] = {
                    "name": name,
                    "icon": icon,
                    "folder": folder
                }
            except Exception as e:
                print(f"Ошибка загрузки спорта {folder}: {e}")

load_sports()