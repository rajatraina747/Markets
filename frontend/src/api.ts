// Typed client for the Python API. All endpoints are GET + JSON.

export type Num = number | null

export interface Company {
  id: number; ticker: string; cik: number; name: string; exchange: string | null
  sic: string | null; sic_desc: string | null; category: string | null
  fiscal_year_end: string | null; state_of_inc: string | null; ein: string | null
  phone: string | null; website: string | null; business_address: string | null
  former_names: string | null; tickers: string | null
}

export interface EventRow {
  date: string; kind: string; title: string; detail: string | null
  accession: string | null; importance: number
}

export interface Overview {
  company: Company
  quote: { as_of: string; currency: string; exchange: string; long_name: string; partial: number } | null
  price: Num; prev_close: Num; change: Num; last_bar: string | null
  shares_outstanding: Num; market_cap: Num; enterprise_value: Num
  high_52w: Num; low_52w: Num
  returns: Record<string, Num>
  ttm: Record<string, Num> & { period_end: string | null }
  balance: Record<string, Num> & { as_of: string | null }
  valuation: Record<string, Num>
  margins: Record<string, Num>
  counts: Record<string, number>
  recent_events: EventRow[]
}

export interface Prices { cols: string[]; rows: [string, number, number, number, number, number, number][] }

export interface Cell { v: number; concept: string; derived: number; acc: string | null; fy: number; fp: string }
export interface Statements {
  period: 'annual' | 'quarterly'
  periods: { end: string; fy: number | null; fp: string | null }[]
  lines: { key: string; label: string; statement: 'IS' | 'BS' | 'CF'; unit: string }[]
  cells: Record<string, Record<string, Cell>>
  split_adjusted: boolean
}

export interface FilingRow {
  accession: string; form: string; filed: string; report_date: string | null; items: string | null
  primary_doc: string | null; primary_desc: string | null; size: number | null
  archived: number; doc_count: number | null
}
export interface FilingsPage { total: number; rows: FilingRow[]; groups: Record<string, number>; years: string[] }

export interface FilingDoc { seq: number; doc_type: string; filename: string; description: string | null; kind: string; bytes: number }
export interface FilingDetail { filing: FilingRow & Record<string, unknown>; documents: FilingDoc[]; sec_url: string }

export interface SearchHit { accession: string; seq: number; form: string; filed: string; doc_type: string; snip: string; score: number }
export interface SearchResult { q: string; results: SearchHit[]; total: number; by_year?: { year: string; n: number }[]; error?: string }

export interface Insider {
  id: number; cik: number | null; name: string; titles: string[]
  is_director: number; is_officer: number; is_ten_pct: number
  first_seen: string; last_seen: string; txns?: number
  last_holding?: number; last_holding_date?: string
  net_open_market_usd?: number; net_open_market_usd_1y?: number
}
export interface InsiderTxn {
  accession: string; row: number; person_id: number; name: string; form: string; table_kind: string
  security: string | null; txn_date: string | null; code: string | null; acq_disp: string | null
  shares: Num; price: Num; shares_after: Num; shares_adj: Num; price_adj: Num; shares_after_adj: Num
  ownership: string | null; nature: string | null; is_10b5_1: number; footnotes: string | null
  split_factor: number
}

export interface FactSeries {
  concept: string; label: string | null; description: string | null
  facts: { taxonomy: string; unit: string; value: number; period_start: string | null; period_end: string; form: string; filed: string; accession: string; frame: string | null }[]
}

const cache = new Map<string, Promise<unknown>>()

export async function get<T>(path: string, opts: { fresh?: boolean } = {}): Promise<T> {
  const key = path
  if (!opts.fresh && cache.has(key)) return cache.get(key) as Promise<T>
  const p = fetch('/api/' + path).then(async (r) => {
    const body = await r.json()
    if (!r.ok) throw new Error(body?.error || r.statusText)
    return body as T
  })
  cache.set(key, p)
  p.catch(() => cache.delete(key))
  return p
}

export const fileUrl = (t: string, acc: string, filename: string) =>
  `/api/c/${t}/files/${acc}/${encodeURIComponent(filename)}`

