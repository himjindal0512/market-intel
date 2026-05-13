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
import time
from datetime import datetime, timedelta
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


def get_earnings_dates() -> dict:
    """Fetch upcoming/recent earnings dates from Finnhub. Returns {ticker: earnings_date}."""
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return {}
    try:
        import urllib.request
        today = datetime.now()
        from_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        to_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        url = f"https://finnhub.io/api/v1/calendar/earnings?from={from_date}&to={to_date}&token={api_key}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        earnings = {}
        for item in data.get("earningsCalendar", []):
            symbol = item.get("symbol", "")
            date_str = item.get("date", "")
            if symbol and date_str:
                earnings[symbol] = date_str
        return earnings
    except Exception:
        return {}


def get_earnings_from_yfinance(tickers: list[str]) -> dict:
    """Fallback: get earnings dates from Yahoo Finance for tickers not in Finnhub."""
    earnings = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            cal = t.calendar
            if cal is not None and not cal.empty:
                date = cal.iloc[0, 0] if hasattr(cal, 'iloc') else None
                if date:
                    earnings[ticker] = str(date)[:10]
        except Exception:
            continue
    return earnings


def get_sector_map() -> dict:
    """Get GICS sector for each S&P 500 ticker from the CSV source."""
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        df = pd.read_csv(url)
        col_sym = "Symbol" if "Symbol" in df.columns else df.columns[0]
        col_sec = "Sector" if "Sector" in df.columns else (df.columns[3] if len(df.columns) > 3 else None)
        if not col_sec:
            return {}
        sectors = {}
        for _, row in df.iterrows():
            ticker = str(row[col_sym]).replace(".", "-")
            sectors[ticker] = row[col_sec]
        return sectors
    except Exception:
        return {}


def get_analyst_ratings(tickers: list[str]) -> dict:
    """Fetch recent upgrade/downgrade for alert tickers. Returns {ticker: count_in_7d}."""
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return {}
    import urllib.request
    today = datetime.now()
    from_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")
    results = {}
    for ticker in tickers:
        try:
            url = f"https://finnhub.io/api/v1/stock/upgrade-downgrade?symbol={ticker}&from={from_date}&to={to_date}&token={api_key}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
            if len(data) >= 3:
                results[ticker] = len(data)
            time.sleep(1.1)  # Rate limit: 60/min
        except Exception:
            continue
    return results


