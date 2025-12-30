import abc

from ..models import events
from .event_bus import EventBus


class Producer(abc.ABC):
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def publish(self, event: events.Event) -> None:
        self._event_bus.publish(event)

    @abc.abstractmethod
    def shutdown(self) -> None:
        pass
