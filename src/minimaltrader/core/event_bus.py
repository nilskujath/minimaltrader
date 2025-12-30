from __future__ import annotations

import collections
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .consumer import Consumer

from ..models import events


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
