import abc
import collections
import queue
import threading

from .models import enums, events


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
