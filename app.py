"""
Market Intelligence Web Dashboard
- Insights summary at top
- Signal/Accumulation/Breakout/Distribution tabs
- Ticker search at bottom with volume chart
"""

import json
import logging
import os
from pathlib import Path

import yfinance as yf
from flask import Flask, render_template_string, request, jsonify

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

app = Flask(__name__)
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent))
DB_PATH = DATA_DIR / "volume_alerts.json"

HTML = open(Path(__file__).parent / "templates" / "dashboard.html").read() if (Path(__file__).parent / "templates" / "dashboard.html").exists() else ""


@app.route("/")
def index():
    html_path = Path(__file__).parent / "templates" / "dashboard.html"
    return html_path.read_text()


@app.route("/api/dashboard")
def api_dashboard():
    if not DB_PATH.exists():
        return jsonify({"alerts": [], "signals": []})

    history = json.loads(DB_PATH.read_text())
    dates = sorted(history.keys())
    today_alerts = history[dates[-1]] if dates else []

    recent_dates = dates[-5:]
    appearances = {}
    for date in recent_dates:
        for entry in history[date]:
            t = entry["ticker"]
            if t not in appearances:
                appearances[t] = {"days": 0, "vol_spikes": []}
            appearances[t]["days"] += 1
            appearances[t]["vol_spikes"].append(entry["vol_spike"])

    signals = []
    for a in today_alerts:
        t = a["ticker"]
        if t in appearances and appearances[t]["days"] >= 3:
            avg_vol = sum(appearances[t]["vol_spikes"]) / len(appearances[t]["vol_spikes"])
            signals.append({**a, "days_seen": appearances[t]["days"], "avg_vol": round(avg_vol, 1)})

    signals.sort(key=lambda x: x["days_seen"], reverse=True)
    return jsonify({"alerts": today_alerts, "signals": signals, "scan_date": dates[-1] if dates else ""})


@app.route("/api/ticker/<ticker>")
def api_ticker(ticker):
    ticker = ticker.upper()
    try:
        import io
        from contextlib import redirect_stderr
        f = io.StringIO()
        with redirect_stderr(f):
            hist = yf.Ticker(ticker).history(period="3mo")
        if len(hist) < 22:
            return jsonify({"error": f"Not enough data for {ticker}. Check the symbol."})

        close = hist["Close"]
        volume = hist["Volume"]

        price = float(close.iloc[-1])
        price_1w = (close.iloc[-1] / close.iloc[-6] - 1) * 100
        price_1m = (close.iloc[-1] / close.iloc[-22] - 1) * 100

        vol_recent = volume.iloc[-5:].mean()
        vol_prior = volume.iloc[-21:-5].mean()
        vol_spike = (vol_recent / max(vol_prior, 1) - 1) * 100
        avg_volume = volume.iloc[-21:].mean()

        daily_volume = []
        avg_21 = volume.iloc[-21:].mean()
        for i in range(-10, 0):
            date = volume.index[i].strftime("%m/%d")
            ratio = float(volume.iloc[i]) / max(avg_21, 1)
            daily_volume.append({"date": date, "ratio": round(ratio, 2)})

        if abs(price_1w) < 5:
            signal = "EARLY"
        elif price_1w > 5:
            signal = "CONFIRMING"
        else:
            signal = "SELLING"

        return jsonify({
            "ticker": ticker,
            "price": round(price, 2),
            "price_1w": round(float(price_1w), 1),
            "price_1m": round(float(price_1m), 1),
            "vol_spike": round(float(vol_spike), 1),
            "avg_volume": round(float(avg_volume), 0),
            "daily_volume": daily_volume,
            "signal": signal,
        })
    except Exception as e:
        return jsonify({"error": f"Could not fetch data for {ticker}: {str(e)}"})


if __name__ == "__main__":
    print("\n  🌐 Market Intel Dashboard: http://localhost:5000\n")
    app.run(debug=True, port=5000)
