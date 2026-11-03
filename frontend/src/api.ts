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
  quote: { as_of: string; currency: string; exchange: string; long_name: string } | null
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
