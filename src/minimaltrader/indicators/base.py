import abc
import collections
import threading

import numpy as np

from ..models import events


class Indicator(abc.ABC):
    def __init__(self, max_history: int = 100) -> None:
        self._lock = threading.Lock()
        self._history: collections.deque[float] = collections.deque(
            maxlen=max(1, int(max_history))
        )

    @property
    @abc.abstractmethod
    def name(self) -> str:
        pass

    def update(self, incoming_bar: events.ReceivedNewBar) -> None:
        _latest_value: float = self._compute_indicator(incoming_bar)
        with self._lock:
            self._history.append(_latest_value)

    @abc.abstractmethod
    def _compute_indicator(self, incoming_bar: events.ReceivedNewBar) -> float:
        pass

    @property
    def latest(self) -> float:
        with self._lock:
            return self._history[-1] if self._history else np.nan

    @property
    def history(self) -> collections.deque[float]:
        with self._lock:
            return collections.deque(self._history, maxlen=self._history.maxlen)
