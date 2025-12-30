import abc
import collections
import logging
import pathlib
import queue
import threading

import pandas as pd

from .models import enums, events

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(threadName)s - %(message)s",
)
logger = logging.getLogger("minimaltrader")


class SystemComponent(abc.ABC):

    @abc.abstractmethod
    def shutdown(self) -> None:
        pass


class Consumer(SystemComponent):

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


class EventBus:

    def __init__(self) -> None:
        self._subscriptions: collections.defaultdict[
            type[events.Event], set[Consumer]
        ] = collections.defaultdict(set)
        self._consumers: set[Consumer] = set()
        self._lock: threading.Lock = threading.Lock()

    def subscribe(self, subscriber: Consumer, event_type: type[events.Event]):
        with self._lock:
            self._consumers.add(subscriber)
            self._subscriptions[event_type].add(subscriber)

    def unsubscribe(self, subscriber: Consumer):
        with self._lock:
            for consumer_set in self._subscriptions.values():
                consumer_set.discard(subscriber)
            self._consumers.discard(subscriber)

    def publish(self, event: events.Event) -> None:
        with self._lock:
            consumers = self._subscriptions[type(event)].copy()
        for consumer in consumers:
            consumer.receive(event)

    def wait_for_all_consumers_to_finish(self) -> None:
        with self._lock:
            consumers = self._consumers.copy()
        for consumer in consumers:
            consumer.incoming_event_queue.join()


class Producer(SystemComponent):

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def publish(self, event: events.Event) -> None:
        self._event_bus.publish(event)

    @abc.abstractmethod
    def shutdown(self) -> None:
        pass


class Datafeeds:

    class Datafeed(Producer):

        def __init__(self, event_bus: EventBus) -> None:
            super().__init__(event_bus)
            self._thread: threading.Thread | None = None
            self._stop_event = threading.Event()

        def stream(self, symbols: list[str], bar_period: enums.BarPeriod) -> None:
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._stream,
                args=(symbols, bar_period),
                name=self.__class__.__name__,
                daemon=False,
            )
            self._thread.start()

        @abc.abstractmethod
        def shutdown(self) -> None:
            pass

        @abc.abstractmethod
        def _stream(self, symbols: list[str], bar_period: enums.BarPeriod) -> None:
            pass

    class SimulatedDatafeed(Datafeed):

        def __init__(self, event_bus: EventBus, csv_path: str | pathlib.Path) -> None:
            super().__init__(event_bus)
            self._csv_path = pathlib.Path(csv_path)

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
                chunksize=1,
            ):
                if self._stop_event.is_set():
                    break

                row = chunk.iloc[0]
                if row["symbol"] not in symbols_set or row["rtype"] != rtype:
                    continue

                self._event_bus.publish(
                    events.ReceivedNewBar(
                        ts_event=pd.Timestamp(row["ts_event"], unit="ns", tz="UTC"),
                        symbol=row["symbol"],
                        bar_period=bar_period,
                        open=row["open"] / 1e9,
                        high=row["high"] / 1e9,
                        low=row["low"] / 1e9,
                        close=row["close"] / 1e9,
                        volume=row["volume"],
                    )
                )
                self._event_bus.wait_for_all_consumers_to_finish()


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
