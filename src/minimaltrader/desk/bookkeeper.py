import pathlib

import pandas as pd

from ..core import Consumer, EventBus
from ..models import events


class Bookkeeper(Consumer):
    BATCH_SIZE = 1000

    def __init__(self, event_bus: EventBus, results_path: pathlib.Path) -> None:
        self._results_path = results_path
        self._bars_buffer: list[dict] = []
        self._fills_buffer: list[dict] = []
        self._orders_buffer: list[dict] = []

        Consumer.__init__(self)
        event_bus.subscribe(
            self,
            events.ReceivedNewBar,
            events.OrderFilled,
            events.RequestOrderSubmission,
            events.RequestOrderModification,
            events.RequestOrderCancellation,
            events.AcceptedOrderSubmission,
            events.AcceptedOrderModification,
            events.AcceptedOrderCancellation,
            events.RejectedOrderSubmission,
            events.RejectedOrderModification,
            events.RejectedOrderCancellation,
            events.OrderExpired,
        )

    def on_event(self, incoming_event: events.Event) -> None:
        match incoming_event:
            case events.ReceivedNewBar() as event:
                self._on_bar(event)
            case events.OrderFilled() as event:
                self._on_fill(event)
            case events.RequestOrderSubmission() as event:
                self._on_order_event(event, "submission_requested")
            case events.RequestOrderModification() as event:
                self._on_order_event(event, "modification_requested")
            case events.RequestOrderCancellation() as event:
                self._on_order_event(event, "cancellation_requested")
            case events.AcceptedOrderSubmission() as event:
                self._on_order_event(event, "submission_accepted")
            case events.AcceptedOrderModification() as event:
                self._on_order_event(event, "modification_accepted")
            case events.AcceptedOrderCancellation() as event:
                self._on_order_event(event, "cancellation_accepted")
            case events.RejectedOrderSubmission() as event:
                self._on_order_event(event, "submission_rejected")
            case events.RejectedOrderModification() as event:
                self._on_order_event(event, "modification_rejected")
            case events.RejectedOrderCancellation() as event:
                self._on_order_event(event, "cancellation_rejected")
            case events.OrderExpired() as event:
                self._on_order_event(event, "expired")

    def _on_bar(self, event: events.ReceivedNewBar) -> None:
        self._bars_buffer.append(
            {
                "ts_event": event.ts_event,
                "symbol": event.symbol,
                "bar_period": event.bar_period.name,
                "open": event.open,
                "high": event.high,
                "low": event.low,
                "close": event.close,
                "volume": event.volume,
            }
        )
        if len(self._bars_buffer) >= self.BATCH_SIZE:
            self._flush_bars()

    def _on_fill(self, event: events.OrderFilled) -> None:
        self._fills_buffer.append(
            {
                "ts_event": event.ts_event,
                "fill_id": str(event.fill_id),
                "broker_fill_id": event.broker_fill_id,
                "order_id": str(event.associated_order_id),
                "symbol": event.symbol,
                "side": event.side.name,
                "quantity": event.quantity_filled,
                "price": event.fill_price,
                "commission": event.commission,
                "exchange": event.exchange,
            }
        )
        if len(self._fills_buffer) >= self.BATCH_SIZE:
            self._flush_fills()

    def _on_order_event(self, event: events.Event, event_type: str) -> None:
        record: dict = {
            "ts_event": event.ts_event,
            "event_type": event_type,
        }
        match event:
            case events.RequestOrderSubmission():
                record.update(
                    {
                        "order_id": str(event.order_id),
                        "symbol": event.symbol,
                        "order_type": event.order_type.name,
                        "side": event.side.name,
                        "quantity": event.quantity,
                        "limit_price": event.limit_price,
                        "stop_price": event.stop_price,
                    }
                )
            case events.RequestOrderModification():
                record.update(
                    {
                        "order_id": str(event.order_id),
                        "symbol": event.symbol,
                        "quantity": event.quantity,
                        "limit_price": event.limit_price,
                        "stop_price": event.stop_price,
                    }
                )
            case events.RequestOrderCancellation():
                record.update(
                    {
                        "order_id": str(event.order_id),
                        "symbol": event.symbol,
                    }
                )
            case events.AcceptedOrderSubmission() | events.AcceptedOrderModification():
                record.update(
                    {
                        "order_id": str(event.order_id),
                        "broker_order_id": event.broker_order_id,
                    }
                )
            case events.AcceptedOrderCancellation():
                record.update({"order_id": str(event.order_id)})
            case (
                events.RejectedOrderSubmission()
                | events.RejectedOrderModification()
                | events.RejectedOrderCancellation()
            ):
                record.update({"order_id": str(event.order_id)})
            case events.OrderExpired():
                record.update({"order_id": str(event.order_id)})

        self._orders_buffer.append(record)
        if len(self._orders_buffer) >= self.BATCH_SIZE:
            self._flush_orders()

    def _flush_bars(self) -> None:
        if not self._bars_buffer:
            return
        df = pd.DataFrame(self._bars_buffer)
        path = self._results_path / "bars.csv"
        df.to_csv(path, mode="a", header=not path.exists(), index=False)
        self._bars_buffer.clear()

    def _flush_fills(self) -> None:
        if not self._fills_buffer:
            return
        df = pd.DataFrame(self._fills_buffer)
        path = self._results_path / "fills.csv"
        df.to_csv(path, mode="a", header=not path.exists(), index=False)
        self._fills_buffer.clear()

    def _flush_orders(self) -> None:
        if not self._orders_buffer:
            return
        df = pd.DataFrame(self._orders_buffer)
        path = self._results_path / "orders.csv"
        df.to_csv(path, mode="a", header=not path.exists(), index=False)
        self._orders_buffer.clear()

    def shutdown(self) -> None:
        self.incoming_event_queue.put(None)
        self._thread.join()
        self._flush_bars()
        self._flush_fills()
        self._flush_orders()
