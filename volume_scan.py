"""
Broad Market Volume Screener
Scans S&P 500 for unusual volume — catches moves before they hit headlines.
Downloads in batches to avoid network throttling.
Supports --backfill to analyze past 5 trading days from historical data.
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

# Suppress noisy yfinance warnings
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent))
DB_PATH = DATA_DIR / "volume_alerts.json"


def get_sp500_tickers() -> list[str]:
    """Fetch live S&P 500 ticker list from GitHub."""
    sources = [
        "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
    ]
    for url in sources:
        try:
            df = pd.read_csv(url)
            col = "Symbol" if "Symbol" in df.columns else df.columns[0]
            tickers = df[col].str.replace(".", "-", regex=False).dropna().tolist()
            if len(tickers) > 400:
                print(f"  Fetched {len(tickers)} tickers (live)")
                return tickers
        except Exception:
            continue
    print("  ⚠️  Using cached fallback list")
    return FALLBACK_SP500


FALLBACK_SP500 = [
    "AAPL","ABBV","ABT","ACN","ADBE","ADI","ADP","ADSK","AEP","AFL","AIG","AKAM",
    "ALGN","ALL","AMAT","AMD","AMGN","AMP","AMT","AMZN","ANET","ANSS","AON","APD",
    "APH","AVGO","AXP","BA","BAC","BDX","BK","BKNG","BLK","BMY","BR","BRK-B",
    "BSX","C","CAT","CB","CCI","CDNS","CDW","CEG","CF","CHD","CHTR","CI","CL",
    "CMCSA","CME","CMG","CMI","COP","COST","CRM","CSCO","CSX","CTAS","CTSH","CVS",
    "CVX","D","DAL","DD","DE","DFS","DHR","DIS","DLR","DOV","DOW","DUK","DVN",
    "DXCM","EA","EBAY","ECL","ED","EFX","EMR","ENPH","EOG","EPAM","EQIX","EQR",
    "ES","ETN","ETR","EVRG","EW","EXC","EXPE","F","FANG","FAST","FCX","FDX","FE",
    "FIS","FISV","FITB","FSLR","FTNT","GD","GE","GILD","GIS","GLW","GM","GOOG",
    "GOOGL","GPN","GS","GWW","HAL","HCA","HD","HOLX","HON","HPE","HPQ","HUM",
    "HWM","IBM","ICE","IDXX","INTC","INTU","ISRG","IT","ITW","J","JBHT","JCI",
    "JNJ","JNPR","JPM","KEY","KEYS","KHC","KLAC","KMB","KO","KR","LDOS","LEN",
    "LHX","LIN","LLY","LMT","LOW","LRCX","LYB","MA","MAR","MAS","MCD","MCHP",
    "MCK","MCO","MDLZ","MDT","MET","META","MMC","MMM","MNST","MO","MPC","MPWR",
    "MRK","MRNA","MS","MSCI","MSFT","MSI","MTD","MU","NCLH","NDAQ","NEE","NEM",
    "NFLX","NKE","NOC","NOW","NRG","NSC","NTAP","NVDA","NVR","NXPI","O","ODFL",
    "OKE","OMC","ON","ORCL","ORLY","OTIS","OXY","PAYC","PAYX","PCAR","PCG","PEG",
    "PEP","PFE","PG","PGR","PH","PHM","PLD","PM","PNC","POOL","PPG","PRU","PSA",
    "PSX","PTC","PVH","PWR","PYPL","QCOM","RCL","REGN","RF","RJF","ROK","ROL",
    "ROP","ROST","RSG","RTX","SBUX","SCHW","SHW","SLB","SNPS","SO","SPG","SPGI",
    "SRE","STE","STT","STX","STZ","SWK","SYF","SYK","SYY","T","TDG","TDY","TEL",
    "TER","TFC","TGT","TJX","TMO","TMUS","TPR","TRGP","TRMB","TROW","TRV","TSCO",
    "TSLA","TT","TTWO","TXN","TXT","TYL","UAL","UHS","ULTA","UNH","UNP","UPS",
    "URI","USB","V","VICI","VLO","VMC","VRSK","VRSN","VRTX","VTRS","VZ","WAB",
    "WAT","WBA","WBD","WDC","WEC","WELL","WFC","WM","WMB","WMT","WRB","WST",
    "WTW","XEL","XOM","XYL","YUM","ZBH","ZBRA","ZION","ZTS",
]


def download_batch(tickers: list[str]) -> dict:
    """Download a batch of tickers and return price/volume data."""
    results = {}
    try:
        import io
        from contextlib import redirect_stderr
        f = io.StringIO()
        with redirect_stderr(f):
            data = yf.download(tickers, period="3mo", progress=False, threads=False)
        if data.empty:
            return results
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    close = data["Close"]
                    volume = data["Volume"]
                    open_ = data["Open"]
                else:
                    close = data["Close"][ticker]
                    volume = data["Volume"][ticker]
                    open_ = data["Open"][ticker]
                close = close.dropna()
                volume = volume.dropna()
                open_ = open_.dropna()
                if len(close) < 22 or len(volume) < 22:
                    continue
                results[ticker] = {"close": close, "volume": volume, "open": open_}
            except Exception:
                continue
    except Exception:
        pass
    return results


def analyze_day(all_data: dict, min_vol_spike: float, day_offset: int) -> list[dict]:
    """Analyze volume for a specific day offset (0=latest, 1=day before, etc.)."""
    alerts = []
    for ticker, data in all_data.items():
        close = data["close"]
        volume = data["volume"]
        open_ = data["open"]

        end_idx = len(close) - day_offset
        if end_idx < 22:
            continue

        vol_recent = volume.iloc[end_idx-5:end_idx].mean()
        vol_prior = volume.iloc[end_idx-21:end_idx-5].mean()
        if vol_prior == 0:
            continue
        vol_spike = (vol_recent / vol_prior - 1) * 100

        if vol_spike < min_vol_spike:
            continue

        price_1w = (close.iloc[end_idx-1] / close.iloc[end_idx-6] - 1) * 100
        price_1m = (close.iloc[end_idx-1] / close.iloc[end_idx-22] - 1) * 100

        # Estimated buy ratio: green days (close > open) in last 5 days
        green_days = sum(1 for i in range(end_idx-5, end_idx)
                        if i < len(close) and i < len(open_) and close.iloc[i] > open_.iloc[i])
        buy_ratio = f"{green_days}/5"

        if abs(price_1w) < 5:
            status = "🟡 EARLY"
        elif price_1w > 5:
            status = "🟢 CONFIRMING"
        else:
            status = "🔴 SELLING"

        alerts.append({
            "ticker": ticker,
            "price": round(float(close.iloc[end_idx-1]), 2),
            "vol_spike": round(vol_spike, 1),
            "price_1w": round(price_1w, 1),
            "price_1m": round(price_1m, 1),
            "buy_ratio": buy_ratio,
            "status": status,
        })

    alerts.sort(key=lambda x: x["vol_spike"], reverse=True)
    return alerts


def get_date_for_offset(all_data: dict, offset: int) -> str:
    """Get the actual trading date for a given offset."""
    sample = next(iter(all_data.values()))
    idx = len(sample["close"]) - 1 - offset
    if idx < 0:
        return None
    return sample["close"].index[idx].strftime("%Y-%m-%d")


def display_results(alerts, min_vol_spike):
    """Display categorized results."""
    print(f"\n  Found {len(alerts)} stocks with volume spike > {min_vol_spike}%\n")

    early = [a for a in alerts if a["status"] == "🟡 EARLY"]
    confirming = [a for a in alerts if a["status"] == "🟢 CONFIRMING"]
    selling = [a for a in alerts if a["status"] == "🔴 SELLING"]

    ranges = [
        ("🔥 EXTREME (200%+)", 200, float("inf")),
        ("⚡ HIGH (100-200%)", 100, 200),
        ("📈 MODERATE (50-100%)", 50, 100),
        ("📊 MILD (25-50%)", 25, 50),
    ]

    print("=" * 60)
    print("  🟡 ACCUMULATION (volume UP, price flat = smart money loading)")
    print("=" * 60)
    if early:
        for label, lo, hi in ranges:
            group = [a for a in early if lo <= a["vol_spike"] < hi]
            if group:
                print(f"\n  {label}")
                for a in group[:10]:
                    bar = "█" * min(int(a["vol_spike"] / 20), 15)
                    print(f"    {a['ticker']:6} ${a['price']:<8.2f} Vol: {a['vol_spike']:+6.0f}% {bar}  Price 1W: {a['price_1w']:+.1f}%  1M: {a['price_1m']:+.1f}%")
    else:
        print("  None found.")

    print("\n" + "=" * 60)
    print("  🟢 BREAKOUTS (volume UP + price UP = trend confirmed)")
    print("=" * 60)
    if confirming:
        for label, lo, hi in ranges:
            group = [a for a in confirming if lo <= a["vol_spike"] < hi]
            if group:
                print(f"\n  {label}")
                for a in group[:10]:
                    bar = "█" * min(int(a["vol_spike"] / 20), 15)
                    print(f"    {a['ticker']:6} ${a['price']:<8.2f} Vol: {a['vol_spike']:+6.0f}% {bar}  Price 1W: {a['price_1w']:+.1f}%  1M: {a['price_1m']:+.1f}%")
    else:
        print("  None found.")

    print("\n" + "=" * 60)
    print("  🔴 DISTRIBUTION (volume UP + price DOWN = institutions selling)")
    print("=" * 60)
    if selling:
        for label, lo, hi in ranges:
            group = [a for a in selling if lo <= a["vol_spike"] < hi]
            if group:
                print(f"\n  {label}")
                for a in group[:10]:
                    bar = "█" * min(int(a["vol_spike"] / 20), 15)
                    print(f"    {a['ticker']:6} ${a['price']:<8.2f} Vol: {a['vol_spike']:+6.0f}% {bar}  Price 1W: {a['price_1w']:+.1f}%  1M: {a['price_1m']:+.1f}%")
    else:
        print("  None found.")


def display_signal_noise(alerts):
    """Analyze persistence across days from saved history."""
    print("\n" + "=" * 60)
    print("  🎯 SIGNAL vs NOISE (appeared multiple days = real signal)")
    print("=" * 60)

    history = {}
    if DB_PATH.exists():
        history = json.loads(DB_PATH.read_text())

    recent_dates = sorted(history.keys())[-5:]
    ticker_appearances = {}
    for date in recent_dates:
        for entry in history[date]:
            t = entry["ticker"]
            if t not in ticker_appearances:
                ticker_appearances[t] = {"days": 0, "vol_spikes": [], "statuses": []}
            ticker_appearances[t]["days"] += 1
            ticker_appearances[t]["vol_spikes"].append(entry["vol_spike"])
            ticker_appearances[t]["statuses"].append(entry["status"])

    signals = []
    noise = []
    for a in alerts:
        t = a["ticker"]
        if t in ticker_appearances and ticker_appearances[t]["days"] >= 3:
            avg_vol = sum(ticker_appearances[t]["vol_spikes"]) / len(ticker_appearances[t]["vol_spikes"])
            signals.append({**a, "days_seen": ticker_appearances[t]["days"], "avg_vol": round(avg_vol, 1)})
        else:
            days = ticker_appearances.get(t, {}).get("days", 1)
            noise.append({**a, "days_seen": days})

    if signals:
        print("\n  ✅ SIGNAL (3+ days of unusual volume = institutional trend)")
        signals.sort(key=lambda x: x["days_seen"], reverse=True)
        for s in signals[:15]:
            trend = "📈 growing" if s["vol_spike"] > s["avg_vol"] else "📉 fading" if s["vol_spike"] < s["avg_vol"] * 0.7 else "➡️ steady"
            print(f"    {s['ticker']:6} ${s['price']:<8.2f} Seen {s['days_seen']}/5 days | Today: {s['vol_spike']:+.0f}% | Avg: {s['avg_vol']:+.0f}% | {trend} | {s['status']}")
    else:
        print("\n  No persistent signals yet — need more history (run with --backfill).")

    if noise:
        print(f"\n  ❌ NOISE ({len(noise)} stocks seen only 1-2 days — likely one-off events)")
        for n in noise[:5]:
            print(f"    {n['ticker']:6} ${n['price']:<8.2f} Seen {n['days_seen']}/5 days | Vol: {n['vol_spike']:+.0f}% | Probably earnings/news spike")


def scan_volume(min_vol_spike: float = 25.0, backfill: bool = False):
    print("=" * 60)
    print("  BROAD MARKET VOLUME SCREENER")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    tickers = get_sp500_tickers()
    print(f"  Scanning {len(tickers)} stocks...")
    if backfill:
        print("  📅 Backfilling last 5 trading days from historical data...")
    print("=" * 60)

    # Download in batches
    batch_size = 30
    all_data = {}
    total_batches = (len(tickers) + batch_size - 1) // batch_size

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        batch_num = i // batch_size + 1
        print(f"  Downloading batch {batch_num}/{total_batches}...", end="\r")
        all_data.update(download_batch(batch))

    print(f"  Downloaded data for {len(all_data)}/{len(tickers)} stocks        ")

    # Backfill: analyze past 5 trading days and save each to history
    if backfill:
        print("\n  Backfilling history:")
        for offset in range(5, 0, -1):  # 5 days ago -> 1 day ago
            date = get_date_for_offset(all_data, offset)
            if not date:
                continue
            day_alerts = analyze_day(all_data, min_vol_spike, offset)
            # Save to history
            history = json.loads(DB_PATH.read_text()) if DB_PATH.exists() else {}
            history[date] = day_alerts
            DB_PATH.write_text(json.dumps(history, indent=2))
            early_count = sum(1 for a in day_alerts if a["status"] == "🟡 EARLY")
            print(f"    📅 {date}: {len(day_alerts)} signals ({early_count} accumulation)")

    # Today's analysis
    alerts = analyze_day(all_data, min_vol_spike, 0)
    today_date = get_date_for_offset(all_data, 0)
    history = json.loads(DB_PATH.read_text()) if DB_PATH.exists() else {}
    history[today_date] = alerts
    DB_PATH.write_text(json.dumps(history, indent=2))

    # Display
    display_results(alerts, min_vol_spike)
    display_signal_noise(alerts)

    print(f"\n✅ Done. {len(all_data)} stocks analyzed, {len(alerts)} signals found.")
    if backfill:
        print("   History backfilled — signal/noise detection is now active.")
    print("   Run daily to keep tracking.\n")


if __name__ == "__main__":
    threshold = 25.0
    backfill = "--backfill" in sys.argv
    for arg in sys.argv[1:]:
        if arg != "--backfill":
            try:
                threshold = float(arg)
            except ValueError:
                pass
    scan_volume(min_vol_spike=threshold, backfill=backfill)
