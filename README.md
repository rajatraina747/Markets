# Markets

A £0, single-company research terminal: everything public about a company in one
place, stored cleanly, viewable in an interactive local dashboard. Starts with **TSLA**.

> Research and paper-trading aid, not financial advice. Data is free and public:
> delayed/daily, not real-time. It is not a trading edge on its own.

## Quick start

```sh
./markets add TSLA          # resolve ticker → SEC CIK, start tracking
./markets update TSLA       # fetch everything new, then rebuild the DB
./markets serve --open      # dashboard at http://localhost:5800
```

First `update` downloads the full filing archive (~1,760 filings, ~2 GB raw / ~0.8 GB
gzipped, ~30 min at SEC's rate limit). Later updates only fetch what's new.
`--skip-filings` for a fast refresh of prices + financials only.

Frontend (only needed after UI changes): `cd frontend && npm install && npm run build`.
Dev mode with hot reload: `./markets serve` + `cd frontend && npm run dev` → :5801.

## What's in it (per company)

| Data | Source | Notes |
|---|---|---|
| Profile, former names, full filing index | SEC EDGAR submissions API | every filing since 2005 |
| **Every filing, every document & exhibit** | EDGAR full submission `.txt` | immutable, gzipped; images/PDFs decoded on demand |
| All XBRL financial facts | SEC companyfacts API | ~24k facts for TSLA, 2009→ |
| Income / balance / cash-flow statements | normalized from XBRL | restatements: latest filing wins; Q4 & CF quarters derived |
| Daily prices since IPO, splits, dividends | Yahoo chart API | cross-checked against Nasdaq on each update |
| Insiders: people, roles, every Form 3/4/5 txn | Form 3/4/5 XML | split-adjusted shares & prices |
| Event timeline | 8-K items, filings, splits, insider trades | drives chart markers |
| Full-text search over all filings | SQLite FTS5 | phrases, prefix*, AND/OR |
| >5% holders (13D/13G) | archived Schedule 13D/G filings | XML (2024+), HTML and text cover pages |
| Short interest | FINRA consolidated short interest API | bi-monthly, split-adjusted |
| Pay vs performance | proxy-statement `ecd:` XBRL | CEO / NEO comp, TSR |
| News headlines | Google News RSS + GDELT | accumulates with every update |
| **Your journal** | you | `data/journal.db` — notes + paper trades; back this up |

## Dashboard

- **Overview** — candles/line/area, 50/200 MA, log scale, event markers (results,
  10-K/Q, 8-K, insider buys/sells, splits) → click to open the filing; key stats,
  valuation, margins, returns, quarterly revenue/profit/margins, recent events.
- **Financials** — annual/quarterly statements with sparklines; click a row to chart it
  with growth; hover a cell for its source XBRL tag; ratios table.
- **Filings** — filter the whole archive by group/year/text; read any document or
  exhibit locally (sandboxed), original or extracted text.
- **Search** — full-text across everything, hits by year, highlighted reader.
- **People** — every insider, roles, tenure, holdings over time, every transaction; pay vs performance.
- **Ownership** — >5% holders over time, short interest vs price.
- **News** — archived headlines, coverage vs price, filter by source.
- **10-K compare** — pick two years and an Item (Risk Factors, MD&A, …): what was added, removed, reworded.
- **Journal** — paper trades with thesis/stop/target, P&L and R; notes per company.

Keys: `/` or `⌘K` palette · `g o` overview · `g f` financials · `g l` filings · `g s` search ·
`g p` people · `g w` ownership · `g n` news · `g c` 10-K compare · `g j` journal.

## Layout

```
markets                 CLI (add / update / rebuild / status / serve)
backend/markets/
  net.py                the only network code (rate limits, retries)
  archive.py            immutable raw archive + manifest
  sources/              one module per source: fetch() + pure parse()
  normalize/            raw → SQLite build steps (statements, insiders, events, FTS)
  db/schema.sql         derived-store schema
  api/                  stdlib HTTP JSON API + static frontend
frontend/               React + Vite + TS (lightweight-charts, ECharts, vendored fonts)
tests/                  offline unittest suite on trimmed real fixtures
data/                   (gitignored)
  companies.json        tracked tickers
  companies/TSLA/raw/   the archive — source of truth, never edited
  companies/TSLA/manifest.jsonl   every fetch: url, time, sha256, bytes
  markets.db            derived — `./markets rebuild` recreates it with zero network
  journal.db            YOURS — notes & paper trades (not rebuildable; back it up)
```

## Tests

```sh
python3 -m unittest discover -s tests
```
