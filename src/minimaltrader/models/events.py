import dataclasses
import uuid

import pandas as pd

from .enums import BarPeriod, OrderType, OrderSide


@dataclasses.dataclass(kw_only=True, frozen=True)
class Event:
    ts_event: pd.Timestamp = dataclasses.field(
        default_factory=lambda: pd.Timestamp.now(tz="UTC")
    )


@dataclasses.dataclass(kw_only=True, frozen=True)
class ReceivedNewBar(Event):
    ts_event: pd.Timestamp
    symbol: str
    bar_period: BarPeriod
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None


@dataclasses.dataclass(kw_only=True, frozen=True)
class RequestOrderSubmission(Event):
    order_id: uuid.UUID = dataclasses.field(default_factory=uuid.uuid4)
    symbol: str
    order_type: OrderType
    side: OrderSide
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
    side: OrderSide
    quantity_filled: float
    fill_price: float
    commission: float
    exchange: str = "SIMULATED"


@dataclasses.dataclass(kw_only=True, frozen=True)
class OrderExpired(Event):
    order_id: uuid.UUID
