-- markets.db — DERIVED store. Every row is rebuildable from data/companies/*/raw.
-- Bump SCHEMA_VERSION in db/__init__.py when this changes; rebuild recreates the file.

CREATE TABLE companies (
  id            INTEGER PRIMARY KEY,
  ticker        TEXT NOT NULL UNIQUE,
  cik           INTEGER NOT NULL UNIQUE,
  name          TEXT NOT NULL,
  exchange      TEXT,
  sic           TEXT,
  sic_desc      TEXT,
  category      TEXT,
  fiscal_year_end TEXT,
  state_of_inc  TEXT,
  ein           TEXT,
  phone         TEXT,
  website       TEXT,
  business_address TEXT,   -- JSON
  mailing_address  TEXT,   -- JSON
  former_names  TEXT,      -- JSON [{name, from, to}]
  tickers       TEXT,      -- JSON
  exchanges     TEXT,      -- JSON
  updated_at    TEXT
);

CREATE TABLE filings (
  company_id    INTEGER NOT NULL REFERENCES companies(id),
  accession     TEXT NOT NULL,
  form          TEXT NOT NULL,
  filed         TEXT NOT NULL,     -- YYYY-MM-DD
  accepted      TEXT,              -- ISO datetime
  report_date   TEXT,
  act           TEXT,
  file_number   TEXT,
  items         TEXT,              -- 8-K item codes, comma-separated
  size          INTEGER,
  is_xbrl       INTEGER,
  is_inline_xbrl INTEGER,
  primary_doc   TEXT,
  primary_desc  TEXT,
  raw_path      TEXT,              -- relative to company dir; NULL until downloaded
  doc_count     INTEGER,
  PRIMARY KEY (company_id, accession)
);
CREATE INDEX filings_form ON filings(company_id, form, filed);
CREATE INDEX filings_filed ON filings(company_id, filed);

CREATE TABLE filing_documents (
  company_id    INTEGER NOT NULL,
  accession     TEXT NOT NULL,
  seq           INTEGER NOT NULL,
  doc_type      TEXT,              -- 10-K, EX-21.1, GRAPHIC, XML, ...
  filename      TEXT,
  description   TEXT,
  kind          TEXT,              -- text | html | xml | binary
  bytes         INTEGER,
  PRIMARY KEY (company_id, accession, seq)
);

CREATE TABLE facts (
  company_id    INTEGER NOT NULL,
  taxonomy      TEXT NOT NULL,     -- us-gaap, dei, ecd, ...
  concept       TEXT NOT NULL,
  unit          TEXT NOT NULL,
  value         REAL NOT NULL,
  period_start  TEXT,              -- NULL for instant facts
  period_end    TEXT NOT NULL,
  fy            INTEGER,
  fp            TEXT,              -- FY, Q1..Q4
  form          TEXT,
  filed         TEXT,
  accession     TEXT,
  frame         TEXT               -- SEC dedup frame (CY2024Q3 etc.) when present
);
CREATE INDEX facts_concept ON facts(company_id, concept, period_end);

CREATE TABLE concepts (
  company_id    INTEGER NOT NULL,
  taxonomy      TEXT NOT NULL,
  concept       TEXT NOT NULL,
  label         TEXT,
  description   TEXT,
  PRIMARY KEY (company_id, taxonomy, concept)
);

-- Normalized statements: one value per (line, period), latest-filed wins.
CREATE TABLE statement_lines (
  company_id    INTEGER NOT NULL,
  statement     TEXT NOT NULL,     -- IS | BS | CF
  line          TEXT NOT NULL,     -- standard key, e.g. revenue
  period_type   TEXT NOT NULL,     -- annual | quarterly | instant
  period_start  TEXT,
  period_end    TEXT NOT NULL,
  fy            INTEGER,
  fp            TEXT,
  value         REAL NOT NULL,
  concept       TEXT NOT NULL,     -- source concept actually used
  accession     TEXT,
  filed         TEXT,              -- filing date of the value (split-adjustment anchor)
  derived       INTEGER DEFAULT 0, -- 1 when computed (e.g. Q4 = FY - 9M)
  PRIMARY KEY (company_id, statement, line, period_type, period_end)
);

CREATE TABLE prices_daily (
  company_id    INTEGER NOT NULL,
  date          TEXT NOT NULL,
  open REAL, high REAL, low REAL, close REAL,  -- split-adjusted (Yahoo quote)
  adj_close     REAL,                          -- split + dividend adjusted
  volume        INTEGER,
  source        TEXT,
  PRIMARY KEY (company_id, date)
);

CREATE TABLE corporate_actions (
  company_id    INTEGER NOT NULL,
  date          TEXT NOT NULL,
  kind          TEXT NOT NULL,     -- split | dividend
  ratio         TEXT,
  numerator     REAL,
  denominator   REAL,
  amount        REAL,
  PRIMARY KEY (company_id, date, kind)
);

CREATE TABLE quote_meta (
  company_id    INTEGER PRIMARY KEY,
  as_of         TEXT,
  price         REAL,
  prev_close    REAL,
  day_high REAL, day_low REAL, volume INTEGER,
  high_52w REAL, low_52w REAL,
  currency      TEXT,
  exchange      TEXT,
  long_name     TEXT
);

CREATE TABLE people (
  id            INTEGER PRIMARY KEY,
  cik           INTEGER UNIQUE,    -- SEC reporting-owner CIK when known
  name          TEXT NOT NULL
);

CREATE TABLE roles (
  company_id    INTEGER NOT NULL,
  person_id     INTEGER NOT NULL REFERENCES people(id),
  is_director   INTEGER, is_officer INTEGER, is_ten_pct INTEGER, is_other INTEGER,
  title         TEXT,
  first_seen    TEXT,
  last_seen     TEXT,
  PRIMARY KEY (company_id, person_id, title)
);

CREATE TABLE insider_txns (
  company_id    INTEGER NOT NULL,
  accession     TEXT NOT NULL,
  row           INTEGER NOT NULL,
  person_id     INTEGER,
  form          TEXT,              -- 3 | 4 | 5
  table_kind    TEXT,              -- nonDerivative | derivative | holding
  security      TEXT,
  txn_date      TEXT,
  code          TEXT,              -- P buy, S sell, M exercise, A award, G gift, F tax ...
  acq_disp      TEXT,              -- A | D
  shares        REAL,
  price         REAL,
  shares_after  REAL,
  ownership     TEXT,              -- D direct | I indirect
  nature        TEXT,
  is_10b5_1     INTEGER,
  footnotes     TEXT,
  PRIMARY KEY (company_id, accession, row)
);
CREATE INDEX insider_person ON insider_txns(company_id, person_id, txn_date);

CREATE TABLE holders_13dg (
  company_id    INTEGER NOT NULL,
  accession     TEXT NOT NULL,
  form          TEXT,
  filed         TEXT,
  filer_name    TEXT,
  filer_cik     INTEGER,
  shares        REAL,
  percent       REAL,
  event_date    TEXT,
  PRIMARY KEY (company_id, accession, filer_name)
);

CREATE TABLE exec_comp (
  company_id    INTEGER NOT NULL,
  fy            INTEGER NOT NULL,
  concept       TEXT NOT NULL,     -- ecd:PeoTotalCompAmt, ...
  member        TEXT NOT NULL DEFAULT '',
  value         REAL,
  accession     TEXT,
  PRIMARY KEY (company_id, fy, concept, member)
);

-- Unified timeline: everything datable lands here for chart markers.
CREATE TABLE events (
  company_id    INTEGER NOT NULL,
  date          TEXT NOT NULL,
  kind          TEXT NOT NULL,     -- earnings | 8k | filing | split | dividend | insider | holder
  title         TEXT NOT NULL,
  detail        TEXT,
  accession     TEXT,
  importance    INTEGER DEFAULT 1  -- 1 low .. 3 high (drives marker visibility)
);
CREATE INDEX events_date ON events(company_id, date);

CREATE TABLE short_interest (
  company_id    INTEGER NOT NULL,
  settle_date   TEXT NOT NULL,
  shares_short  REAL,
  avg_daily_vol REAL,
  days_to_cover REAL,
  PRIMARY KEY (company_id, settle_date)
);

CREATE TABLE news (
  company_id    INTEGER NOT NULL,
  url           TEXT NOT NULL,
  published     TEXT,
  source        TEXT,
  title         TEXT,
  tone          REAL,
  feed          TEXT,
  PRIMARY KEY (company_id, url)
);
CREATE INDEX news_pub ON news(company_id, published);

-- Plain text of every text/html document, for search + diffing.
CREATE VIRTUAL TABLE filing_text USING fts5(
  body, company_id UNINDEXED, accession UNINDEXED, seq UNINDEXED,
  form UNINDEXED, filed UNINDEXED, doc_type UNINDEXED,
  tokenize = 'porter unicode61'
);

CREATE TABLE build_log (
  company_id    INTEGER,
  step          TEXT,
  rows          INTEGER,
  seconds       REAL,
  built_at      TEXT
);
