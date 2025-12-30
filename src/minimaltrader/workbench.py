import abc

from .core import Consumer
from .models import enums, events


class Strategy(Consumer, abc.ABC):
    def __init__(self, symbols: list[str], bar_period: enums.BarPeriod) -> None:
        super().__init__()
        self.symbols = symbols
        self.bar_period = bar_period

    def on_event(self, incoming_event: events.Event) -> None:
        if isinstance(incoming_event, events.ReceivedNewBar):
            self.on_bar(incoming_event)

    @abc.abstractmethod
    def on_bar(self, bar: events.ReceivedNewBar) -> None:
        pass

    def shutdown(self) -> None:
        self.incoming_event_queue.put(None)
        self._thread.join()


class Trader:
    pass
