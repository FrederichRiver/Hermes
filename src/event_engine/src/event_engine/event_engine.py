# EventEngine 事件引擎基础骨架

class EventEngine:
    def __init__(self):
        self.handlers = {}
        self.running = False

    def register(self, event_type, handler):
        self.handlers.setdefault(event_type, []).append(handler)

    def emit(self, event_type, event_data):
        for handler in self.handlers.get(event_type, []):
            handler(event_data)

    def start(self):
        self.running = True
        print("EventEngine started.")

    def stop(self):
        self.running = False
        print("EventEngine stopped.")
