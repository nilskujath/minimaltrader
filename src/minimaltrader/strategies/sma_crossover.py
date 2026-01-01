from ..indicators import SimpleMovingAverage
from ..models import enums, events
from .base import Strategy


class SMACrossover(Strategy):
    symbols: list[str] = []
    bar_period: enums.BarPeriod = enums.BarPeriod.MINUTE
    fast_period: int = 10
    slow_period: int = 30
    quantity: float = 1.0

    def setup(self) -> None:
        self.fast = self.indicator(SimpleMovingAverage(period=self.fast_period))
        self.slow = self.indicator(SimpleMovingAverage(period=self.slow_period))

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
