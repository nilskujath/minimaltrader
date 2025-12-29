import abc
import collections
import dataclasses
import enum
import logging
import numpy as np
import pandas as pd
import pathlib
import queue
import threading
import uuid


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(threadName)s - %(message)s",
)
logger = logging.getLogger("minimaltrader")


class Models:

    class BarPeriod(enum.Enum):
        SECOND = 32
        MINUTE = 33
        HOUR = 34
        DAY = 35

    class OrderType(enum.Enum):
        MARKET = enum.auto()
        LIMIT = enum.auto()
        STOP = enum.auto()
        STOP_LIMIT = enum.auto()

    class OrderSide(enum.Enum):
        BUY = enum.auto()
        SELL = enum.auto()

    class InputSource(enum.Enum):
        OPEN = enum.auto()
        HIGH = enum.auto()
        LOW = enum.auto()
        CLOSE = enum.auto()
        VOLUME = enum.auto()


class Records:

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class OrderRecord:
        order_id: uuid.UUID
        symbol: str
        order_type: Models.OrderType
        side: Models.OrderSide
        quantity: float
        limit_price: float | None = None
        stop_price: float | None = None

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class FillRecord:
        fill_id: uuid.UUID
        order_id: uuid.UUID
        symbol: str
        side: Models.OrderSide
        quantity: float
        price: float
        commission: float
        ts_event: pd.Timestamp


class Events:

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class Event:
        ts_event: pd.Timestamp = dataclasses.field(
            default_factory=lambda: pd.Timestamp.now(tz="UTC")
        )

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class ReceivedNewBar(Event):
        ts_event: pd.Timestamp
        symbol: str
        bar_period: Models.BarPeriod
        open: float
        high: float
        low: float
        close: float
        volume: int | None = None

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class RequestOrderSubmission(Event):
        order_id: uuid.UUID = dataclasses.field(default_factory=uuid.uuid4)
        symbol: str
        order_type: Models.OrderType
        side: Models.OrderSide
        quantity: float
        limit_price: float | None = None
        stop_price: float | None = None

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class RequestOrderModification(Event):
        symbol: str
        order_id: uuid.UUID
        quantity: float | None = None
        limit_price: float | None = None
        stop_price: float | None = None

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class RequestOrderCancellation(Event):
        symbol: str
        order_id: uuid.UUID

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class AcceptedOrderSubmission(Event):
        order_id: uuid.UUID
        broker_order_id: str | None = None

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class AcceptedOrderModification(Event):
        order_id: uuid.UUID
        broker_order_id: str | None = None

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class AcceptedOrderCancellation(Event):
        order_id: uuid.UUID

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class RejectedOrderSubmission(Event):
        order_id: uuid.UUID

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class RejectedOrderModification(Event):
        order_id: uuid.UUID

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class RejectedOrderCancellation(Event):
        order_id: uuid.UUID

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class OrderFilled(Event):
        fill_id: uuid.UUID = dataclasses.field(default_factory=uuid.uuid4)
        broker_fill_id: str | None = None
        associated_order_id: uuid.UUID
        symbol: str
        side: Models.OrderSide
        quantity_filled: float
        fill_price: float
        commission: float
        exchange: str = "SIMULATED"

    @dataclasses.dataclass(kw_only=True, frozen=True)
    class OrderExpired(Event):
        order_id: uuid.UUID


class SystemComponent(abc.ABC):

    @abc.abstractmethod
    def shutdown(self) -> None:
        pass


class Consumer(SystemComponent):

    def __init__(self) -> None:
        self.incoming_event_queue: queue.Queue[Events.Event | None] = queue.Queue()
        self._thread: threading.Thread = threading.Thread(
            target=self._consume, name=self.__class__.__name__, daemon=False
        )
        self._thread.start()

    def receive(self, incoming_event: Events.Event) -> None:
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
    def on_event(self, incoming_event: Events.Event) -> None:
        pass

    @abc.abstractmethod
    def shutdown(self) -> None:
        pass


