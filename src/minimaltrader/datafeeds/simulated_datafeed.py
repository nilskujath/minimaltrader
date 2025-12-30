import pathlib
import threading

import pandas as pd

from ..core import EventBus
from ..models import enums, events
from .base import Datafeed


class SimulatedDatafeed(Datafeed):
    def __init__(self, event_bus: EventBus, csv_path: str | pathlib.Path) -> None:
        super().__init__(event_bus)
        self._csv_path = pathlib.Path(csv_path)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def stream(self, symbols: list[str], bar_period: enums.BarPeriod) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Already streaming")
        if not self._csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self._csv_path}")
        if not symbols:
            raise ValueError("symbols list cannot be empty")

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._stream,
            args=(symbols, bar_period),
            name=self.__class__.__name__,
            daemon=False,
        )
        self._thread.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join()

    def _stream(self, symbols: list[str], bar_period: enums.BarPeriod) -> None:
        symbols_set = set(symbols)
        rtype = bar_period.value

        for chunk in pd.read_csv(
            self._csv_path,
            usecols=[
                "ts_event",
                "rtype",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "symbol",
            ],
            dtype={
                "ts_event": int,
                "rtype": int,
                "open": int,
                "high": int,
                "low": int,
                "close": int,
                "volume": int,
                "symbol": str,
            },
            chunksize=10_000,
        ):
            for row in chunk.itertuples():
                if self._stop_event.is_set():
                    return

                if row.symbol not in symbols_set or row.rtype != rtype:
                    continue

                self._event_bus.publish(
                    events.ReceivedNewBar(
                        ts_event=pd.Timestamp(row.ts_event, unit="ns", tz="UTC"),
                        symbol=row.symbol,
                        bar_period=bar_period,
                        open=row.open / 1e9,
                        high=row.high / 1e9,
                        low=row.low / 1e9,
                        close=row.close / 1e9,
                        volume=row.volume,
                    )
                )
                self._event_bus.wait_for_all_consumers_to_finish()
