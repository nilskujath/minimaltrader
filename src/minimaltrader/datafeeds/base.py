import abc

from ..core import EventBus, Producer
from ..models import enums


class Datafeed(Producer):

    def __init__(self, event_bus: EventBus) -> None:
        super().__init__(event_bus)

    @abc.abstractmethod
    def stream(self, symbols: list[str], bar_period: enums.BarPeriod) -> None:
        pass

    @abc.abstractmethod
    def shutdown(self) -> None:
        pass

