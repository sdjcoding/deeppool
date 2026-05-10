# Operations

## Daily refresh

After KRX market close (~18:00 KST), refresh meta + snapshot + price increments:

```bash
cd /path/to/DeepPool
uv run python -m etf_dash.ingest --job all
```

Job breakdown:

| Job | What it does | Typical duration |
|---|---|---|
| `meta` | Refresh `etf_meta` from `fdr.StockListing('ETF/KR')` and append today's row to `etf_snapshot` for every ticker (~1100 rows). | <10s |
| `prices` | Per-ticker incremental OHLCV pull. Resumes from `last_price_date(ticker) + 1`. | 5–15 min for full universe |
| `validate` | Print row counts and basic sanity checks (NaN/negative closes, missing issuers). | <1s |

`--job all` runs `meta` then `prices`.

### Useful flags

```bash
# One-time bootstrap: pull 5y of history for all ETFs (slow, ~1–2h)
uv run python -m etf_dash.ingest --job prices --full

# Backfill a single ticker
uv run python -m etf_dash.ingest --job prices --full --ticker 069500

# Re-fetch full window (ignore cache) for a small set
uv run python -m etf_dash.ingest --job prices --full \
  --ticker 069500 --ticker 273130 --ticker 360750
```

## Scheduling examples

### macOS (launchd)

`~/Library/LaunchAgents/com.deeppool.daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.deeppool.daily</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd /path/to/DeepPool &amp;&amp; /Users/$USER/.local/bin/uv run python -m etf_dash.ingest --job all &gt;&gt; data/ingest.log 2&gt;&amp;1</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>18</integer>
    <key>Minute</key><integer>30</integer>
  </dict>
  <key>StandardOutPath</key><string>/tmp/deeppool.out</string>
  <key>StandardErrorPath</key><string>/tmp/deeppool.err</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.deeppool.daily.plist
launchctl list | grep deeppool
```

### Linux (cron)

```cron
30 18 * * 1-5 cd /path/to/DeepPool && $HOME/.local/bin/uv run python -m etf_dash.ingest --job all >> data/ingest.log 2>&1
```

## Running the dashboard

### Local

```bash
./scripts/run_dashboard.sh
# or, equivalent:
uv run streamlit run src/etf_dash/ui/app.py
```

Defaults: listens on `http://localhost:8501` (and `http://0.0.0.0:8501` on every
interface — see `.streamlit/config.toml`). Multipage navigation appears in the
sidebar.

### Password gate (always on)

The app refuses to render any page until the user enters the password set in
`.streamlit/secrets.toml`:

```toml
# .streamlit/secrets.toml  (gitignored — never commit)
app_password = "<your-strong-password-here>"
```

Generate a strong password:

```bash
openssl rand -base64 24
```

Then:

```bash
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
$EDITOR .streamlit/secrets.toml      # paste the generated password
```

Or override via env var (useful for CI / headless setups):

```bash
APP_PASSWORD="..." ./scripts/run_dashboard.sh
```

The gate uses `hmac.compare_digest` (constant-time comparison) and stores
`authenticated=True` in `st.session_state` after one successful entry per
browser session.

### Enabling AI 해설 (Anthropic API key)

ETF Detail and Strategies pages have a "🤖 AI 해설" expander that calls the
Anthropic API for a Korean-language summary. Without a key, the section shows
a configuration hint and the rest of the dashboard works normally.

```bash
# 1. Get an API key from https://console.anthropic.com (Workspace API Key)

# 2. Add to secrets.toml
$EDITOR .streamlit/secrets.toml
# add a line:
#   anthropic_api_key = "sk-ant-api03-..."

# 3. Restart Streamlit (Ctrl+C in the run terminal, then ./scripts/run_dashboard.sh)
```

**Cost control:**

- Default model is `claude-sonnet-4-6` ($3/$15 per 1M tokens). Override in
  `config/settings.yaml` → `llm.model` to `claude-haiku-4-5` (~1/3 cost) or
  `claude-opus-4-7` (best quality, ~5x cost).
- Calls use `thinking: disabled` + `effort: low` (configured in code) — minimum
  tokens spent.
- Streamlit caches results for 24h per (ticker, metrics signature), so the
  same ETF/strategy never re-hits the API the same day.
- Estimated cost per call: ETF ≈ $0.005, strategy ≈ $0.008. Realistic monthly
  cost for casual personal use: under $5.

Verify spend at https://console.anthropic.com → Usage.

### Exposing to the internet (ngrok)

For external access from your phone or other networks:

```bash
# 1. Install + authenticate (once)
brew install ngrok
ngrok config add-authtoken <YOUR_TOKEN>     # sign up free at https://ngrok.com

# 2. Set ngrok-level basic auth (second layer on top of the app password)
export NGROK_BASIC_AUTH="alice:another-strong-password"

# 3. In one terminal, run the dashboard
./scripts/run_dashboard.sh

# 4. In another terminal, open the tunnel
./scripts/run_tunnel.sh
```

ngrok prints a URL like `https://abc123.ngrok-free.app`. Visiting it prompts
for the ngrok basic-auth credentials, then the Streamlit password gate. Free
tier URLs change on each restart — buy a paid plan ($8/mo) if you want a
stable hostname.

> ⚠️ Even with both auth layers, a personal investment dashboard exposed on
> a public URL has non-zero risk. Use unique strong passwords, rotate
> occasionally, and prefer Tailscale (private mesh, no public exposure) if
> you only need access from your own devices.

## Troubleshooting

### "ETF 데이터가 없습니다"
The cache DB exists but is empty. Run `--job all` once to populate.

### Ingest errors for specific tickers
Look at `ingest_log` table:
```bash
uv run python -c "
from etf_dash.repository.db import connect
with connect() as c:
    for r in c.execute(
      'SELECT * FROM ingest_log WHERE status != \"ok\" ORDER BY run_at DESC LIMIT 20'
    ):
        print(dict(r))
"
```

### Stale cache after long downtime
Use `--full` to re-fetch the full lookback window:
```bash
uv run python -m etf_dash.ingest --job prices --full
```

### KRX site blocks (future-proofing)
We use FinanceDataReader (Naver-backed) precisely to avoid the `data.krx.co.kr`
bot block that disabled `pykrx` as of 2026-05. If Naver also tightens, options
are in priority order:
1. Register for KRX OPEN API (https://openapi.krx.co.kr) — official, stable
2. Add a NaverScraperProvider for ETF detail pages
3. Re-enable pykrx if/when its session handling is fixed

## Backup / cleanup

```bash
# Backup the SQLite cache
cp data/cache.db data/cache.$(date +%Y%m%d).db.bak

# Reset everything (will require re-ingest from scratch)
rm -rf data/cache.db data/cache.db-shm data/cache.db-wal data/holdings/
```
