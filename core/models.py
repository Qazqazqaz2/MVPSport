import time
import re

class Wrestler:
    def __init__(self, color, name="", region=""):
        self.color = color
        self.name = name
        self.region = region
        self.points = 0
        self.cautions = 0
        self.passivity = 0
        self.last_scored = False
        self.action_history = []

class MatchHistory:
    def __init__(self):
        self.events = []
    
    def add_event(self, description, points_red=0, points_blue=0):
        timestamp = time.strftime("%H:%M:%S")
        self.events.append((timestamp, description, points_red, points_blue))
    
    def undo_last(self):
        if self.events:
            return self.events.pop()
        return None