"""Event manager: register and dispatch events"""
from typing import Callable, Dict, Any
import threading
import copy




class EventDispatchError(Exception):
    def __init__(self, code: int, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


class EventManager:
    def __init__(self):
        self._handlers: Dict[str, Callable[[Dict], Dict]] = {}
        self._lock = threading.Lock()

    def register(self, event_name: str, handler: Callable[[Dict, Dict], Dict]):
        with self._lock:
            self._handlers[event_name] = handler

    def unregister(self, event_name: str):
        with self._lock:
            if event_name in self._handlers:
                del self._handlers[event_name]

    def list_events(self):
        with self._lock:
            return list(self._handlers.keys())

    def dispatch(self, event_name: str, payload: Dict, context: Dict = None, timeout: int = None) -> Dict:
        if context is None:
            context = {}
        # copy inputs to isolate handler from caller and other handlers
        payload_copy = copy.deepcopy(payload)
        context_copy = copy.deepcopy(context)

        handler = None
        with self._lock:
            handler = self._handlers.get(event_name)
        if handler is None:
            raise EventDispatchError(404, f'Event handler not found: {event_name}')
        result_container = {}

        def _run():
            try:
                res = handler(payload_copy, context_copy)
                result_container['result'] = res
                result_container['status'] = 'ok'
            except EventDispatchError as ede:
                result_container['status'] = 'error'
                result_container['error'] = {'code': ede.code, 'message': ede.message, 'details': ede.details}
            except Exception as ex:
                result_container['status'] = 'error'
                result_container['error'] = {'code': 500, 'message': 'Handler execution error', 'details': str(ex)}

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            # Handler still running after timeout
            return {'status': 'error', 'error': {'code': 408, 'message': 'Handler timeout'}}

        return result_container if result_container else {'status': 'error', 'error': {'code': 500, 'message': 'No result returned'}}
