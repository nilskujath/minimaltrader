import abc
import math
import uuid

from .core import Consumer, EventBus, Producer
from .indicators import Indicator, SimpleMovingAverage
from .models import enums, events, records


class Strategy(Consumer, Producer, abc.ABC):
    def __init__(
        self, symbols: list[str], bar_period: enums.BarPeriod, event_bus: EventBus
    ) -> None:
        Consumer.__init__(self)
        Producer.__init__(self, event_bus)
        self.symbols = symbols
        self.bar_period = bar_period
        self._indicators: dict[str, list[Indicator]] = {s: [] for s in symbols}
        self._fills: dict[str, list[records.FillRecord]] = {s: [] for s in symbols}
        self._submitted_orders: dict[uuid.UUID, records.OrderRecord] = {}
        self._pending_orders: dict[uuid.UUID, records.OrderRecord] = {}

    def on_event(self, incoming_event: events.Event) -> None:
        match incoming_event:
            case events.ReceivedNewBar() as event:
                self._update_indicators(event)
                self.on_bar(event)
            case events.AcceptedOrderSubmission() as event:
                self._handle_order_accepted(event)
            case events.AcceptedOrderModification():
                pass
            case events.AcceptedOrderCancellation() as event:
                self._handle_order_cancelled(event)
            case events.RejectedOrderSubmission() as event:
                self._handle_order_rejected(event)
            case (
                events.RejectedOrderModification()
                | events.RejectedOrderCancellation()
            ):
                pass
            case events.OrderFilled() as event:
                self._handle_order_filled(event)
            case events.OrderExpired() as event:
                self._handle_order_expired(event)

    def _update_indicators(self, event: events.ReceivedNewBar) -> None:
        for indicator in self._indicators.get(event.symbol, []):
            indicator.update(event)

    def _handle_order_accepted(self, event: events.AcceptedOrderSubmission) -> None:
        order = self._submitted_orders.pop(event.order_id, None)
        if order is not None:
            self._pending_orders[event.order_id] = order

    def _handle_order_rejected(self, event: events.RejectedOrderSubmission) -> None:
        self._submitted_orders.pop(event.order_id, None)

    def _handle_order_cancelled(self, event: events.AcceptedOrderCancellation) -> None:
        self._pending_orders.pop(event.order_id, None)

    def _handle_order_filled(self, event: events.OrderFilled) -> None:
        self._pending_orders.pop(event.associated_order_id, None)
        fill = records.FillRecord(
            fill_id=event.fill_id,
            order_id=event.associated_order_id,
            symbol=event.symbol,
            side=event.side,
            quantity=event.quantity_filled,
            price=event.fill_price,
            commission=event.commission,
            ts_event=event.ts_event,
        )
        self._fills.setdefault(event.symbol, []).append(fill)

    def _handle_order_expired(self, event: events.OrderExpired) -> None:
        self._pending_orders.pop(event.order_id, None)

    @abc.abstractmethod
    def on_bar(self, event: events.ReceivedNewBar) -> None:
        pass

    def submit_order(self, event: events.RequestOrderSubmission) -> None:
        order = records.OrderRecord(
            order_id=event.order_id,
            symbol=event.symbol,
            order_type=event.order_type,
            side=event.side,
            quantity=event.quantity,
            limit_price=event.limit_price,
            stop_price=event.stop_price,
        )
        self._submitted_orders[event.order_id] = order
        self.publish(event)

    def submit_modification(self, event: events.RequestOrderModification) -> None:
        self.publish(event)

    def submit_cancellation(self, event: events.RequestOrderCancellation) -> None:
        self.publish(event)

    def pending_orders(self, symbol: str | None = None) -> list[records.OrderRecord]:
        if symbol is None:
            return list(self._pending_orders.values())
        return [o for o in self._pending_orders.values() if o.symbol == symbol]

    def register_indicator(self, symbol: str, indicator: Indicator) -> Indicator:
        if symbol not in self._indicators:
            self._indicators[symbol] = []
        self._indicators[symbol].append(indicator)
        return indicator

    def shutdown(self) -> None:
        self.incoming_event_queue.put(None)
        self._thread.join()


class SMACrossover(Strategy):
    def __init__(
        self,
        symbol: str,
        fast_period: int,
        slow_period: int,
        quantity: float,
        event_bus: EventBus,
    ) -> None:
        super().__init__([symbol], enums.BarPeriod.DAY, event_bus)
        self._symbol = symbol
        self._quantity = quantity
        self._fast = self.register_indicator(symbol, SimpleMovingAverage(fast_period))
        self._slow = self.register_indicator(symbol, SimpleMovingAverage(slow_period))
        self._prev_fast: float = math.nan
        self._prev_slow: float = math.nan

    def on_bar(self, event: events.ReceivedNewBar) -> None:
        fast, slow = self._fast.latest, self._slow.latest
        if math.isnan(fast) or math.isnan(slow) or math.isnan(self._prev_fast):
            self._prev_fast, self._prev_slow = fast, slow
            return

        crossed_above = self._prev_fast <= self._prev_slow and fast > slow
        crossed_below = self._prev_fast >= self._prev_slow and fast < slow

        if crossed_above:
            self.submit_order(
                events.RequestOrderSubmission(
                    symbol=self._symbol,
                    order_type=enums.OrderType.MARKET,
                    side=enums.OrderSide.BUY,
                    quantity=self._quantity,
                )
            )
        elif crossed_below:
            self.submit_order(
                events.RequestOrderSubmission(
                    symbol=self._symbol,
                    order_type=enums.OrderType.MARKET,
                    side=enums.OrderSide.SELL,
                    quantity=self._quantity,
                )
            )

        self._prev_fast, self._prev_slow = fast, slow


class Trader:
    pass


class Bookkeeper:
    pass


class Chartist:
    pass
