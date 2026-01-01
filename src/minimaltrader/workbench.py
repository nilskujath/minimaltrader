import pathlib
import shutil
from dataclasses import dataclass
from enum import Enum

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from .indicators import Indicator


class ChartMode(Enum):
    TRADES = "trades"
    PRICE_ACTION = "price_action"


@dataclass
class TradeInfo:
    """Represents a trade extracted from fills data."""

    trade_id: int
    symbol: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    side: str  # "BUY" or "SELL"
    quantity: float
    pnl: float
    entry_fills: list
    exit_fills: list


class Chartist:
    """Generates charts from backtest results stored in CSV files."""

    def __init__(
        self,
        results_path: str | pathlib.Path,
        indicators: list[Indicator] | None = None,
    ) -> None:
        self._results_path = pathlib.Path(results_path)
        self._indicators = indicators or []
        self._bars_df: pd.DataFrame | None = None
        self._fills_df: pd.DataFrame | None = None
        self._trades: list[TradeInfo] = []
        self._load_data()

    def _load_data(self) -> None:
        """Load bars and fills data from CSV files."""
        bars_path = self._results_path / "bars.csv"
        fills_path = self._results_path / "fills.csv"

        if bars_path.exists():
            self._bars_df = pd.read_csv(bars_path)
            self._bars_df["ts_event"] = pd.to_datetime(self._bars_df["ts_event"])
            self._bars_df = self._bars_df.sort_values("ts_event").reset_index(drop=True)

        if fills_path.exists():
            self._fills_df = pd.read_csv(fills_path)
            self._fills_df["ts_event"] = pd.to_datetime(self._fills_df["ts_event"])
            self._fills_df = self._fills_df.sort_values("ts_event").reset_index(
                drop=True
            )
            self._extract_trades()

    def _extract_trades(self) -> None:
        """Extract trades from fills data by pairing entries and exits."""
        if self._fills_df is None or self._fills_df.empty:
            return

        self._trades = []
        symbols = self._fills_df["symbol"].unique()

        for symbol in symbols:
            symbol_fills = self._fills_df[self._fills_df["symbol"] == symbol].copy()
            position = 0.0
            entry_fills = []
            trade_id = 0

            for _, fill in symbol_fills.iterrows():
                qty = fill["quantity"]
                side = fill["side"]
                signed_qty = qty if side == "BUY" else -qty
                new_position = position + signed_qty

                if position == 0.0:
                    entry_fills = [fill]
                elif (position > 0 and signed_qty > 0) or (
                    position < 0 and signed_qty < 0
                ):
                    entry_fills.append(fill)
                elif new_position == 0.0:
                    trade_id += 1
                    entry_price = sum(
                        f["price"] * f["quantity"] for f in entry_fills
                    ) / sum(f["quantity"] for f in entry_fills)
                    exit_price = fill["price"]
                    entry_qty = sum(f["quantity"] for f in entry_fills)
                    trade_side = "BUY" if position > 0 else "SELL"
                    pnl = (exit_price - entry_price) * entry_qty
                    if trade_side == "SELL":
                        pnl = -pnl

                    self._trades.append(
                        TradeInfo(
                            trade_id=trade_id,
                            symbol=symbol,
                            entry_time=entry_fills[0]["ts_event"],
                            exit_time=fill["ts_event"],
                            entry_price=entry_price,
                            exit_price=exit_price,
                            side=trade_side,
                            quantity=entry_qty,
                            pnl=pnl,
                            entry_fills=list(entry_fills),
                            exit_fills=[fill],
                        )
                    )
                    entry_fills = []
                else:
                    pass

                position = new_position

    def trades(
        self,
        bars_before: int = 100,
        bars_after: int = 100,
        top_n_winners: int = 10,
        top_n_losers: int = 10,
    ) -> bool:
        """Generate trade-specific charts.

        Args:
            bars_before: Number of bars to show before trade entry.
            bars_after: Number of bars to show after trade exit.
            top_n_winners: Number of top winners to copy to biggest_winners folder.
            top_n_losers: Number of top losers to copy to biggest_losers folder.

        Returns:
            True if charts were generated successfully.
        """
        if not self._trades or self._bars_df is None:
            return False

        symbols = set(t.symbol for t in self._trades)
        for symbol in symbols:
            self._generate_trade_charts_for_symbol(
                symbol, bars_before, bars_after, top_n_winners, top_n_losers
            )
        return True

    def _generate_trade_charts_for_symbol(
        self,
        symbol: str,
        bars_before: int,
        bars_after: int,
        top_n_winners: int,
        top_n_losers: int,
    ) -> None:
        """Generate trade charts for a specific symbol."""
        base_dir = self._results_path / "charts" / symbol
        all_dir = base_dir / "all"
        winners_dir = base_dir / "biggest_winners"
        losers_dir = base_dir / "biggest_losers"

        for d in [all_dir, winners_dir, losers_dir]:
            if d.exists():
                shutil.rmtree(d)
            d.mkdir(parents=True, exist_ok=True)

        symbol_trades = [t for t in self._trades if t.symbol == symbol]
        if self._bars_df is None:
            return
        symbol_bars = self._bars_df[self._bars_df["symbol"] == symbol].copy()

        for trade in symbol_trades:
            self._create_trade_chart(
                trade, symbol_bars, bars_before, bars_after, all_dir
            )

        sorted_trades = sorted(symbol_trades, key=lambda t: t.pnl, reverse=True)
        winners = sorted_trades[:top_n_winners]
        losers = sorted_trades[-top_n_losers:]

        for i, trade in enumerate(winners, 1):
            src = all_dir / f"trade_{trade.trade_id:03d}.png"
            if src.exists():
                dst = (
                    winners_dir
                    / f"winner_{i:02d}_trade_{trade.trade_id:03d}_pnl_{trade.pnl:.2f}.png"
                )
                shutil.copy2(src, dst)

        for i, trade in enumerate(reversed(losers), 1):
            src = all_dir / f"trade_{trade.trade_id:03d}.png"
            if src.exists():
                dst = (
                    losers_dir
                    / f"loser_{i:02d}_trade_{trade.trade_id:03d}_pnl_{trade.pnl:.2f}.png"
                )
                shutil.copy2(src, dst)

    def _create_trade_chart(
        self,
        trade: TradeInfo,
        bars_df: pd.DataFrame,
        bars_before: int,
        bars_after: int,
        output_dir: pathlib.Path,
    ) -> None:
        """Create a chart for a single trade."""
        entry_mask = bars_df["ts_event"] >= trade.entry_time
        exit_mask = bars_df["ts_event"] <= trade.exit_time

        if not entry_mask.any() or not exit_mask.any():
            return

        entry_idx = bars_df[entry_mask].index[0]
        exit_idx = bars_df[exit_mask].index[-1]

        entry_pos_raw = bars_df.index.get_loc(entry_idx)
        exit_pos_raw = bars_df.index.get_loc(exit_idx)

        # get_loc can return int, slice, or ndarray - we need int
        if not isinstance(entry_pos_raw, int) or not isinstance(exit_pos_raw, int):
            return

        entry_pos: int = entry_pos_raw
        exit_pos: int = exit_pos_raw

        chart_start = max(0, entry_pos - bars_before)
        chart_end = min(len(bars_df) - 1, exit_pos + bars_after)

        chart_data = bars_df.iloc[chart_start : chart_end + 1].copy()
        if chart_data.empty:
            return

        highlight_start = entry_pos - chart_start
        highlight_end = exit_pos - chart_start

        self._plot_trade_chart(
            chart_data, trade, highlight_start, highlight_end, output_dir
        )

    def _plot_trade_chart(
        self,
        chart_data: pd.DataFrame,
        trade: TradeInfo,
        highlight_start: int,
        highlight_end: int,
        output_dir: pathlib.Path,
    ) -> None:
        """Plot the trade chart with OHLC bars, indicators, and trade markers."""
        main_indicators = [ind for ind in self._indicators if ind.plot_at == 0]
        subplot_groups: dict[int, list[Indicator]] = {}
        for ind in self._indicators:
            if 1 <= ind.plot_at <= 98:
                subplot_groups.setdefault(ind.plot_at, []).append(ind)

        num_subplots = 1 + len(subplot_groups)
        height_ratios = [4] + [1] * len(subplot_groups)

        fig, axes = plt.subplots(
            num_subplots,
            1,
            figsize=(16, 8 + 2 * len(subplot_groups)),
            sharex=True,
            gridspec_kw={"height_ratios": height_ratios},
        )
        if num_subplots == 1:
            axes = [axes]

        ax_main = axes[0]
        self._plot_price_data(ax_main, chart_data, highlight_start, highlight_end)
        self._plot_indicators_on_main(ax_main, chart_data, main_indicators)
        self._plot_trade_markers(ax_main, chart_data, trade)

        for i, (subplot_num, indicators) in enumerate(sorted(subplot_groups.items())):
            ax = axes[i + 1]
            self._plot_subplot_indicators(ax, chart_data, indicators, subplot_num)

        self._format_and_save_trade_chart(fig, axes, trade, chart_data, output_dir)

    def _plot_price_data(
        self,
        ax,
        chart_data: pd.DataFrame,
        highlight_start: int,
        highlight_end: int,
    ) -> None:
        """Plot OHLC price data as high-low bars."""
        for i in range(len(chart_data)):
            date = chart_data["ts_event"].iloc[i]
            high = chart_data["high"].iloc[i]
            low = chart_data["low"].iloc[i]
            close = chart_data["close"].iloc[i]

            ax.plot([date, date], [low, high], color="black", linewidth=0.8, alpha=0.7)
            ax.plot([date], [close], marker="_", color="blue", markersize=3)

        if 0 <= highlight_start < len(chart_data) and 0 <= highlight_end < len(
            chart_data
        ):
            start_time = mdates.date2num(chart_data["ts_event"].iloc[highlight_start])
            end_time = mdates.date2num(chart_data["ts_event"].iloc[highlight_end])
            y_min, y_max = ax.get_ylim()
            rect = Rectangle(
                (start_time, y_min),
                end_time - start_time,
                y_max - y_min,
                facecolor="lightblue",
                alpha=0.2,
                label="Trade Period",
            )
            ax.add_patch(rect)

    def _plot_indicators_on_main(
        self, ax, chart_data: pd.DataFrame, indicators: list[Indicator]
    ) -> None:
        """Plot main indicators on the price chart."""
        colors = ["orange", "purple", "brown", "pink", "gray", "cyan", "magenta"]
        for i, ind in enumerate(indicators):
            color = colors[i % len(colors)]
            history = list(ind.history)
            if len(history) >= len(chart_data):
                values = history[-len(chart_data) :]
                ax.plot(
                    chart_data["ts_event"],
                    values,
                    label=ind.name,
                    linewidth=1.5,
                    alpha=0.8,
                    color=color,
                )

    def _plot_trade_markers(
        self, ax, chart_data: pd.DataFrame, trade: TradeInfo
    ) -> None:
        """Plot trade entry/exit markers."""
        entry_marker = "^" if trade.side == "BUY" else "v"
        exit_marker = "v" if trade.side == "BUY" else "^"

        ax.scatter(
            trade.entry_time,
            trade.entry_price,
            marker=entry_marker,
            color="green",
            s=150,
            edgecolors="black",
            linewidth=1,
            zorder=5,
            alpha=0.8,
            label="Entry",
        )
        ax.scatter(
            trade.exit_time,
            trade.exit_price,
            marker=exit_marker,
            color="red",
            s=150,
            edgecolors="black",
            linewidth=1,
            zorder=5,
            alpha=0.8,
            label="Exit",
        )

    def _plot_subplot_indicators(
        self,
        ax,
        chart_data: pd.DataFrame,
        indicators: list[Indicator],
        subplot_num: int,
    ) -> None:
        """Plot indicators in their own subplot."""
        colors = [
            "#1f77b4",
            "#ff7f0e",
            "#2ca02c",
            "#d62728",
            "#9467bd",
            "#8c564b",
            "#e377c2",
            "#7f7f7f",
        ]
        for i, ind in enumerate(indicators):
            color = colors[i % len(colors)]
            history = list(ind.history)
            if len(history) >= len(chart_data):
                values = history[-len(chart_data) :]
                ax.plot(
                    chart_data["ts_event"],
                    values,
                    label=ind.name,
                    linewidth=1,
                    color=color,
                )

        ax.legend(loc="upper left", fontsize=8)
        ax.grid(True, alpha=0.3)

    def _format_and_save_trade_chart(
        self,
        fig,
        axes,
        trade: TradeInfo,
        chart_data: pd.DataFrame,
        output_dir: pathlib.Path,
    ) -> None:
        """Format the chart and save to file."""
        ax_main = axes[0]
        win_loss = "WIN" if trade.pnl > 0 else "LOSS" if trade.pnl < 0 else "BREAK-EVEN"
        title = f"Trade #{trade.trade_id} - {win_loss} - {trade.side} - P&L: ${trade.pnl:.2f}"
        ax_main.set_title(title, fontsize=14, fontweight="bold")
        ax_main.grid(True, alpha=0.3)

        custom_lines = [
            Line2D(
                [0],
                [0],
                marker="^",
                color="w",
                markerfacecolor="green",
                markersize=10,
                label="Entry (Buy)",
            ),
            Line2D(
                [0],
                [0],
                marker="v",
                color="w",
                markerfacecolor="green",
                markersize=10,
                label="Entry (Sell)",
            ),
            Line2D(
                [0],
                [0],
                marker="v",
                color="w",
                markerfacecolor="red",
                markersize=10,
                label="Exit (Sell)",
            ),
            Line2D(
                [0],
                [0],
                marker="^",
                color="w",
                markerfacecolor="red",
                markersize=10,
                label="Exit (Buy)",
            ),
            Line2D(
                [0],
                [0],
                color="lightblue",
                marker="s",
                alpha=0.3,
                markersize=10,
                label="Trade Period",
            ),
        ]
        ax_main.legend(handles=custom_lines, loc="upper left", fontsize=9)

        stats_text = (
            f"Qty: {trade.quantity}\n"
            f"Entry: ${trade.entry_price:.2f}\n"
            f"Exit: ${trade.exit_price:.2f}"
        )
        ax_main.text(
            0.02,
            0.02,
            stats_text,
            transform=ax_main.transAxes,
            fontsize=9,
            verticalalignment="bottom",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8),
        )

        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
            chart_duration_hours = (
                chart_data["ts_event"].iloc[-1] - chart_data["ts_event"].iloc[0]
            ).total_seconds() / 3600

            if chart_duration_hours <= 2:
                ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=5))
            elif chart_duration_hours <= 8:
                ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=15))
            elif chart_duration_hours <= 24:
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
            else:
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))

        plt.xticks(rotation=90)
        plt.tight_layout()

        filename = output_dir / f"trade_{trade.trade_id:03d}.png"
        plt.savefig(filename, dpi=300, bbox_inches="tight")
        plt.close(fig)

    def price(
        self,
        bars_per_chart: int = 500,
        bar_overlap: int = 50,
    ) -> bool:
        """Generate full price action charts.

        Args:
            bars_per_chart: Number of bars per chart.
            bar_overlap: Number of overlapping bars between consecutive charts.

        Returns:
            True if charts were generated successfully.
        """
        if self._bars_df is None or self._bars_df.empty:
            return False

        symbols = self._bars_df["symbol"].unique()
        for symbol in symbols:
            self._generate_price_charts_for_symbol(symbol, bars_per_chart, bar_overlap)
        return True

    def _generate_price_charts_for_symbol(
        self, symbol: str, bars_per_chart: int, bar_overlap: int
    ) -> None:
        """Generate price action charts for a specific symbol."""
        base_dir = self._results_path / "charts" / symbol / "price_action"
        if base_dir.exists():
            shutil.rmtree(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)

        if self._bars_df is None:
            return
        symbol_bars = self._bars_df[self._bars_df["symbol"] == symbol].copy()
        total_bars = len(symbol_bars)
        step = bars_per_chart - bar_overlap
        chart_num = 0

        start_idx = 0
        while start_idx < total_bars:
            end_idx = min(start_idx + bars_per_chart, total_bars)
            chart_data = symbol_bars.iloc[start_idx:end_idx].copy()

            if len(chart_data) > 0:
                chart_num += 1
                self._create_price_chart(chart_data, symbol, chart_num, base_dir)

            start_idx += step
            if end_idx >= total_bars:
                break

    def _create_price_chart(
        self,
        chart_data: pd.DataFrame,
        symbol: str,
        chart_num: int,
        output_dir: pathlib.Path,
    ) -> None:
        """Create a price action chart."""
        main_indicators = [ind for ind in self._indicators if ind.plot_at == 0]
        subplot_groups: dict[int, list[Indicator]] = {}
        for ind in self._indicators:
            if 1 <= ind.plot_at <= 98:
                subplot_groups.setdefault(ind.plot_at, []).append(ind)

        num_subplots = 1 + len(subplot_groups)
        height_ratios = [4] + [1] * len(subplot_groups)

        fig, axes = plt.subplots(
            num_subplots,
            1,
            figsize=(16, 8 + 2 * len(subplot_groups)),
            sharex=True,
            gridspec_kw={"height_ratios": height_ratios},
        )
        if num_subplots == 1:
            axes = [axes]

        ax_main = axes[0]
        self._plot_price_data(ax_main, chart_data, -1, -1)
        self._plot_indicators_on_main(ax_main, chart_data, main_indicators)

        for i, (subplot_num, indicators) in enumerate(sorted(subplot_groups.items())):
            ax = axes[i + 1]
            self._plot_subplot_indicators(ax, chart_data, indicators, subplot_num)

        start_time = chart_data["ts_event"].iloc[0].strftime("%Y-%m-%d %H:%M")
        end_time = chart_data["ts_event"].iloc[-1].strftime("%Y-%m-%d %H:%M")
        title = f"{symbol} - Chart #{chart_num} - {start_time} to {end_time}"
        ax_main.set_title(title, fontsize=14, fontweight="bold")
        ax_main.grid(True, alpha=0.3)

        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
            chart_duration_hours = (
                chart_data["ts_event"].iloc[-1] - chart_data["ts_event"].iloc[0]
            ).total_seconds() / 3600

            if chart_duration_hours <= 2:
                ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=5))
            elif chart_duration_hours <= 8:
                ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=15))
            elif chart_duration_hours <= 24:
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
            else:
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))

        plt.xticks(rotation=90)
        plt.tight_layout()

        filename = output_dir / f"chart_{chart_num:03d}.png"
        plt.savefig(filename, dpi=300, bbox_inches="tight")
        plt.close(fig)


class Optimizer:
    pass
