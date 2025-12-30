import abc
import queue
import threading

from ..models import events


class Consumer(abc.ABC):
    def __init__(self) -> None:
        self.incoming_event_queue: queue.Queue[events.Event | None] = queue.Queue()
        self._thread: threading.Thread = threading.Thread(
            target=self._consume, name=self.__class__.__name__, daemon=False
        )
        self._thread.start()

    def receive(self, incoming_event: events.Event) -> None:
        self.incoming_event_queue.put(incoming_event)

    def _consume(self) -> None:
        while True:
            incoming_event = self.incoming_event_queue.get()
            if incoming_event is None:
                self.incoming_event_queue.task_done()
                break
            self.on_event(incoming_event)
            self.incoming_event_queue.task_done()

    @abc.abstractmethod
    def on_event(self, incoming_event: events.Event) -> None:
        pass

    @abc.abstractmethod
    def shutdown(self) -> None:
        pass
