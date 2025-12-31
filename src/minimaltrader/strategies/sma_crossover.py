from ..core import EventBus
from ..indicators import SimpleMovingAverage
from ..models import enums, events
from .base import Strategy


class SMACrossover(Strategy):
    def __init__(
        self,
        symbols: list[str],
        event_bus: EventBus,
        fast_period: int = 10,
        slow_period: int = 30,
        quantity: float = 1.0,
    ) -> None:
        super().__init__(symbols, event_bus)
        self.fast = self.indicator(SimpleMovingAverage(period=fast_period))
        self.slow = self.indicator(SimpleMovingAverage(period=slow_period))
        self.quantity = quantity

    def on_bar(self, event: events.ReceivedNewBar) -> None:
        fast_val = self.fast.latest
        slow_val = self.slow.latest

        if fast_val != fast_val or slow_val != slow_val:
            return

        if fast_val > slow_val and self.position <= 0:
            self.submit_order(
                order_type=enums.OrderType.MARKET,
                side=enums.OrderSide.BUY,
                quantity=self.quantity,
            )

        elif fast_val < slow_val and self.position >= 0:
            self.submit_order(
                order_type=enums.OrderType.MARKET,
                side=enums.OrderSide.SELL,
                quantity=self.quantity,
            )
