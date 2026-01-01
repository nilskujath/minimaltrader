import abc
import uuid
from types import SimpleNamespace

from ..core import Consumer, EventBus, Producer
from ..indicators import Close, High, Indicator, Low, Open, Volume
from ..models import enums, events, records


class Strategy(Consumer, Producer, abc.ABC):
    symbols: list[str] = []
    bar_period: enums.BarPeriod = enums.BarPeriod.MINUTE

    def __init__(self, event_bus: EventBus) -> None:
        Consumer.__init__(self)
        Producer.__init__(self, event_bus)
        event_bus.subscribe(
            self,
            events.ReceivedNewBar,
            events.AcceptedOrderSubmission,
            events.AcceptedOrderModification,
            events.AcceptedOrderCancellation,
            events.RejectedOrderSubmission,
            events.RejectedOrderModification,
            events.RejectedOrderCancellation,
            events.OrderFilled,
            events.OrderExpired,
        )

        self._current_symbol: str = ""
        self._indicators: list[Indicator] = []

        self._fills: dict[str, list[records.FillRecord]] = {}
        self._positions: dict[str, float] = {}
        self._avg_prices: dict[str, float] = {}
        self._pending_orders: dict[uuid.UUID, records.OrderRecord] = {}
        self._submitted_orders: dict[uuid.UUID, records.OrderRecord] = {}
        self._submitted_modifications: dict[uuid.UUID, records.OrderRecord] = {}
        self._submitted_cancellations: dict[uuid.UUID, records.OrderRecord] = {}

        self.bar = SimpleNamespace(
            open=self.indicator(Open()),
            high=self.indicator(High()),
            low=self.indicator(Low()),
            close=self.indicator(Close()),
            volume=self.indicator(Volume()),
        )

        self.setup()

    def indicator(self, ind: Indicator) -> Indicator:
        ind._strategy = self
        self._indicators.append(ind)
        return ind

    @property
    def position(self) -> float:
        return self._positions.get(self._current_symbol, 0.0)

    @property
    def avg_price(self) -> float:
        return self._avg_prices.get(self._current_symbol, 0.0)

    def submit_order(
        self,
        order_type: enums.OrderType,
        side: enums.OrderSide,
        quantity: float,
        limit_price: float | None = None,
        stop_price: float | None = None,
    ) -> uuid.UUID:
        event = events.RequestOrderSubmission(
            symbol=self._current_symbol,
            order_type=order_type,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            stop_price=stop_price,
        )
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
        return event.order_id

    def submit_modification(
        self,
        order_id: uuid.UUID,
        quantity: float | None = None,
        limit_price: float | None = None,
        stop_price: float | None = None,
    ) -> bool:
        original_order = self._pending_orders.get(order_id)
        if original_order is None:
            return False

        event = events.RequestOrderModification(
            symbol=original_order.symbol,
            order_id=order_id,
            quantity=quantity,
            limit_price=limit_price,
            stop_price=stop_price,
        )
        self.publish(event)
        modified_order = records.OrderRecord(
            order_id=order_id,
            symbol=original_order.symbol,
            order_type=original_order.order_type,
            side=original_order.side,
            quantity=quantity if quantity is not None else original_order.quantity,
            limit_price=(
                limit_price if limit_price is not None else original_order.limit_price
            ),
            stop_price=(
                stop_price if stop_price is not None else original_order.stop_price
            ),
        )
        self._submitted_modifications[order_id] = modified_order
        return True

    def submit_cancellation(self, order_id: uuid.UUID) -> bool:
        original_order = self._pending_orders.get(order_id)
        if original_order is None:
            return False

        event = events.RequestOrderCancellation(
            symbol=original_order.symbol,
            order_id=order_id,
        )
        self.publish(event)
        self._submitted_cancellations[order_id] = original_order
        return True

    def on_event(self, incoming_event: events.Event) -> None:
        match incoming_event:
            case events.ReceivedNewBar() as event:
                self._on_received_new_bar(event)
            case events.AcceptedOrderSubmission() as event:
                self._on_accepted_order_submission(event)
            case events.AcceptedOrderModification() as event:
                self._on_accepted_order_modification(event)
            case events.AcceptedOrderCancellation() as event:
                self._on_accepted_order_cancellation(event)
            case events.RejectedOrderSubmission() as event:
                self._on_rejected_order_submission(event)
            case events.RejectedOrderModification() as event:
                self._on_rejected_order_modification(event)
            case events.RejectedOrderCancellation() as event:
                self._on_rejected_order_cancellation(event)
            case events.OrderFilled() as event:
                self._on_order_filled(event)
            case events.OrderExpired() as event:
                self._on_order_expired(event)

    def _on_received_new_bar(self, event: events.ReceivedNewBar) -> None:
        self._current_symbol = event.symbol
        for ind in self._indicators:
            ind.update(event)
        self.on_bar(event)

    def _on_accepted_order_submission(
        self, event: events.AcceptedOrderSubmission
    ) -> None:
        order = self._submitted_orders.pop(event.order_id, None)
        if order is not None:
            self._pending_orders[event.order_id] = order

    def _on_accepted_order_modification(
        self, event: events.AcceptedOrderModification
    ) -> None:
        modified_order = self._submitted_modifications.pop(event.order_id, None)
        if modified_order is not None:
            self._pending_orders[event.order_id] = modified_order

    def _on_accepted_order_cancellation(
        self, event: events.AcceptedOrderCancellation
    ) -> None:
        self._submitted_cancellations.pop(event.order_id, None)
        self._pending_orders.pop(event.order_id, None)

    def _on_rejected_order_submission(
        self, event: events.RejectedOrderSubmission
    ) -> None:
        self._submitted_orders.pop(event.order_id, None)

    def _on_rejected_order_modification(
        self, event: events.RejectedOrderModification
    ) -> None:
        self._submitted_modifications.pop(event.order_id, None)

    def _on_rejected_order_cancellation(
        self, event: events.RejectedOrderCancellation
    ) -> None:
        self._submitted_cancellations.pop(event.order_id, None)

    def _on_order_filled(self, event: events.OrderFilled) -> None:
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
        self._update_position(event)

    def _update_position(self, event: events.OrderFilled) -> None:
        symbol = event.symbol
        fill_qty = event.quantity_filled
        fill_price = event.fill_price

        signed_qty = 0.0
        match event.side:
            case enums.OrderSide.BUY:
                signed_qty = fill_qty
            case enums.OrderSide.SELL:
                signed_qty = -fill_qty

        old_pos = self._positions.get(symbol, 0.0)
        old_avg = self._avg_prices.get(symbol, 0.0)
        new_pos = old_pos + signed_qty

        if new_pos == 0.0:
            new_avg = 0.0
        elif old_pos == 0.0:
            new_avg = fill_price
        elif (old_pos > 0 and signed_qty > 0) or (old_pos < 0 and signed_qty < 0):
            new_avg = (old_avg * abs(old_pos) + fill_price * abs(signed_qty)) / abs(
                new_pos
            )
        else:
            if abs(new_pos) <= abs(old_pos):
                new_avg = old_avg
            else:
                new_avg = fill_price

        self._positions[symbol] = new_pos
        self._avg_prices[symbol] = new_avg

    def _on_order_expired(self, event: events.OrderExpired) -> None:
        self._pending_orders.pop(event.order_id, None)

    def shutdown(self) -> None:
        self.incoming_event_queue.put(None)
        self._thread.join()

    def setup(self) -> None:
        pass

    @abc.abstractmethod
    def on_bar(self, event: events.ReceivedNewBar) -> None:
        pass
