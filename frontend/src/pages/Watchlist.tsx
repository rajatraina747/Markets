import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { WatchRow } from '../api'
import { useApi } from '../hooks'
import { Spark } from '../components/Spark'
import { money, mult, pct, price, tone } from '../format'

type Sort = { key: string; dir: 1 | -1 }

const COLS: { key: string; label: string; get: (r: WatchRow) => number | null | undefined; fmt: (v: number | null | undefined) => string; toned?: boolean }[] = [
  { key: 'price', label: 'Price', get: (r) => r.price, fmt: price },
  { key: 'change', label: 'Day', get: (r) => r.change, fmt: (v) => pct(v, 2), toned: true },
  { key: '1m', label: '1M', get: (r) => r.returns['1m'], fmt: (v) => pct(v, 0), toned: true },
  { key: 'ytd', label: 'YTD', get: (r) => r.returns.ytd, fmt: (v) => pct(v, 0), toned: true },
  { key: '1y', label: '1Y', get: (r) => r.returns['1y'], fmt: (v) => pct(v, 0), toned: true },
  { key: 'mcap', label: 'Mkt cap', get: (r) => r.market_cap, fmt: (v) => money(v) },
  { key: 'rev', label: 'Revenue TTM', get: (r) => r.ttm.revenue, fmt: (v) => money(v) },
  { key: 'growth', label: 'Rev growth', get: (r) => r.revenue_growth, fmt: (v) => pct(v, 0), toned: true },
  { key: 'gm', label: 'Gross m.', get: (r) => r.margins.gross, fmt: (v) => pct(v, 1, false) },
  { key: 'om', label: 'Op. m.', get: (r) => r.margins.operating, fmt: (v) => pct(v, 1, false), toned: true },
  { key: 'pe', label: 'P/E', get: (r) => r.valuation.pe, fmt: mult },
  { key: 'ps', label: 'P/S', get: (r) => r.valuation.ps, fmt: mult },
]

export default function Watchlist() {
  const nav = useNavigate()
  const { data, error } = useApi<WatchRow[]>('watchlist')
  const [sort, setSort] = useState<Sort>({ key: 'mcap', dir: -1 })
  const [q, setQ] = useState('')
  const [sector, setSector] = useState('')
  const [limit, setLimit] = useState(100)
  const sectors = useMemo(() => [...new Set((data ?? []).map((r) => r.sector).filter(Boolean) as string[])].sort(), [data])
  const rows = useMemo(() => {
    const col = COLS.find((c) => c.key === sort.key)!
    const ql = q.toLowerCase()
    return [...(data ?? [])]
      .filter((r) => (!sector || r.sector === sector) && (!ql || r.ticker.toLowerCase().includes(ql) || r.name.toLowerCase().includes(ql)))
      .sort((a, b) => ((col.get(a) ?? -Infinity) - (col.get(b) ?? -Infinity)) * sort.dir)
  }, [data, sort, q, sector])
  const cards = useMemo(() => (data ?? []).filter((r) => r.tier !== 'core').sort((a, b) => (b.market_cap ?? 0) - (a.market_cap ?? 0)), [data])
  const breadth = useMemo(() => {
    const u = (data ?? []).filter((r) => r.change !== null)
    return { up: u.filter((r) => (r.change ?? 0) > 0).length, n: u.length,
      median: u.length ? u.map((r) => r.change!).sort((a, b) => a - b)[Math.floor(u.length / 2)] : null }
  }, [data])
  if (error) return <div className="err">{error}</div>
  if (!data) return <div className="loading">loading watchlist</div>
  return (
    <div className="grid">
      <div className="page-title"><h1>Watchlist</h1><span className="sub">{data.length} companies tracked · breadth today {breadth.up}/{breadth.n} up · median {pct(breadth.median, 2)} · <code>./markets add TICKER [--lite|--core]</code></span></div>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))' }}>
        {cards.map((r) => (
          <section key={r.ticker} className="panel card-hover" style={{ cursor: 'pointer' }} onClick={() => nav(`/c/${r.ticker}/overview`)}>
            <div style={{ padding: '12px 14px 4px', display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span className="mono gold" style={{ fontWeight: 700, fontSize: 15 }}>{r.ticker}</span>
              <span className="dim" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{r.name}</span>
              {r.tier === 'core' ? <span className="tag">CORE</span> : r.filings === 0 ? <span className="tag q10" title="non-SEC listing: prices, news, macro (+ Companies House with a key)">{r.ticker.includes('.') ? 'LSE' : 'NON-SEC'}</span>
                : r.archived_filings >= r.filings * 0.9 ? <span className="tag k10" title="full filing archive">FULL</span>
                : <span className="tag" title="lite: prices + financials + ownership/proxy filings">LITE</span>}
            </div>
            <div style={{ padding: '0 14px', display: 'flex', alignItems: 'baseline', gap: 10 }}>
              <span className="mono" style={{ fontSize: 20, fontWeight: 600 }}>{price(r.price)}</span>
              <span className={'mono ' + tone(r.change)}>{pct(r.change, 2)}</span>
              {r.partial && <span className="gold mono" style={{ fontSize: 10 }}>intraday</span>}
              <span className="dimmer mono" style={{ marginLeft: 'auto', fontSize: 11 }}>{money(r.market_cap)}</span>
            </div>
            <div style={{ padding: '6px 0 0' }}><Spark vals={r.spark} w={300} h={44} /></div>
          </section>
        ))}
      </div>
      <section className="panel">
        <header>Universe · {rows.length.toLocaleString()} shown<span className="grow" />
          <span style={{ display: 'flex', gap: 8, textTransform: 'none', letterSpacing: 0 }}>
            <input className="input" placeholder="ticker or name…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 180 }} />
            <select className="input" value={sector} onChange={(e) => setSector(e.target.value)}><option value="">All sectors</option>{sectors.map((x) => <option key={x}>{x}</option>)}</select>
          </span>
        </header>
        <div style={{ overflow: 'auto' }}>
          <table className="t">
            <thead><tr><th>Ticker</th><th>Name</th><th>Sector</th>{COLS.map((c) => (
              <th key={c.key} className="n" style={{ cursor: 'pointer', color: sort.key === c.key ? 'var(--gold)' : undefined }}
                onClick={() => setSort({ key: c.key, dir: sort.key === c.key ? (sort.dir === 1 ? -1 : 1) : -1 })}>
                {c.label}{sort.key === c.key ? (sort.dir === 1 ? ' ↑' : ' ↓') : ''}
              </th>))}<th>120d</th></tr></thead>
            <tbody>
              {rows.slice(0, limit).map((r) => (
                <tr key={r.ticker} className="click" onClick={() => nav(`/c/${r.ticker}/overview`)}>
                  <td className="mono gold" style={{ fontWeight: 700 }}>{r.ticker}{r.tier !== 'core' && <span className="dimmer" style={{ fontSize: 9 }}> ●</span>}</td>
                  <td className="dim" style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</td>
                  <td className="dimmer" style={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 12 }}>{r.sector}</td>
                  {COLS.map((c) => { const v = c.get(r); return <td key={c.key} className={'n ' + (c.toned ? tone(v) : '')}>{c.fmt(v)}</td> })}
                  <td><Spark vals={r.spark} w={90} h={22} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > limit && <div style={{ padding: 12, textAlign: 'center' }}><button className="chip" onClick={() => setLimit(limit + 200)}>Show more ({rows.length - limit} left)</button></div>}
        </div>
      </section>
    </div>
  )
}
