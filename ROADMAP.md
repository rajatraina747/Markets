# Roadmap

## Done (2026-11-04)
- **P0 Skeleton** — CLI, config, rate-limited fetcher, immutable raw archive + manifest,
  schema, registry, offline tests.
- **P1 Core ingest** — EDGAR submissions (all pages), full filing archive incl. every
  exhibit (resumable), XBRL companyfacts, Yahoo daily prices + splits/dividends with
  Nasdaq cross-check.
- **P2 Normalize** — statements (ranked concepts, restatements, derived Q4/CF quarters,
  FCF), Forms 3/4/5 → people/roles/insider txns, 8-K items → event timeline, FTS5 index.
- **P3 Dashboard v1** — Overview, Financials, Filings reader, Full-text search, People.

## P4 Depth (next)
- [ ] **Ownership** — SC 13D/13G holders over time (parse cover pages), insider net buying,
      FINRA short interest (bi-monthly files).
- [ ] **Exec comp** — `ecd:` pay-vs-performance XBRL already in facts; proxy (DEF 14A)
      summary comp table + director list parsing.
- [ ] **News** — GDELT doc API + Google News RSS, archived daily; volume vs price overlay.
- [ ] **10-K diffs** — section splitter (Item 1A Risk Factors, Item 7 MD&A), YoY diff view.
- [ ] **Journal** — notes + paper trades in `data/journal.db`, P&L vs stored prices.
- [ ] Concept explorer — click any cell → every raw XBRL fact behind it (`/api/.../facts/<concept>`
      exists already).

## P5 Expansion (separate plan)
- More tickers + watchlist + cross-company compare; screener over the local DB.
- UK companies via Companies House API (free key) + LSE prices.
- 13F institutional holders via SEC quarterly bulk datasets.
- Nightly launchd update (logs in `~/Library/Logs/markets/` — TCC gotcha).
- Macro context panel (FRED/BoE) — optional Ember hook.

## Known gaps / honest limits
- No real-time ticks, no broker consensus estimates (not free).
- Tesla's own custom XBRL tags (e.g. CF D&A after 2018) aren't in companyfacts; D&A falls
  back to `Depreciation`.
- Pre-2009 financials aren't XBRL-tagged.
