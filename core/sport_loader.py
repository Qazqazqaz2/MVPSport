# core/sport_loader.py
from importlib import import_module
from sports import SPORTS

class SportLoader:
    @staticmethod
    def get_sport_config(sport_key):
        return SPORTS.get(sport_key, SPORTS.get("greco_roman"))

    @staticmethod
    def load_control_panel(sport_key, *args, **kwargs):
        try:
            mod = import_module(f"sports.{sport_key}.control_panel")
            return mod.ControlPanel(*args, **kwargs)
        except:
            # fallback
            mod = import_module("sports.greco_roman.control_panel")
            return mod.ControlPanel(*args, **kwargs)

    @staticmethod
    def load_scoreboard(sport_key, *args, **kwargs):
        try:
            mod = import_module(f"sports.{sport_key}.scoreboard")
            return mod.ScoreboardWindow(*args, **kwargs)
        except:
            mod = import_module("sports.greco_roman.scoreboard")
            return mod.ScoreboardWindow(*args, **kwargs)