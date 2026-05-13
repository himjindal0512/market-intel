"""
Builds a static dashboard site into docs/ folder for GitHub Pages.
Embeds the scan data directly into the HTML so no server needed.
"""

import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "volume_alerts.json"
TEMPLATE_PATH = Path(__file__).parent / "templates" / "dashboard.html"
DOCS_DIR = Path(__file__).parent / "docs"


def build():
    DOCS_DIR.mkdir(exist_ok=True)

    # Load scan data
    history = {}
    if DB_PATH.exists():
        history = json.loads(DB_PATH.read_text())

    dates = sorted(history.keys())
    today_alerts = history[dates[-1]] if dates else []

    # Build signals
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

    scan_date = dates[-1] if dates else ""

    # Read template and inject data
    html = TEMPLATE_PATH.read_text()

    # Replace the API fetch with embedded data
    data_json = json.dumps({"alerts": today_alerts, "signals": signals, "scan_date": scan_date})

    # Replace the loadDashboard function to use embedded data
    html = html.replace(
        """async function loadDashboard() {
    const resp = await fetch('/api/dashboard');
    data = await resp.json();
    renderInsights();
    showTab(document.querySelector('.tab.active'), 'signals');
}""",
        f"""async function loadDashboard() {{
    data = {data_json};
    renderInsights();
    showTab(document.querySelector('.tab.active'), 'signals');
}}"""
    )

    # Replace the ticker search to parse Yahoo Finance directly
    html = html.replace(
        """async function searchTicker() {
    const ticker = document.getElementById('ticker-input').value.trim().toUpperCase();
    if (!ticker) return;
    document.getElementById('ticker-result').innerHTML = '<p class="loading">Analyzing ' + ticker + '...</p>';

    const resp = await fetch('/api/ticker/' + ticker);
    const d = await resp.json();""",
        """async function searchTicker() {
    const ticker = document.getElementById('ticker-input').value.trim().toUpperCase();
    if (!ticker) return;
    document.getElementById('ticker-result').innerHTML = '<p class="loading">Analyzing ' + ticker + '...</p>';

    let d;
    try {
        const resp = await fetch('https://api.allorigins.win/raw?url=' + encodeURIComponent('https://query1.finance.yahoo.com/v8/finance/chart/' + ticker + '?range=3mo&interval=1d'));
        if (!resp.ok) throw new Error('Failed');
        const raw = await resp.json();
        const result = raw.chart.result[0];
        const closes = result.indicators.quote[0].close;
        const volumes = result.indicators.quote[0].volume;
        const opens = result.indicators.quote[0].open;
        const timestamps = result.timestamp;

        // Filter nulls
        const validIdx = closes.map((c,i) => c !== null && volumes[i] !== null && opens[i] !== null ? i : -1).filter(i => i >= 0);
        const c = validIdx.map(i => closes[i]);
        const v = validIdx.map(i => volumes[i]);
        const o = validIdx.map(i => opens[i]);
        const ts = validIdx.map(i => timestamps[i]);

        if (c.length < 22) throw new Error('Not enough data');

        const price = c[c.length - 1];
        const price_1w = (c[c.length-1] / c[c.length-6] - 1) * 100;
        const price_1m = (c[c.length-1] / c[c.length-22] - 1) * 100;
        const vol_recent = v.slice(-5).reduce((a,b)=>a+b,0) / 5;
        const vol_prior = v.slice(-21,-5).reduce((a,b)=>a+b,0) / 16;
        const vol_spike = (vol_recent / Math.max(vol_prior, 1) - 1) * 100;
        const avg_volume = v.slice(-21).reduce((a,b)=>a+b,0) / 21;

        const daily_volume = [];
        for (let i = -10; i < 0; i++) {
            const idx = v.length + i;
            const date = new Date(ts[ts.length + i] * 1000);
            daily_volume.push({ date: (date.getMonth()+1) + '/' + date.getDate(), ratio: Math.round((v[idx] / Math.max(avg_volume,1)) * 100) / 100 });
        }

        d = { ticker, price, price_1w, price_1m, vol_spike, avg_volume, daily_volume, buy_ratio: (c.slice(-5).filter((cl,i) => cl > o.slice(-5)[i]).length) + '/5', signal: Math.abs(price_1w) < 5 ? 'EARLY' : price_1w > 5 ? 'CONFIRMING' : 'SELLING' };
    } catch(e) {
        d = { error: 'Could not fetch data for ' + ticker + '. Try again in a moment.' };
    }"""
    )

    (DOCS_DIR / "index.html").write_text(html)
    print(f"✅ Built static site in docs/ with {len(today_alerts)} alerts, {len(signals)} signals")


if __name__ == "__main__":
    build()
