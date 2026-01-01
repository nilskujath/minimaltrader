from __future__ import annotations

import abc
import collections
import threading
from typing import TYPE_CHECKING

import numpy as np

from ..models import events

if TYPE_CHECKING:
    from ..strategies import Strategy


class Indicator(abc.ABC):
    def __init__(self, max_history: int = 100, plot_at: int = 99) -> None:
        self._lock = threading.Lock()
        self._max_history = max(1, int(max_history))
        self._history: dict[str, collections.deque[float]] = {}
        self._strategy: Strategy | None = None
        self._plot_at = plot_at  # 0=main chart, 1-98=subcharts, 99=no plot

    @property
    @abc.abstractmethod
    def name(self) -> str:
        pass

    def update(self, incoming_bar: events.ReceivedNewBar) -> None:
        symbol = incoming_bar.symbol
        if symbol not in self._history:
            self._history[symbol] = collections.deque(maxlen=self._max_history)
        value = self._compute_indicator(incoming_bar)
        with self._lock:
            self._history[symbol].append(value)

    @abc.abstractmethod
    def _compute_indicator(self, incoming_bar: events.ReceivedNewBar) -> float:
        pass

    def _current_history(self) -> collections.deque[float]:
        if self._strategy is None:
            return collections.deque(maxlen=self._max_history)
        return self._history.get(
            self._strategy._current_symbol,
            collections.deque(maxlen=self._max_history),
        )

    @property
    def latest(self) -> float:
        with self._lock:
            history = self._current_history()
            return history[-1] if history else np.nan

    @property
    def history(self) -> collections.deque[float]:
        with self._lock:
            h = self._current_history()
            return collections.deque(h, maxlen=self._max_history)

    @property
    def plot_at(self) -> int:
        return self._plot_at
