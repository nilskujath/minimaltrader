import collections

import numpy as np

from ..models import enums, events
from .base import Indicator


class SimpleMovingAverage(Indicator):
    def __init__(
        self,
        period: int = 200,
        max_history: int = 100,
        input_source: enums.InputSource = enums.InputSource.CLOSE,
    ) -> None:
        super().__init__(max_history=max_history)
        self.period: int = max(1, int(period))
        self.input_source: enums.InputSource = input_source
        self._window: collections.deque[float] = collections.deque(maxlen=self.period)

    @property
    def name(self) -> str:
        return f"SMA_{self.period}_{self.input_source.name}"

    def _compute_indicator(self, incoming_bar: events.ReceivedNewBar) -> float:
        value: float = self._extract_input(incoming_bar)
        self._window.append(value)
        if len(self._window) < self.period:
            return np.nan
        return sum(self._window) / self.period

    def _extract_input(self, incoming_bar: events.ReceivedNewBar) -> float:
        match self.input_source:
            case enums.InputSource.OPEN:
                return incoming_bar.open
            case enums.InputSource.HIGH:
                return incoming_bar.high
            case enums.InputSource.LOW:
                return incoming_bar.low
            case enums.InputSource.CLOSE:
                return incoming_bar.close
            case enums.InputSource.VOLUME:
                return (
                    float(incoming_bar.volume)
                    if incoming_bar.volume is not None
                    else np.nan
                )
            case _:
                return incoming_bar.close