// ---------------------------------------------------------------- P4

export interface HolderFiling { filed: string; form: string; event_date: string | null; shares: Num; shares_adj: Num; percent: Num; accession: string }
export interface Holder { name: string; filings: HolderFiling[]; latest_percent: Num; latest_shares_adj: Num; latest_filed: string; is_13d: boolean }
export interface Ownership {
  holders: Holder[]
  short_interest: { date: string; shares_short: number; avg_daily_vol: number; days_to_cover: Num }[]
  shares_outstanding: Num
  psc: { name: string; kind: string; natures: string; notified: string | null; ceased: string | null }[]
}

export interface NewsItem { url: string; published: string | null; source: string | null; title: string; feed: string }
export interface NewsPage { rows: NewsItem[]; per_day: { day: string; n: number }[]; sources: { source: string; n: number }[]; total: number; first: string | null; last: string | null }

export interface Comp { years: number[]; lines: { concept: string; label: string; values: Record<string, number> }[]; net_income: Record<string, number> }

export interface TenK { accession: string; form: string; filed: string; report_date: string | null; has_text: number }
export type DiffBlock =
  | { op: 'equal'; n: number; first: string }
  | { op: 'add' | 'remove'; text: string }
  | { op: 'change'; words: ['=' | '+' | '-', string][] }
export interface Diff {
  item: string; label: string | null; a: string; b: string; error?: string
  items_a: Record<string, number>; items_b: Record<string, number>; item_labels: Record<string, string>
  stats?: { added: number; removed: number; changed: number; unchanged: number; similarity: number; words_a: number; words_b: number }
  blocks?: DiffBlock[]
}

export interface Note { id: number; ticker: string; title: string | null; body: string; tags: string | null; pinned: number; created: string; updated: string }
export interface Trade {
  id: number; ticker: string; side: 'long' | 'short'; qty: number; entry_date: string; entry_price: number
  stop: Num; target: Num; thesis: string | null; exit_date: string | null; exit_price: Num; exit_reason: string | null
  mark: Num; pnl: Num; pnl_pct: Num; r?: Num; open: boolean; entry_close: Num
}
export interface Journal { notes: Note[]; trades: Trade[]; last: { date: string; close: number } | null }

export async function send<T>(method: 'POST' | 'DELETE', path: string, body?: unknown): Promise<T> {
  const r = await fetch('/api/' + path, {
    method, headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const j = await r.json()
  if (!r.ok) throw new Error(j?.error || r.statusText)
  return j as T
}

// ---------------------------------------------------------------- P4.5 / P5

export interface SctRow { fy: number; name: string; position: string | null; salary: Num; bonus: Num; stock: Num; option: Num; non_equity: Num; pension: Num; other: Num; total: Num; accession: string }
export interface DirRow { proxy_year: number; name: string; fees: Num; stock: Num; option: Num; other: Num; total: Num; accession: string }
export interface ProxyComp { sct: SctRow[]; directors: DirRow[] }

export interface InstHolder { manager: string; manager_cik: string; shares: number; value: number; change: Num; pct_of_shares: Num }
export interface Institutions {
  quarters: { period: string; managers: number; shares: number; value: number; pct_of_shares: Num }[]
  last?: string; prev?: string | null
  top: InstHolder[]
  movers: { manager: string; delta: number; now: number; status: 'new' | 'exited' | 'changed' }[]
  options: { period: string; put_call: string; managers: number; shares: number; value: number }[]
  shares_outstanding: Num
}

export interface MacroSeries { label: string; unit: string; group: string; points: [string, number][] }
export type Macro = Record<string, MacroSeries>

export interface WatchRow {
  ticker: string; name: string; sic_desc: string | null; exchange: string | null
  price: Num; change: Num; partial: boolean; market_cap: Num; enterprise_value: Num
  returns: Record<string, Num>; valuation: Record<string, Num>; margins: Record<string, Num>
  ttm: Record<string, Num>; balance: Record<string, Num>; high_52w: Num; low_52w: Num
  spark: number[]; archived_filings: number; filings: number; revenue_growth: Num
}
export interface CompareRes { start?: string; series: Record<string, [string, number][]> }
