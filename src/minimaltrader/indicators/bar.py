from ..models import events
from .base import Indicator


class Open(Indicator):
    def __init__(self, max_history: int = 100, plot_at: int = 99) -> None:
        super().__init__(max_history=max_history, plot_at=plot_at)

    @property
    def name(self) -> str:
        return "OPEN"

    def _compute_indicator(self, incoming_bar: events.ReceivedNewBar) -> float:
        return incoming_bar.open


class High(Indicator):
    def __init__(self, max_history: int = 100, plot_at: int = 99) -> None:
        super().__init__(max_history=max_history, plot_at=plot_at)

    @property
    def name(self) -> str:
        return "HIGH"

    def _compute_indicator(self, incoming_bar: events.ReceivedNewBar) -> float:
        return incoming_bar.high


class Low(Indicator):
    def __init__(self, max_history: int = 100, plot_at: int = 99) -> None:
        super().__init__(max_history=max_history, plot_at=plot_at)

    @property
    def name(self) -> str:
        return "LOW"

    def _compute_indicator(self, incoming_bar: events.ReceivedNewBar) -> float:
        return incoming_bar.low


class Close(Indicator):
    def __init__(self, max_history: int = 100, plot_at: int = 99) -> None:
        super().__init__(max_history=max_history, plot_at=plot_at)

    @property
    def name(self) -> str:
        return "CLOSE"

    def _compute_indicator(self, incoming_bar: events.ReceivedNewBar) -> float:
        return incoming_bar.close


class Volume(Indicator):
    def __init__(self, max_history: int = 100, plot_at: int = 99) -> None:
        super().__init__(max_history=max_history, plot_at=plot_at)

    @property
    def name(self) -> str:
        return "VOLUME"

    def _compute_indicator(self, incoming_bar: events.ReceivedNewBar) -> float:
        return float(incoming_bar.volume) if incoming_bar.volume is not None else 0.0
