"""
Market Intelligence Signal Detector v3
Focused on what catches waves early: Volume + Reddit + Price
No API keys needed. Run daily.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import yfinance as yf

# --- THEMES & TICKERS ---
SECTOR_THEMES = {
    "AI Infrastructure": {
        "reddit_terms": ["AI data center", "NVDA", "AVGO", "SMCI", "AI infrastructure"],
        "tickers": ["NVDA", "AVGO", "MRVL", "SMCI", "VRT"],
    },
    "Nuclear Energy": {
        "reddit_terms": ["nuclear energy", "SMR", "uranium", "CCJ", "nuclear power"],
        "tickers": ["CEG", "VST", "SMR", "CCJ", "LEU"],
    },
    "Robotics": {
        "reddit_terms": ["humanoid robot", "Tesla bot", "robotics", "Figure AI"],
        "tickers": ["ISRG", "FANUY", "TER", "AXON", "PATH"],
    },
    "Space Economy": {
        "reddit_terms": ["Rocket Lab", "RKLB", "space stocks", "satellite"],
        "tickers": ["RKLB", "ASTS", "LUNR", "RDW", "MNTS"],
    },
    "Quantum Computing": {
        "reddit_terms": ["quantum computing", "IONQ", "RGTI", "quantum stocks"],
        "tickers": ["IONQ", "RGTI", "QBTS", "QUBT"],
    },
    "Synthetic Biology": {
        "reddit_terms": ["CRISPR", "gene therapy", "synthetic biology", "CRSP"],
        "tickers": ["CRSP", "BEAM", "NTLA", "RXRX", "TWST"],
    },
    "Defense Tech": {
        "reddit_terms": ["defense stocks", "PLTR", "Palantir", "defense spending"],
        "tickers": ["PLTR", "LMT", "RTX", "LDOS", "KTOS"],
    },
    "Reshoring": {
        "reddit_terms": ["reshoring", "CHIPS Act", "US manufacturing", "onshoring"],
        "tickers": ["FSLR", "WOLF", "AEHR", "ATKR"],
    },
    "Longevity": {
        "reddit_terms": ["GLP-1", "Ozempic", "longevity", "anti aging", "LLY"],
        "tickers": ["LLY", "NVO", "AMGN", "ABBV"],
    },
    "Edge AI": {
        "reddit_terms": ["edge AI", "on device AI", "local LLM", "Qualcomm AI"],
        "tickers": ["QCOM", "ARM", "INTC", "AMD"],
    },
}

DB_PATH = Path(__file__).parent / "signals.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (market-intel/2.0)"}


def load_history():
    if DB_PATH.exists():
        return json.loads(DB_PATH.read_text())
    return {}


def save_history(data):
    DB_PATH.write_text(json.dumps(data, indent=2, default=str))


# --- REDDIT ---
def get_reddit_mentions(terms: list[str]) -> int:
    """Count mentions across investing subreddits in past week."""
    subreddits = ["wallstreetbets", "investing", "stocks", "stockmarket"]
    total = 0
    for term in terms:
        for sub in subreddits:
            try:
                url = f"https://www.reddit.com/r/{sub}/search.json"
                params = {"q": term, "restrict_sr": "on", "sort": "new", "t": "week", "limit": 100}
                resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
                if resp.status_code == 200:
                    total += resp.json().get("data", {}).get("dist", 0)
                time.sleep(1)
            except Exception:
                continue
    return total


# --- MARKET DATA ---
def get_price_volume(tickers: list[str]) -> list[dict]:
    """Get price change and volume spike for each ticker."""
    results = []
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period="3mo")
            if len(hist) < 21:
                continue
            price_1w = (hist["Close"].iloc[-1] / hist["Close"].iloc[-5] - 1) * 100
            price_1m = (hist["Close"].iloc[-1] / hist["Close"].iloc[-21] - 1) * 100
            vol_recent = hist["Volume"].iloc[-5:].mean()
            vol_prior = hist["Volume"].iloc[-21:-5].mean()
            vol_spike = (vol_recent / max(vol_prior, 1) - 1) * 100
            results.append({
                "ticker": ticker,
                "price_1w": round(price_1w, 1),
                "price_1m": round(price_1m, 1),
                "vol_spike": round(vol_spike, 1),
            })
        except Exception:
            continue
    return results


# --- SCORING ---
def score_theme(theme: str) -> dict:
    config = SECTOR_THEMES[theme]
    print(f"  📡 {theme}...")

    # Reddit
    reddit_count = get_reddit_mentions(config["reddit_terms"])
    # Normalize: 200+ = max score
    reddit_score = min(100, round((reddit_count / 200) * 100, 1))

    # Price & Volume
    stocks = get_price_volume(config["tickers"])
    avg_price_1w = sum(s["price_1w"] for s in stocks) / max(len(stocks), 1)
    avg_vol_spike = sum(s["vol_spike"] for s in stocks) / max(len(stocks), 1)

    # COMPOSITE: Volume-heavy scoring
    # Volume 40% — the key signal (institutions moving)
    # Reddit 30% — early buzz
    # Price  30% — confirmation
    composite = (
        avg_vol_spike * 0.40 +
        reddit_score * 0.30 +
        avg_price_1w * 0.30
    )

    # Sort stocks by volume spike (the key metric)
    stocks.sort(key=lambda x: x["vol_spike"], reverse=True)

    return {
        "theme": theme,
        "score": round(composite, 1),
        "vol_spike": round(avg_vol_spike, 1),
        "reddit_score": round(reddit_score, 1),
        "reddit_mentions": reddit_count,
        "price_1w": round(avg_price_1w, 1),
        "stocks": stocks,
    }


# --- DISPLAY ---
def display(results, changes):
    print("\n" + "=" * 60)
    print("  📊 RANKINGS (Volume-weighted)")
    print("  Higher score = more institutional activity + buzz")
    print("=" * 60)

    for i, r in enumerate(results, 1):
        emoji = "🔥" if r["score"] > 30 else "📈" if r["score"] > 10 else "💤"
        delta = ""
        if r["theme"] in changes:
            d = changes[r["theme"]]
            delta = f" ({'+' if d > 0 else ''}{d} vs last)"

        print(f"\n{emoji} #{i} {r['theme']} — Score: {r['score']}{delta}")
        print(f"   Volume Spike: {r['vol_spike']}% | Reddit: {r['reddit_mentions']} mentions | Price 1W: {r['price_1w']}%")

        # Show top 3 stocks by volume spike
        for s in r["stocks"][:3]:
            vol_bar = "█" * min(int(abs(s["vol_spike"]) / 10), 10)
            print(f"     {s['ticker']:5} Vol: {s['vol_spike']:+.0f}% {vol_bar}  Price: {s['price_1w']:+.1f}%")

    # EARLY SIGNAL: high volume or reddit but price hasn't moved
    print("\n" + "=" * 60)
    print("  ⚡ EARLY SIGNALS")
    print("  (Volume/buzz UP but price hasn't moved = you might be early)")
    print("=" * 60)

    found = False
    for r in results:
        if (r["vol_spike"] > 20 or r["reddit_score"] > 30) and r["price_1w"] < 5:
            found = True
            print(f"\n  🚨 {r['theme']}")
            print(f"     Volume is up {r['vol_spike']}% and Reddit has {r['reddit_mentions']} mentions")
            print(f"     But price only moved {r['price_1w']}% — market hasn't caught on yet")
            print(f"     👀 Watch: {', '.join(s['ticker'] for s in r['stocks'][:3])}")

    # VOLUME ALERT: individual stocks with huge volume spikes
    print("\n" + "=" * 60)
    print("  🔊 UNUSUAL VOLUME (individual stocks)")
    print("  (Smart money moving before the crowd)")
    print("=" * 60)

    all_stocks = []
    for r in results:
        for s in r["stocks"]:
            s["theme"] = r["theme"]
            all_stocks.append(s)
    all_stocks.sort(key=lambda x: x["vol_spike"], reverse=True)

    for s in all_stocks[:8]:
        if s["vol_spike"] > 20:
            status = "🟢 Price confirming" if s["price_1w"] > 5 else "🟡 Price flat — EARLY"
            print(f"  {s['ticker']:5} ({s['theme']}) — Vol: {s['vol_spike']:+.0f}% | Price: {s['price_1w']:+.1f}% | {status}")

    if not found and not any(s["vol_spike"] > 20 for s in all_stocks[:8]):
        print("\n  No unusual activity detected. Market is quiet.")


def run_scan():
    print("=" * 60)
    print("  MARKET INTELLIGENCE v3")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("  Signals: Volume + Reddit + Price (no API keys needed)")
    print("=" * 60)
    print()

    results = []
    for theme in SECTOR_THEMES:
        results.append(score_theme(theme))

    results.sort(key=lambda x: x["score"], reverse=True)

    # History
    history = load_history()
    today = datetime.now().strftime("%Y-%m-%d")
    changes = {}
    dates = sorted(history.keys())
    if dates:
        last = dates[-1] if dates[-1] != today else (dates[-2] if len(dates) > 1 else None)
        if last:
            prev = {r["theme"]: r["score"] for r in history[last]}
            changes = {r["theme"]: round(r["score"] - prev.get(r["theme"], 0), 1) for r in results if r["theme"] in prev}
    history[today] = results
    save_history(history)

    display(results, changes)

    print(f"\n\n✅ Scan complete. Run again tomorrow to track shifts.")
    print("   Tip: Consistent volume spike over multiple days = real trend\n")


if __name__ == "__main__":
    run_scan()
