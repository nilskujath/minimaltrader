import pathlib
import uuid
from datetime import datetime

from ..brokers import Broker
from ..core import EventBus
from ..datafeeds import Datafeed
from ..strategies import Strategy
from .bookkeeper import Bookkeeper


class Trader:
    def __init__(self, results_dir: str = "results") -> None:
        self._results_base_dir = pathlib.Path(results_dir)
        self._event_bus: EventBus | None = None
        self._datafeed: Datafeed | None = None
        self._broker: Broker | None = None
        self._strategy: Strategy | None = None
        self._bookkeeper: Bookkeeper | None = None

    def trade(
        self,
        strategy_cls: type[Strategy],
        broker_cls: type[Broker],
        datafeed_cls: type[Datafeed],
    ) -> pathlib.Path:
        if not strategy_cls.symbols:
            raise ValueError("Strategy must define symbols")

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        session_id = str(uuid.uuid4())[:8]
        results_path = self._results_base_dir / f"results-{timestamp}-{session_id}"
        results_path.mkdir(parents=True, exist_ok=True)

        self._event_bus = EventBus()
        self._bookkeeper = Bookkeeper(self._event_bus, results_path)
        self._datafeed = datafeed_cls(self._event_bus)
        self._broker = broker_cls(self._event_bus)
        self._strategy = strategy_cls(self._event_bus)

        self._datafeed.stream(self._strategy.symbols, self._strategy.bar_period)
        self._datafeed.wait()
        self.stop()

        return results_path

    def stop(self) -> None:
        if self._datafeed:
            self._datafeed.shutdown()
        if self._broker:
            self._broker.shutdown()
        if self._strategy:
            self._strategy.shutdown()
        if self._bookkeeper:
            self._bookkeeper.shutdown()
