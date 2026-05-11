# Market Intelligence Signal Detector

Catches investment themes early by tracking **acceleration** (rate of change) across multiple signals.

## The Key Insight

You missed semis because by the time NVDA was on every headline, the signal was saturated.
This tool flags themes at the "whisper" stage: search interest growing 3-5x week-over-week
but stocks haven't moved yet.

## How It Works

1. **Google Trends** — tracks search acceleration for sector keywords
2. **Price/Volume** — detects breakouts and unusual volume in theme stocks
3. **Composite Score** — weights trend acceleration (50%), price momentum (30%), volume (20%)
4. **Early Signal Alert** — flags themes where search is surging but prices haven't caught up

## Setup

```bash
cd market-intel
pip install -r requirements.txt
python scanner.py
```

## Interpreting Results

- **🔥 Score > 20** — Strong signal, theme is accelerating fast
- **📈 Score 5-20** — Moderate momentum building
- **📊 Score < 5** — Quiet, no signal yet
- **🚨 Early Signal** — The money shot: high trend acceleration + low price move = you're early

## Extending

Add more themes by editing `SECTOR_THEMES` and `THEME_TICKERS` in scanner.py.
Run daily and compare scores over time — consistent acceleration = real trend, not noise.

## Next Steps (future iterations)

- Reddit mention velocity (PRAW API)
- SEC 13F filing tracker (unusual institutional buying)
- Earnings call keyword extraction
- Slack/Discord alerts when score crosses threshold
- Historical backtesting of signal accuracy
