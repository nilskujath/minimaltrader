import dataclasses
import uuid

from ..core import EventBus
from ..models import enums, events, records
from .base import Broker


class SimulatedBroker(Broker):

    commission_per_unit: float = 0.0
    minimum_commission_per_order: float = 0.0

    def __init__(self, event_bus: EventBus) -> None:
        super().__init__(event_bus)
        event_bus.subscribe(self, events.ReceivedNewBar)

        self._pending_market_orders: dict[uuid.UUID, records.OrderRecord] = {}
        self._pending_limit_orders: dict[uuid.UUID, records.OrderRecord] = {}
        self._pending_stop_orders: dict[uuid.UUID, records.OrderRecord] = {}
        self._pending_stop_limit_orders: dict[uuid.UUID, records.OrderRecord] = {}

    def on_event(self, incoming_event: events.Event) -> None:
        match incoming_event:
            case events.ReceivedNewBar() as bar:
                self.on_bar(bar)
            case _:
                super().on_event(incoming_event)

    def on_bar(self, event: events.ReceivedNewBar) -> None:
        self._process_market_orders(event)
        self._process_stop_orders(event)
        self._process_stop_limit_orders(event)
        self._process_limit_orders(event)  # must process after stop limit orders

    def _process_market_orders(self, event: events.ReceivedNewBar) -> None:
        for order_id, order in list(self._pending_market_orders.items()):
            if order.symbol != event.symbol:
                continue

            self.publish(
                events.OrderFilled(
                    ts_event=event.ts_event,
                    associated_order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity_filled=order.quantity,
                    fill_price=event.open,
                    commission=max(
                        order.quantity * self.commission_per_unit,
                        self.minimum_commission_per_order,
                    ),
                )
            )
            del self._pending_market_orders[order_id]

    def _process_stop_orders(self, event: events.ReceivedNewBar) -> None:
        for order_id, order in list(self._pending_stop_orders.items()):
            if order.symbol != event.symbol:
                continue

            triggered = False
            match order.side:
                case enums.OrderSide.BUY:
                    triggered = event.high >= order.stop_price
                case enums.OrderSide.SELL:
                    triggered = event.low <= order.stop_price

            if not triggered:
                continue

            fill_price = 0.0
            match order.side:
                case enums.OrderSide.BUY:
                    fill_price = max(order.stop_price, event.open)
                case enums.OrderSide.SELL:
                    fill_price = min(order.stop_price, event.open)

            self.publish(
                events.OrderFilled(
                    ts_event=event.ts_event,
                    associated_order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity_filled=order.quantity,
                    fill_price=fill_price,
                    commission=max(
                        order.quantity * self.commission_per_unit,
                        self.minimum_commission_per_order,
                    ),
                )
            )
            del self._pending_stop_orders[order_id]

    def _process_stop_limit_orders(self, event: events.ReceivedNewBar) -> None:
        for order_id, order in list(self._pending_stop_limit_orders.items()):
            if order.symbol != event.symbol:
                continue

            triggered = False
            match order.side:
                case enums.OrderSide.BUY:
                    triggered = event.high >= order.stop_price
                case enums.OrderSide.SELL:
                    triggered = event.low <= order.stop_price

            if not triggered:
                continue

            limit_order = dataclasses.replace(order, order_type=enums.OrderType.LIMIT)
            self._pending_limit_orders[order_id] = limit_order
            del self._pending_stop_limit_orders[order_id]

    def _process_limit_orders(self, event: events.ReceivedNewBar) -> None:
        for order_id, order in list(self._pending_limit_orders.items()):
            if order.symbol != event.symbol:
                continue

            triggered = False
            match order.side:
                case enums.OrderSide.BUY:
                    triggered = event.low <= order.limit_price
                case enums.OrderSide.SELL:
                    triggered = event.high >= order.limit_price

            if not triggered:
                continue

            fill_price = 0.0
            match order.side:
                case enums.OrderSide.BUY:
                    fill_price = min(order.limit_price, event.open)
                case enums.OrderSide.SELL:
                    fill_price = max(order.limit_price, event.open)

            self.publish(
                events.OrderFilled(
                    ts_event=event.ts_event,
                    associated_order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity_filled=order.quantity,
                    fill_price=fill_price,
                    commission=max(
                        order.quantity * self.commission_per_unit,
                        self.minimum_commission_per_order,
                    ),
                )
            )
            del self._pending_limit_orders[order_id]

    def _reject_invalid_order(self, event: events.RequestOrderSubmission) -> bool:
        match event.order_type:
            case _ if event.quantity <= 0:
                self.publish(events.RejectedOrderSubmission(order_id=event.order_id))
                return True
            case enums.OrderType.LIMIT if event.limit_price is None:
                self.publish(events.RejectedOrderSubmission(order_id=event.order_id))
                return True
            case enums.OrderType.STOP if event.stop_price is None:
                self.publish(events.RejectedOrderSubmission(order_id=event.order_id))
                return True
            case enums.OrderType.STOP_LIMIT if (
                event.limit_price is None or event.stop_price is None
            ):
                self.publish(events.RejectedOrderSubmission(order_id=event.order_id))
                return True
        return False

    def on_submit_order(self, event: events.RequestOrderSubmission) -> None:
        if self._reject_invalid_order(event):
            return

        order = records.OrderRecord(
            order_id=event.order_id,
            symbol=event.symbol,
            order_type=event.order_type,
            side=event.side,
            quantity=event.quantity,
            limit_price=event.limit_price,
            stop_price=event.stop_price,
        )
        match order.order_type:
            case enums.OrderType.MARKET:
                self._pending_market_orders[order.order_id] = order
            case enums.OrderType.LIMIT:
                self._pending_limit_orders[order.order_id] = order
            case enums.OrderType.STOP:
                self._pending_stop_orders[order.order_id] = order
            case enums.OrderType.STOP_LIMIT:
                self._pending_stop_limit_orders[order.order_id] = order

        self.publish(events.AcceptedOrderSubmission(order_id=order.order_id))

    def on_cancel_order(self, event: events.RequestOrderCancellation) -> None:
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
            self.publish(events.AcceptedOrderCancellation(order_id=order))
        else:
            self.publish(events.RejectedOrderCancellation(order_id=order))

    def on_modify_order(self, event: events.RequestOrderModification) -> None:
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
                self.publish(events.AcceptedOrderModification(order_id=order_id))
                return

        self.publish(events.RejectedOrderModification(order_id=order_id))

    def shutdown(self) -> None:
        self.incoming_event_queue.put(None)
        self._thread.join()