def get_ma_targets() -> set:
    """Search SEC EDGAR for recent M&A filings. Returns set of tickers mentioned."""
    try:
        import urllib.request
        keywords = ["acquisition", "merger", "buyout", "tender offer", "take private"]
        tickers_found = set()
        for kw in keywords:
            url = f"https://efts.sec.gov/LATEST/search-index?q=%22{kw.replace(' ', '%20')}%22&dateRange=custom&startdt={(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')}&enddt={datetime.now().strftime('%Y-%m-%d')}&forms=8-K,SC%20TO-T,SC%2013D"
            req = urllib.request.Request(url, headers={"User-Agent": "MarketIntel/1.0 research@example.com"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            for hit in data.get("hits", {}).get("hits", []):
                # Extract ticker from filing if available
                ticker = hit.get("_source", {}).get("tickers", "")
                if ticker:
                    for t in ticker.split(","):
                        t = t.strip().upper()
                        if t:
                            tickers_found.add(t)
        return tickers_found
    except Exception:
        return set()


def get_dividend_splits(tickers: list[str]) -> dict:
    """Check Finnhub for upcoming dividends/splits. Returns {ticker: event_type}."""
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return {}
    import urllib.request
    today = datetime.now()
    from_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
    to_date = (today + timedelta(days=5)).strftime("%Y-%m-%d")
    results = {}
    # Batch dividend calendar (single call)
    try:
        url = f"https://finnhub.io/api/v1/calendar/ipo?from={from_date}&to={to_date}&token={api_key}"
        # Use stock/dividend2 for individual tickers in alerts only
        for ticker in tickers:
            url = f"https://finnhub.io/api/v1/stock/dividend2?symbol={ticker}&from={from_date}&to={to_date}&token={api_key}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
            if data:
                results[ticker] = "DIVIDEND"
            time.sleep(1.1)  # Rate limit
    except Exception:
        pass
    return results


def tag_alerts(alerts: list[dict], scan_date: str) -> list[dict]:
    """Add tags to alerts: EARNINGS, SECTOR, or UNKNOWN."""
    if not alerts:
        return alerts

    # Fetch earnings calendar
    earnings = get_earnings_dates()

    # Fallback: check Yahoo Finance for tickers not in Finnhub
    alert_tickers = [a["ticker"] for a in alerts]
    missing = [t for t in alert_tickers if t not in earnings]
    if missing:
        yf_earnings = get_earnings_from_yfinance(missing[:30])  # Limit to avoid slowness
        earnings.update(yf_earnings)

    # Get sector map
    sectors = get_sector_map()

    # Get analyst ratings (only for tickers in alerts)
    print("  🏷️  Fetching analyst ratings...")
    analyst = get_analyst_ratings(alert_tickers)

    # Get M&A targets from EDGAR
    print("  🏷️  Checking SEC EDGAR for M&A...")
    ma_targets = get_ma_targets()

    # Get dividend/split info
    print("  🏷️  Checking dividends/splits...")
    dividends = get_dividend_splits(alert_tickers)

    # Count sectors in today's alerts for sector clustering
    sector_counts = {}
    for a in alerts:
        sec = sectors.get(a["ticker"], "")
        if sec:
            sector_counts[sec] = sector_counts.get(sec, 0) + 1

    # Tag each alert
    for a in alerts:
        tags = []
        ticker = a["ticker"]

        # Earnings tag: within ±5 trading days
        if ticker in earnings:
            try:
                earn_date = datetime.strptime(earnings[ticker], "%Y-%m-%d")
                today = datetime.strptime(scan_date, "%Y-%m-%d") if scan_date else datetime.now()
                diff = (earn_date - today).days
                if -5 <= diff <= 5:
                    label = f"EARNINGS ({diff:+d}d)" if diff != 0 else "EARNINGS (today)"
                    tags.append(label)
            except Exception:
                pass

        # Analyst tag: 3+ rating changes in 7 days
        if ticker in analyst:
            tags.append(f"ANALYST ({analyst[ticker]} ratings)")

        # M&A tag
        if ticker in ma_targets:
            tags.append("M&A")

        # Dividend/Split tag
        if ticker in dividends:
            tags.append(dividends[ticker])

        # Sector tag: always show sector; highlight if 5+ tickers from same sector
        sec = sectors.get(ticker, "")
        if sec:
            tags.append(sec)
            if sector_counts.get(sec, 0) >= 5:
                tags.append("SECTOR MOVE")

        # If only sector tag, add "Unknown Catalyst"
        has_catalyst = any(not t == sec and t != "SECTOR MOVE" for t in tags)
        if not has_catalyst:
            tags.append("Unknown Catalyst")

        a["tags"] = tags if tags else ["UNKNOWN"]
        a["sector"] = sec

    tagged_count = sum(1 for a in alerts if a["tags"] != ["UNKNOWN"])

    # Gem scoring
    for a in alerts:
        score = 0
        if "EARLY" in a["status"]:
            score += 2
        buy = int(a.get("buy_ratio", "0")[0])
        if buy >= 4:
            score += 3
        elif buy >= 3:
            score += 1
        if a["vol_spike"] >= 100:
            score += 2
        elif a["vol_spike"] >= 50:
            score += 1
        if "Unknown Catalyst" in a.get("tags", []):
            score += 2
        if any(t.startswith("EARNINGS") for t in a.get("tags", [])):
            score -= 3
        if "SECTOR MOVE" in a.get("tags", []):
            score -= 1
        if buy <= 1:
            score -= 3
        a["gem_score"] = score
        if score >= 7:
            a["tags"].insert(0, "💎 GEM")

    gem_count = sum(1 for a in alerts if a.get("gem_score", 0) >= 7)
    print(f"  🏷️  Tagged {tagged_count}/{len(alerts)} alerts | 💎 Gems: {gem_count} | Analyst: {len(analyst)} | M&A: {len(ma_targets)} | Dividends: {len(dividends)}")
    return alerts


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

    # Tag alerts with earnings/sector info
    alerts = tag_alerts(alerts, today_date)

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
