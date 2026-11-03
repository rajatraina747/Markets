# Roadmap

## ✅ Done

### P0–P3 · foundation (2026-11-04)
- CLI, rate-limited fetcher, immutable raw archive + manifest, versioned schema, offline tests.
- EDGAR submissions (all pages), full filing archive incl. every exhibit (resumable), XBRL
  companyfacts, Yahoo daily prices + splits/dividends with Nasdaq cross-check.
- Statements (ranked concepts, restatements, derived Q4/CF quarters, FCF), Forms 3/4/5 →
  people/roles/insider txns, 8-K items → event timeline, FTS5 over every filing.
- Dashboard: Overview, Financials, Filings reader, Full-text search, People.

### P4 · depth (2026-11-04)
- Ownership: 13D/13G across XML / HTML / text cover pages; FINRA short interest.
- Pay versus performance (`ecd:` XBRL); News (Google News RSS + GDELT); 10-K compare;
  Journal (`journal.db`, same-origin writes, P&L, R-multiples); intraday partial-bar flag.
- Concept explorer — double-click any Financials cell to see every filing behind the number.

### P4.5 · proxy + institutions (2026-11-04)
- **Proxy tables** — Summary Compensation Table + Director Compensation parsed from every
  DEF 14A (TSLA: 17 proxies, 2011→); alignment is checked against each row's Total.
- **13F institutions** — SEC quarterly data sets (8 most recent, shared under
  `data/reference/`), joined by CUSIP (auto-detected from 13D/G cover pages); latest filing per
  manager-quarter, de-duplicated; top holders, QoQ movers, calls vs puts, % of shares held.

### P5 · beyond one company (2026-11-04)
- **Watchlist** home, **Compare peers** (total-return race + fundamentals), **Screener**.
- **Lite tickers** (`--lite`): prices + financials + ownership/proxy filings, no full archive.
  Auto-industry peers added: GM, F, RIVN, LCID.
- **Macro** — FRED (10y, 2y, curve, Fed funds, CPI, unemployment, VIX, WTI, dollar, GBP/USD) +
  Bank of England Bank Rate, with the current company overlaid on rates and VIX.
- **UK listings** — `./markets add RR.L --ch <number>`: Yahoo LSE prices/dividends, news, and
  Companies House profile / officers / PSCs / filing history (with `MARKETS_CH_KEY`).
- **Nightly update** — `launchd/` plist + `scripts/nightly.sh install` (Tue–Sat 04:15 IST,
  logs in `~/Library/Logs/markets/`). *Written, not installed — installing is Rajat's call.*

## 🔜 Next
- [ ] Get a free Companies House key → enable UK officers/PSCs/filings for RR.L.
- [ ] UK financials: iXBRL accounts from Companies House filings (where filed electronically).
- [ ] Alerts — new 8-K / insider buy / 13D on a watched ticker → macOS notification or phone.
- [ ] Earnings view — results 8-K exhibit 99.1 side by side with the quarter's statements.
- [ ] Sector peers from SIC codes automatically (currently hand-picked).
- [ ] 13F history beyond 2 years (`--periods-13f 40`, ~3.5 GB) if it proves useful.

## ⚠️ Known gaps / honest limits
- No real-time ticks, no broker consensus estimates (not free).
- Company-specific XBRL extensions aren't in companyfacts (Tesla CF D&A after 2018 falls back to
  `Depreciation`). Pre-2009 financials aren't XBRL-tagged.
- 13F data sets include late filers for old quarters; only quarters where ≥60 % of the peak
  manager count has filed are shown.
- Lite isn't tiny: ownership + proxy filings for an old company can be ~0.5 GB (proxy graphics).
