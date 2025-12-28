import abc
import dataclasses
import enum
import pandas as pd
import queue
import threading

from collections import defaultdict


class Models:

    class BarPeriod(enum.Enum):
        SECOND = 32
        MINUTE = 33
        HOUR = 34
        DAY = 35


class Events:

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class Event:
        ts_event: pd.Timestamp = dataclasses.field(
            default_factory=lambda: pd.Timestamp.now(tz="UTC")
        )

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class PoisonPill(Event):
        pass


class Consumer(abc.ABC):

    def __init__(self) -> None:
        self.incoming_event_queue: queue.Queue[Events.Event] = queue.Queue()
        self._thread: threading.Thread = threading.Thread(
            target=self._consume, name=self.__class__.__name__, daemon=False
        )
        self._thread.start()

    def receive(self, incoming_event: Events.Event) -> None:
        self.incoming_event_queue.put(incoming_event)

    def _consume(self) -> None:
        while True:
            incoming_event = self.incoming_event_queue.get()
            if isinstance(incoming_event, Events.PoisonPill):
                self.on_event(incoming_event)
                self.incoming_event_queue.task_done()
                break
            self.on_event(incoming_event)
            self.incoming_event_queue.task_done()

    @abc.abstractmethod
    def on_event(self, incoming_event: Events.Event) -> None:
        pass


class EventBus:

    def __init__(self) -> None:
        self._subscriptions: defaultdict[type[Events.Event], set[Consumer]] = (
            defaultdict(set)
        )
        self._consumers: set[Consumer] = set()
        self._lock: threading.Lock = threading.Lock()

    def subscribe(self, subscriber: Consumer, event_type: type[Events.Event]):
        with self._lock:
            self._consumers.add(subscriber)
            self._subscriptions[event_type].add(subscriber)
            self._subscriptions[Events.PoisonPill].add(subscriber)

    def unsubscribe(self, subscriber: Consumer):
        with self._lock:
            for consumer_set in self._subscriptions.values():
                consumer_set.discard(subscriber)
            self._consumers.discard(subscriber)

    def publish(self, event: Events.Event) -> None:
        with self._lock:
            consumers = self._subscriptions[type(event)].copy()
        for consumer in consumers:
            consumer.receive(event)

    def wait_for_all_consumers_to_finish(self) -> None:
        with self._lock:
            consumers = self._consumers.copy()
        for consumer in consumers:
            consumer.incoming_event_queue.join()


class Producer:

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def publish(self, event: Events.Event) -> None:
        self._event_bus.publish(event)


class Datafeeds:

    class Datafeed(Producer, abc.ABC):

        def __init__(self, event_bus: EventBus) -> None:
            super().__init__(event_bus)
            self._is_connected: bool = False
            self._watched_symbols: set[tuple[str, Models.BarPeriod]] = set()

        @abc.abstractmethod
        def watch(self, symbols: list[tuple[str, Models.BarPeriod]]) -> bool:
            pass

        @abc.abstractmethod
        def unwatch(self, symbols: list[str]) -> None:
            pass