class EventBus:

    def __init__(self) -> None:
        self._subscriptions: collections.defaultdict[
            type[Events.Event], set[Consumer]
        ] = collections.defaultdict(set)
        self._consumers: set[Consumer] = set()
        self._lock: threading.Lock = threading.Lock()

    def subscribe(self, subscriber: Consumer, event_type: type[Events.Event]):
        with self._lock:
            self._consumers.add(subscriber)
            self._subscriptions[event_type].add(subscriber)

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


class Producer(SystemComponent):

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def publish(self, event: Events.Event) -> None:
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

        def stream(self, symbols: list[str], bar_period: Models.BarPeriod) -> None:
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
        def _stream(self, symbols: list[str], bar_period: Models.BarPeriod) -> None:
            pass

    class SimulatedDatafeed(Datafeed):

        def __init__(self, event_bus: EventBus, csv_path: str | pathlib.Path) -> None:
            super().__init__(event_bus)
            self._csv_path = pathlib.Path(csv_path)

        def shutdown(self) -> None:
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join()

        def _stream(self, symbols: list[str], bar_period: Models.BarPeriod) -> None:
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
                    Events.ReceivedNewBar(
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


class Brokers:

    class Broker(Consumer, Producer, abc.ABC):

        def __init__(self, event_bus: EventBus) -> None:
            Consumer.__init__(self)
            Producer.__init__(self, event_bus)
            event_bus.subscribe(self, Events.RequestOrderSubmission)
            event_bus.subscribe(self, Events.RequestOrderCancellation)
            event_bus.subscribe(self, Events.RequestOrderModification)

        def on_event(self, incoming_event: Events.Event) -> None:
            match incoming_event:
                case Events.RequestOrderSubmission() as submit_order:
                    self.on_submit_order(submit_order)
                case Events.RequestOrderCancellation() as cancel_order:
                    self.on_cancel_order(cancel_order)
                case Events.RequestOrderModification() as modify_order:
                    self.on_modify_order(modify_order)

        @abc.abstractmethod
        def on_submit_order(self, event: Events.RequestOrderSubmission) -> None:
            pass

        @abc.abstractmethod
        def on_cancel_order(self, event: Events.RequestOrderCancellation) -> None:
            pass

        @abc.abstractmethod
        def on_modify_order(self, event: Events.RequestOrderModification) -> None:
            pass

    class SimulatedBroker(Broker):

        commission_per_unit: float = 0.0

        def __init__(self, event_bus: EventBus) -> None:
            super().__init__(event_bus)
            event_bus.subscribe(self, Events.ReceivedNewBar)

        def on_event(self, incoming_event: Events.Event) -> None:
            match incoming_event:
                case Events.ReceivedNewBar() as bar:
                    self.on_bar(bar)
                case _:
                    super().on_event(incoming_event)

        def on_bar(self, event: Events.ReceivedNewBar) -> None:
            pass

            self._pending_market_orders: dict[uuid.UUID, Records.OrderRecord] = {}
            self._pending_limit_orders: dict[uuid.UUID, Records.OrderRecord] = {}
            self._pending_stop_orders: dict[uuid.UUID, Records.OrderRecord] = {}
            self._pending_stop_limit_orders: dict[uuid.UUID, Records.OrderRecord] = {}

        def on_submit_order(self, event: Events.RequestOrderSubmission) -> None:
            order = Records.OrderRecord(
                order_id=event.order_id,
                symbol=event.symbol,
                order_type=event.order_type,
                side=event.side,
                quantity=event.quantity,
                limit_price=event.limit_price,
                stop_price=event.stop_price,
            )
            match order.order_type:
                case Models.OrderType.MARKET:
                    self._pending_market_orders[order.order_id] = order
                case Models.OrderType.LIMIT:
                    self._pending_limit_orders[order.order_id] = order
                case Models.OrderType.STOP:
                    self._pending_stop_orders[order.order_id] = order
                case Models.OrderType.STOP_LIMIT:
                    self._pending_stop_limit_orders[order.order_id] = order

            self.publish(Events.AcceptedOrderSubmission(order_id=order.order_id))

        def on_cancel_order(self, event: Events.RequestOrderCancellation) -> None:
            order = event.order_id
            removed = False

            for pending_orders in (
                self._pending_market_orders,
                self._pending_limit_orders,
                self._pending_stop_orders,
                self._pending_stop_limit_orders,
            ):
                if order in pending_orders:
                    del pending_orders[order]
                    removed = True
                    break

            if removed:
                self.publish(Events.AcceptedOrderCancellation(order_id=order))
            else:
                self.publish(Events.RejectedOrderCancellation(order_id=order))

        def on_modify_order(self, event: Events.RequestOrderModification) -> None:
            order_id = event.order_id

            for pending_orders in (
                self._pending_market_orders,
                self._pending_limit_orders,
                self._pending_stop_orders,
                self._pending_stop_limit_orders,
            ):
                if order_id in pending_orders:
                    order = pending_orders[order_id]
                    updates = {}
                    if event.quantity is not None:
                        updates["quantity"] = event.quantity
                    if event.limit_price is not None:
                        updates["limit_price"] = event.limit_price
                    if event.stop_price is not None:
                        updates["stop_price"] = event.stop_price

                    pending_orders[order_id] = dataclasses.replace(order, **updates)
                    self.publish(Events.AcceptedOrderModification(order_id=order_id))
                    return

            self.publish(Events.RejectedOrderModification(order_id=order_id))

        def shutdown(self) -> None:
            self.incoming_event_queue.put(None)
            self._thread.join()


class Indicators:

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

        def update(self, incoming_bar: Events.ReceivedNewBar) -> None:
            _latest_value: float = self._compute_indicator(incoming_bar)
            with self._lock:
                self._history.append(_latest_value)

        @abc.abstractmethod
        def _compute_indicator(self, incoming_bar: Events.ReceivedNewBar) -> float:
            pass

        @property
        def latest(self) -> float:
            with self._lock:
                return self._history[-1] if self._history else np.nan

        @property
        def history(self) -> collections.deque[float]:
            with self._lock:
                return collections.deque(self._history, maxlen=self._history.maxlen)

    class SimpleMovingAverage(Indicator):
        def __init__(
            self,
            period: int = 200,
            max_history: int = 100,
            input_source: Models.InputSource = Models.InputSource.CLOSE,
        ) -> None:
            super().__init__(max_history=max_history)
            self.period: int = max(1, int(period))
            self.input_source: Models.InputSource = input_source
            self._window: collections.deque[float] = collections.deque(
                maxlen=self.period
            )

        @property
        def name(self) -> str:
            return f"SMA_{self.period}_{self.input_source.name}"

        def _compute_indicator(self, incoming_bar: Events.ReceivedNewBar) -> float:
            value: float = self._extract_input(incoming_bar)
            self._window.append(value)
            if len(self._window) < self.period:
                return np.nan
            return sum(self._window) / self.period

        def _extract_input(self, incoming_bar: Events.ReceivedNewBar) -> float:
            match self.input_source:
                case Models.InputSource.OPEN:
                    return incoming_bar.open
                case Models.InputSource.HIGH:
                    return incoming_bar.high
                case Models.InputSource.LOW:
                    return incoming_bar.low
                case Models.InputSource.CLOSE:
                    return incoming_bar.close
                case Models.InputSource.VOLUME:
                    return (
                        float(incoming_bar.volume)
                        if incoming_bar.volume is not None
                        else np.nan
                    )
                case _:
                    return incoming_bar.close


class Strategy(Consumer, abc.ABC):

    def __init__(self, symbols: list[str], bar_period: Models.BarPeriod) -> None:
        super().__init__()
        self.symbols = symbols
        self.bar_period = bar_period

    def on_event(self, incoming_event: Events.Event) -> None:
        if isinstance(incoming_event, Events.ReceivedNewBar):
            self.on_bar(incoming_event)

    @abc.abstractmethod
    def on_bar(self, bar: Events.ReceivedNewBar) -> None:
        pass

    def shutdown(self) -> None:
        self.incoming_event_queue.put(None)
        self._thread.join()


class Trader:
    pass