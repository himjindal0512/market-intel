# 📡 Market Intelligence

Volume-based signal detection across S&P 500. Catches institutional moves before they hit headlines.

**Live Dashboard:** [https://himjindal0512.github.io/market-intel/](https://himjindal0512.github.io/market-intel/)

---

## How It Works

Scans all 500 S&P stocks daily for unusual volume activity and categorizes them:

- 🟡 **Accumulation** — Volume surging but price flat. Big players buying quietly before a move.
- 🟢 **Breakouts** — Volume AND price both up. Confirmed trend backed by institutions.
- 🔴 **Distribution** — Volume up but price dropping. Institutions exiting. Avoid.
- 🎯 **Signals** — Stocks with unusual volume for 3+ consecutive days (not noise).

## Status Tags

- **EARLY** — Volume spike but price hasn't moved. Potential early entry. Research why.
- **BREAKOUT** — Price up 5%+ with volume. Move confirmed.
- **SELLING** — Price down 5%+ with volume. Smart money leaving.

## Trend (Signals tab)

- 📈 growing — Volume increasing day over day (strongest signal)
- ➡️ steady — Consistent elevated volume
- 📉 fading — Volume spike dying down (move may be over)

---

## Auto-Updates

Runs automatically every weekday at 4:30 PM ET (after market close) via GitHub Actions. No manual work needed.

To trigger a manual scan: **Actions tab → Daily Market Scan → Run workflow**

---

## Making Changes (from any computer)

```bash
# First time on a new machine
git clone https://github.com/himjindal0512/market-intel.git
cd market-intel

# Edit files, then push
git add .
git commit -m "description of change"
git push
```

Or edit directly on github.com — click any file → ✏️ pencil icon → edit → commit.

---

## Running Locally

**Mac/Linux:**
```bash
cd market-intel
pip3 install -r requirements.txt
python3 volume_scan.py --backfill
python3 app.py
```

**Windows:**
```bash
# 1. Install Python from https://python.org/downloads (check "Add to PATH" during install)
# 2. Install Git from https://git-scm.com/download/win

# 3. Clone the repo (open Command Prompt or PowerShell)
git clone https://github.com/himjindal0512/market-intel.git
cd market-intel

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run the scanner
python volume_scan.py --backfill

# 6. Start the dashboard (http://localhost:5000)
python app.py
```

> On Windows, use `python` and `pip` (not `python3` / `pip3`).

---

## Files

| File | What it does |
|------|-------------|
| `volume_scan.py` | Scans S&P 500 for unusual volume, saves to volume_alerts.json |
| `scanner.py` | Theme-based scanner (Reddit + volume + price for 10 sectors) |
| `app.py` | Local web dashboard (Flask) |
| `build_site.py` | Builds static site for GitHub Pages |
| `templates/dashboard.html` | Dashboard UI template |
| `docs/` | Generated static site (auto-deployed) |

---

## How to Use

1. Check the dashboard daily after market close
2. Look at 🎯 **Signals** tab first — these are persistent (3+ days)
3. Focus on 🟡 **EARLY** tagged stocks — volume up but price flat
4. Use 🔍 **Ticker Lookup** to research any stock
5. Google "[ticker] news" before buying anything — understand WHY volume is up
6. Avoid anything tagged 🔴 SELLING

---

## Cost

$0. Everything uses free public data (Yahoo Finance, GitHub Actions, GitHub Pages).
