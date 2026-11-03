import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { CompareRes, WatchRow } from '../api'
import { useApi } from '../hooks'
import { EChart, base, axis, C } from '../components/EChart'
import { money, mult, pct } from '../format'

const PALETTE = [C.gold, C.blue, C.violet, C.cyan, C.orange, C.up, '#e879a8', '#9ad14b', '#f5f5f5']
const SINCE: [string, string][] = [['1Y', '1y'], ['3Y', '3y'], ['5Y', '5y'], ['2021', '2021-01-01'], ['MAX', '1990-01-01']]

function sinceDate(k: string) {
  const d = new Date()
  if (k === '1y') d.setFullYear(d.getFullYear() - 1)
  else if (k === '3y') d.setFullYear(d.getFullYear() - 3)
  else if (k === '5y') d.setFullYear(d.getFullYear() - 5)
  else return k
  return d.toISOString().slice(0, 10)
}

const METRICS: { label: string; get: (r: WatchRow) => number | null | undefined; fmt: (v: number | null | undefined) => string; better: 1 | -1 }[] = [
  { label: 'Market cap', get: (r) => r.market_cap, fmt: (v) => money(v), better: 1 },
  { label: 'Revenue (TTM)', get: (r) => r.ttm.revenue, fmt: (v) => money(v), better: 1 },
  { label: 'Revenue growth (YoY TTM)', get: (r) => r.revenue_growth, fmt: (v) => pct(v, 1), better: 1 },
  { label: 'Gross margin', get: (r) => r.margins.gross, fmt: (v) => pct(v, 1, false), better: 1 },
  { label: 'Operating margin', get: (r) => r.margins.operating, fmt: (v) => pct(v, 1, false), better: 1 },
  { label: 'Net margin', get: (r) => r.margins.net, fmt: (v) => pct(v, 1, false), better: 1 },
  { label: 'FCF margin', get: (r) => r.margins.fcf, fmt: (v) => pct(v, 1, false), better: 1 },
  { label: 'R&D / revenue', get: (r) => r.margins.rnd, fmt: (v) => pct(v, 1, false), better: 1 },
  { label: 'P/E', get: (r) => r.valuation.pe, fmt: mult, better: -1 },
  { label: 'P/S', get: (r) => r.valuation.ps, fmt: mult, better: -1 },
  { label: 'EV / sales', get: (r) => r.valuation.ev_sales, fmt: mult, better: -1 },
  { label: 'Cash + ST investments', get: (r) => r.balance.total_cash, fmt: (v) => money(v), better: 1 },
  { label: 'Total debt', get: (r) => r.balance.total_debt, fmt: (v) => money(v), better: -1 },
  { label: '1-year return', get: (r) => r.returns['1y'], fmt: (v) => pct(v, 0), better: 1 },
]

export default function Peers() {
  const [sp, setSp] = useSearchParams()
  const { data: all } = useApi<WatchRow[]>('watchlist')
  const picked = (sp.get('t') ?? '').split(',').filter(Boolean)
  const tickers = picked.length ? picked : (all ?? []).map((r) => r.ticker)
  const since = sp.get('since') ?? '3y'
  const { data: cmp } = useApi<CompareRes>(tickers.length ? `compare?tickers=${tickers.join(',')}&since=${sinceDate(since)}` : null)
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); n.set(k, v); setSp(n, { replace: true }) }
  const toggle = (t: string) => set('t', (tickers.includes(t) ? tickers.filter((x) => x !== t) : [...tickers, t]).join(','))
  const rows = (all ?? []).filter((r) => tickers.includes(r.ticker))

  const option = useMemo(() => cmp && {
    ...base, grid: { left: 52, right: 90, top: 16, bottom: 46 },
    tooltip: { ...base.tooltip, valueFormatter: (v: number) => (v - 100 >= 0 ? '+' : '') + (v - 100).toFixed(1) + '%' },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 14, bottom: 6, borderColor: C.line, fillerColor: 'rgba(212,175,55,.12)', textStyle: { color: C.text3 } }],
    xAxis: { type: 'time', ...axis },
    yAxis: { type: 'log', ...axis, axisLabel: { ...axis.axisLabel, formatter: (v: number) => (v - 100 >= 0 ? '+' : '') + (v - 100).toFixed(0) + '%' } },
    series: Object.entries(cmp.series).map(([t, pts]) => {
      const i = (all ?? []).findIndex((r) => r.ticker === t)
      return { name: t, type: 'line', data: pts, showSymbol: false, lineStyle: { width: 2, color: PALETTE[i % PALETTE.length] }, itemStyle: { color: PALETTE[i % PALETTE.length] },
        endLabel: { show: true, formatter: (p: { seriesName: string; value: [string, number] }) => `${p.seriesName} ${p.value[1] >= 100 ? '+' : ''}${(p.value[1] - 100).toFixed(0)}%`, color: PALETTE[i % PALETTE.length], fontFamily: 'JetBrains Mono', fontSize: 11 } }
    }),
  }, [cmp, all])

  return (
    <div className="grid">
      <div className="page-title"><h1>Compare</h1><span className="sub">Total-return (dividend-adjusted, local currency) performance rebased to the first common date · fundamentals side by side · best in each row highlighted</span></div>
      <div className="filters">
        {(all ?? []).map((r, i) => (
          <span key={r.ticker} className={'chip' + (tickers.includes(r.ticker) ? ' on' : '')} onClick={() => toggle(r.ticker)}>
            <span className="dot" style={{ background: PALETTE[i % PALETTE.length] }} />{r.ticker}
          </span>
        ))}
        <span style={{ flex: 1 }} />
        <div className="seg">{SINCE.map(([l, k]) => <button key={k} className={since === k ? 'on' : ''} onClick={() => set('since', k)}>{l}</button>)}</div>
      </div>
      <section className="panel">
        <header>Performance since {cmp?.start ?? '…'}</header>
        <div className="body">{option ? <EChart option={option} height={380} /> : <div className="loading">loading</div>}</div>
      </section>
      <section className="panel">
        <header>Fundamentals</header>
        <table className="t">
          <thead><tr><th>Metric</th>{rows.map((r) => <th key={r.ticker} className="n gold">{r.ticker}</th>)}</tr></thead>
          <tbody>
            {METRICS.map((m) => {
              const vals = rows.map((r) => m.get(r) ?? null)
              const finite = vals.filter((v): v is number => v !== null && isFinite(v))
              const best = finite.length > 1 ? (m.better === 1 ? Math.max(...finite) : Math.min(...finite.filter((v) => v > 0))) : null
              return (
                <tr key={m.label}>
                  <td>{m.label}</td>
                  {vals.map((v, i) => <td key={i} className={'n' + (v !== null && v === best ? ' gold' : '') + (v !== null && v < 0 ? ' down' : '')} style={v !== null && v === best ? { fontWeight: 700 } : undefined}>{m.fmt(v)}</td>)}
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>
    </div>
  )
}
