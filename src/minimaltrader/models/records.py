import dataclasses
import uuid

import pandas as pd

from .enums import OrderType, OrderSide


@dataclasses.dataclass(kw_only=True, frozen=True)
class OrderRecord:
    order_id: uuid.UUID
    symbol: str
    order_type: OrderType
    side: OrderSide
    quantity: float
    limit_price: float | None = None
    stop_price: float | None = None


@dataclasses.dataclass(kw_only=True, frozen=True)
class FillRecord:
    fill_id: uuid.UUID
    order_id: uuid.UUID
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float
    ts_event: pd.Timestamp
