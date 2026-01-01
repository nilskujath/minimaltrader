"""
Example usage of the Trader class for backtesting.

Run from the project root:
    poetry run python scripts/example_backtest.py
"""

from minimaltrader import brokers, datafeeds, desk, enums, strategies


class MyStrategy(strategies.SMACrossover):
    symbols = ["MNQZ4"]
    bar_period = enums.BarPeriod.MINUTE
    fast_period = 10
    slow_period = 30
    quantity = 1.0


class MyDatafeed(datafeeds.SimulatedDatafeed):
    csv_path = "market_data/glbx-mdp3-20241201-20241230.ohlcv-1m.csv"


def main() -> None:
    trader = desk.Trader()
    results_path = trader.trade(MyStrategy, brokers.SimulatedBroker, MyDatafeed)

    print("\n=== Backtest Complete ===")
    print(f"Results saved to: {results_path}")


if __name__ == "__main__":
    main()
