"""Plotly figures for the web app. Taiwan convention: red = up, green = down."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

UP, DOWN = "#e5484d", "#30a46c"
MA_COLORS = {"SMA5": "#f59e0b", "SMA20": "#2563eb", "SMA60": "#9333ea", "SMA120": "#0891b2", "SMA240": "#64748b"}
SERIES = ["#2563eb", "#e5484d", "#30a46c", "#f59e0b", "#9333ea", "#0891b2", "#db2777", "#64748b", "#84cc16"]


def price_chart(df: pd.DataFrame, title: str, mas: list[str], bollinger: bool, lower: list[str]) -> go.Figure:
    """Candles + moving averages (+ Bollinger) + volume, then one panel per lower indicator."""
    rows = 2 + len(lower)
    heights = [0.55, 0.15] + [0.3 / max(len(lower), 1)] * len(lower)
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.025, row_heights=heights)
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="K 線",
        increasing={"line": {"color": UP}, "fillcolor": UP}, decreasing={"line": {"color": DOWN}, "fillcolor": DOWN},
    ), row=1, col=1)
    for ma in mas:
        if ma in df:
            fig.add_trace(go.Scatter(x=df.index, y=df[ma], name=ma.replace("SMA", "MA"),
                                     line={"width": 1.3, "color": MA_COLORS.get(ma)}), row=1, col=1)
    if bollinger:
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_up"], name="布林上軌",
                                 line={"width": 1, "dash": "dot", "color": "#94a3b8"}), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_low"], name="布林下軌", fill="tonexty",
                                 fillcolor="rgba(148,163,184,0.12)",
                                 line={"width": 1, "dash": "dot", "color": "#94a3b8"}), row=1, col=1)
    colors = [UP if c >= o else DOWN for o, c in zip(df["Open"], df["Close"], strict=False)]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="成交量", marker_color=colors, opacity=0.7,
                         showlegend=False), row=2, col=1)
    for i, ind in enumerate(lower, start=3):
        if ind == "MACD":
            hist_colors = [UP if v >= 0 else DOWN for v in df["MACD_hist"].fillna(0)]
            fig.add_trace(go.Bar(x=df.index, y=df["MACD_hist"], name="MACD 柱", marker_color=hist_colors,
                                 showlegend=False), row=i, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="DIF", line={"width": 1.2, "color": "#2563eb"}),
                          row=i, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["MACD_signal"], name="DEA",
                                     line={"width": 1.2, "color": "#f59e0b"}), row=i, col=1)
        elif ind == "RSI":
            fig.add_trace(go.Scatter(x=df.index, y=df["RSI14"], name="RSI 14", line={"width": 1.3, "color": "#9333ea"}),
                          row=i, col=1)
            for lvl in (30, 70):
                fig.add_hline(y=lvl, line={"dash": "dash", "width": 1, "color": "#94a3b8"}, row=i, col=1)
            fig.update_yaxes(range=[0, 100], row=i, col=1)
        elif ind == "KD":
            fig.add_trace(go.Scatter(x=df.index, y=df["K"], name="K", line={"width": 1.2, "color": "#2563eb"}),
                          row=i, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["D"], name="D", line={"width": 1.2, "color": "#f59e0b"}),
                          row=i, col=1)
            for lvl in (20, 80):
                fig.add_hline(y=lvl, line={"dash": "dash", "width": 1, "color": "#94a3b8"}, row=i, col=1)
            fig.update_yaxes(range=[0, 100], row=i, col=1)
        fig.update_yaxes(title_text=ind, title_font_size=11, row=i, col=1)
    fig.update_yaxes(title_text="價格", title_font_size=11, row=1, col=1)
    fig.update_yaxes(title_text="量", title_font_size=11, row=2, col=1)
    fig.update_layout(
        height=460 + 170 * len(lower),
        margin={"l": 10, "r": 10, "t": 30, "b": 10}, xaxis_rangeslider_visible=False,
        legend={"orientation": "h", "y": 1.02, "x": 0, "yanchor": "bottom"}, hovermode="x unified",
    )
    # Hide weekends so candles sit next to each other.
    fig.update_xaxes(rangebreaks=[{"bounds": ["sat", "mon"]}])
    return fig


def performance_chart(closes: pd.DataFrame, names: dict[str, str], title: str) -> go.Figure:
    """Each series rebased to 0% at the window start."""
    rebased = closes.div(closes.bfill().iloc[0]) - 1
    fig = go.Figure()
    for i, col in enumerate(rebased.columns):
        s = rebased[col].dropna()
        if s.empty:
            continue
        label = f"{names.get(col, col)} {s.iloc[-1]:+.1%}"
        fig.add_trace(go.Scatter(x=s.index, y=s, name=label, line={"width": 2, "color": SERIES[i % len(SERIES)]},
                                 hovertemplate="%{y:+.2%}"))
    fig.add_hline(y=0, line={"width": 1, "color": "#94a3b8"})
    fig.update_layout(title={"text": title, "font": {"size": 16}}, height=420, yaxis_tickformat="+.0%",
                      margin={"l": 10, "r": 10, "t": 50, "b": 10}, hovermode="x unified",
                      legend={"orientation": "h", "y": -0.15})
    return fig


def sparkline(series: pd.Series, up: bool) -> go.Figure:
    fig = go.Figure(go.Scatter(x=series.index, y=series, line={"width": 1.6, "color": UP if up else DOWN},
                               fill="tozeroy", fillcolor="rgba(0,0,0,0)", hoverinfo="skip"))
    lo, hi = series.min(), series.max()
    pad = (hi - lo) * 0.1 or 1
    fig.update_layout(height=60, margin={"l": 0, "r": 0, "t": 0, "b": 0}, showlegend=False,
                      xaxis={"visible": False}, yaxis={"visible": False, "range": [lo - pad, hi + pad]})
    return fig


def line_chart(df: pd.DataFrame, mas: list[str]) -> go.Figure:
    """Close price as a line (with optional moving averages) over a volume panel."""
    up = df["Close"].iloc[-1] >= df["Close"].iloc[0]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.78, 0.22])
    fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="收盤", line={"width": 2, "color": UP if up else DOWN},
                             hovertemplate="%{y:,.2f}"), row=1, col=1)
    for ma in mas:
        if ma in df:
            fig.add_trace(go.Scatter(x=df.index, y=df[ma], name=ma.replace("SMA", "MA"),
                                     line={"width": 1.2, "color": MA_COLORS.get(ma)}), row=1, col=1)
    if df["Volume"].fillna(0).sum() > 0:
        fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="成交量", marker_color="#94a3b8", showlegend=False),
                      row=2, col=1)
    fig.update_layout(height=520, margin={"l": 10, "r": 10, "t": 30, "b": 10}, hovermode="x unified",
                      legend={"orientation": "h", "y": 1.02, "x": 0, "yanchor": "bottom"})
    fig.update_xaxes(rangebreaks=[{"bounds": ["sat", "mon"]}])
    return fig
