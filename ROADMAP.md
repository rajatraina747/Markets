# Roadmap

## P0–P3 — done (2026-11-04)
- **P0 Skeleton** — CLI, config, rate-limited fetcher, immutable raw archive + manifest,
  schema, registry, offline tests.
- **P1 Core ingest** — EDGAR submissions (all pages), full filing archive incl. every
  exhibit (resumable), XBRL companyfacts, Yahoo daily prices + splits/dividends with
  Nasdaq cross-check.
- **P2 Normalize** — statements (ranked concepts, restatements, derived Q4/CF quarters,
  FCF), Forms 3/4/5 → people/roles/insider txns, 8-K items → event timeline, FTS5 index.
- **P3 Dashboard v1** — Overview, Financials, Filings reader, Full-text search, People.

## P4 Depth — done (2026-11-04)
- [x] **Ownership** — SC 13D/13G holders over time (XML + HTML + text cover pages), FINRA short interest.
- [x] **Exec comp** — pay-versus-performance (`ecd:` XBRL) table on People.
- [x] **News** — Google News RSS + GDELT headlines archived per update; coverage vs price.
- [x] **10-K compare** — Item splitter + paragraph/word diff (Risk Factors, MD&A, …).
- [x] **Journal** — notes + paper trades in `data/journal.db` (+ append-only `journal.log.jsonl`),
      P&L, R-multiples, win rate.
- [x] Partial-bar flag — an in-session fetch labels the last bar "intraday", never a close.

## P4.5 Next small things
- [x] Concept explorer — double-click a Financials cell → every raw XBRL fact behind it (
      `/api/c/<T>/facts/<concept>`).
- [ ] Proxy summary-comp table + director list parsed from DEF 14A HTML.
- [ ] 13F institutional holders (SEC quarterly bulk sets) — bigger than 13G's >5% view.

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
