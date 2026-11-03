// Workspace widgets: compact, self-contained views that render for any ticker.
// Each is (ticker) → content, sized by its panel. Keep them light: one or two API calls each.
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { EarningsT, EventRow, FilingsPage, InsiderTxn, Macro, NewsPage, Overview, Prices, Segments, Statements, WatchRow } from './types'
import { useApi } from '../hooks'
import { PriceChart, EVENT_KINDS } from '../components/PriceChart'
import { EChart, base, axis, C } from '../components/EChart'
import { Spark } from '../components/Spark'
import { compact, date, money, mult, pct, price, tone } from '../format'
import { Bar, Delta, Loading, Stat, StatGrid } from '../ui'
import { formTag } from '../pages/Filings'

export type WidgetKind = 'chart' | 'stats' | 'fundamentals' | 'segments' | 'earnings' | 'insiders' | 'filings' | 'news' | 'macro' | 'watchlist' | 'events'

export const WIDGETS: Record<WidgetKind, { label: string; icon: string; linked: boolean; w: number; h: number }> = {
  chart: { label: 'Price chart', icon: '◉', linked: true, w: 8, h: 9 },
  stats: { label: 'Key stats', icon: '▦', linked: true, w: 4, h: 9 },
  fundamentals: { label: 'Quarterly P&L', icon: '▤', linked: true, w: 6, h: 7 },
  segments: { label: 'Segments', icon: '◫', linked: true, w: 6, h: 7 },
  earnings: { label: 'Earnings reactions', icon: '◆', linked: true, w: 6, h: 7 },
  insiders: { label: 'Insider trades', icon: '◎', linked: true, w: 4, h: 7 },
  filings: { label: 'Latest filings', icon: '▦', linked: true, w: 4, h: 7 },
  news: { label: 'Headlines', icon: '≋', linked: true, w: 4, h: 7 },
  events: { label: 'Event feed', icon: '•', linked: true, w: 4, h: 7 },
  macro: { label: 'Macro series', icon: '∿', linked: false, w: 4, h: 5 },
  watchlist: { label: 'Watchlist', icon: '☰', linked: false, w: 4, h: 9 },
}

const fill = { height: '100%', overflow: 'auto' } as const

export function ChartW({ t }: { t: string }) {
  const { data: prices } = useApi<Prices>(`c/${t}/prices`)
  const { data: events } = useApi<EventRow[]>(`c/${t}/events?min_importance=2`)
  const kinds = useMemo(() => new Set(['earnings', 'split', 'insider']), [])
  if (!prices) return <Loading />
  return <div style={{ height: '100%', overflow: 'hidden' }}><PriceChart prices={prices} events={events ?? []} kinds={kinds} height={9999} fluid /></div>
}

export function StatsW({ t }: { t: string }) {
  const { data: ov } = useApi<Overview>(`c/${t}/overview`)
  if (!ov) return <Loading />
  return (
    <div style={fill}>
      <div style={{ padding: '10px 12px', display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span className="mono" style={{ fontSize: 22, fontWeight: 600 }}>{price(ov.price)}</span>
        <Delta v={ov.change} digits={2} />
        {ov.quote?.partial ? <span className="gold mono" style={{ fontSize: 10 }}>intraday</span> : null}
      </div>
      <StatGrid cols={2}>
        <Stat label="Market cap" value={money(ov.market_cap)} />
        <Stat label="P/E · P/S" value={`${mult(ov.valuation.pe)} · ${mult(ov.valuation.ps)}`} />
        <Stat label="Revenue TTM" value={money(ov.ttm.revenue)} />
        <Stat label="Op. margin" value={pct(ov.margins.operating, 1, false)} tone={(ov.margins.operating ?? 0) < 0 ? 'down' : ''} />
        <Stat label="FCF TTM" value={money(ov.ttm.free_cash_flow)} tone={tone(ov.ttm.free_cash_flow) as 'up' | 'down' | ''} />
        <Stat label="Cash / debt" value={`${money(ov.balance.total_cash)} / ${money(ov.balance.total_debt)}`} />
        <Stat label="1Y · YTD" value={<><Delta v={ov.returns['1y']} digits={0} /> · <Delta v={ov.returns.ytd} digits={0} /></>} />
        <Stat label="52w" value={`${price(ov.low_52w)}–${price(ov.high_52w)}`} />
      </StatGrid>
    </div>
  )
}

export function FundamentalsW({ t }: { t: string }) {
  const { data: st } = useApi<Statements>(`c/${t}/statements?period=quarterly`)
  const option = useMemo(() => {
    if (!st) return null
    const ps = [...st.periods].reverse().slice(-12)
    const v = (k: string) => ps.map((p) => st.cells[k]?.[p.end]?.v ?? null)
    const rev = v('revenue'), op = v('operating_income')
    return {
      ...base, grid: { left: 44, right: 36, top: 26, bottom: 22 },
      legend: { top: 0, right: 0, textStyle: { color: C.text2, fontSize: 10 }, itemWidth: 8, itemHeight: 6 },
      tooltip: { ...base.tooltip, valueFormatter: (x: number) => (Math.abs(x) > 1000 ? money(x) : x + '%') },
      xAxis: { type: 'category', data: ps.map((p) => `${p.fp}'${String(p.fy).slice(2)}`), ...axis },
      yAxis: [{ type: 'value', ...axis, axisLabel: { ...axis.axisLabel, formatter: (x: number) => compact(x, 0) } },
        { type: 'value', ...axis, splitLine: { show: false }, axisLabel: { ...axis.axisLabel, formatter: '{value}%' } }],
      series: [
        { name: 'Revenue', type: 'bar', data: rev, color: C.gold, barMaxWidth: 14 },
        { name: 'Op. margin', type: 'line', yAxisIndex: 1, color: C.violet, symbol: 'none',
          data: op.map((x, i) => (x !== null && rev[i] ? +(x / rev[i]! * 100).toFixed(1) : null)) },
      ],
    }
  }, [st])
  return option ? <EChart option={option} height="100%" /> : <Loading />
}

export function SegmentsW({ t }: { t: string }) {
  const { data } = useApi<Segments>(`c/${t}/segments?period=annual`)
  const option = useMemo(() => {
    const ax = data?.axes[0]
    const m = ax?.metrics.revenue ?? (ax ? Object.values(ax.metrics)[0] : undefined)
    if (!m) return null
    const ps = m.periods.slice(-8)
    const mems = m.members.filter((x) => !x.is_subtotal).slice(0, 8)
    const pal = [C.gold, C.blue, C.violet, C.cyan, C.orange, C.up, '#e879a8', '#9ad14b']
    return {
      ...base, grid: { left: 44, right: 10, top: 30, bottom: 22 },
      legend: { top: 0, left: 0, type: 'scroll', textStyle: { color: C.text2, fontSize: 10 }, itemWidth: 8, itemHeight: 6 },
      tooltip: { ...base.tooltip, axisPointer: { type: 'shadow' }, valueFormatter: (x: number) => money(x) },
      xAxis: { type: 'category', data: ps.map((p) => p.slice(0, 4)), ...axis },
      yAxis: { type: 'value', ...axis, axisLabel: { ...axis.axisLabel, formatter: (x: number) => compact(x, 0) } },
      series: mems.map((x, i) => ({ name: x.label, type: 'bar', stack: 'a', color: pal[i], barMaxWidth: 22,
        data: ps.map((p) => x.values[p]?.v ?? null) })),
    }
  }, [data])
  if (!data) return <Loading />
  return option ? <EChart option={option} height="100%" /> : <div className="empty">No segment data</div>
}

export function EarningsW({ t }: { t: string }) {
  const { data } = useApi<EarningsT>(`c/${t}/earnings`)
  if (!data) return <Loading />
  const rows = data.rows.filter((r) => r.kind === 'earnings').slice(0, 12)
  return (
    <div style={fill}>
      <div className="mono dimmer" style={{ padding: '6px 12px', fontSize: 11 }}>typical move {pct(data.stats.avg_abs_day, 1, false)} · {data.stats.up}↑ {data.stats.down}↓</div>
      <table className="t"><tbody>{rows.map((r) => (
        <tr key={r.accession}><td><b>{r.fp} {r.fy}</b></td><td className="mono dim">{r.filed}</td>
          <td className="n"><Delta v={r.metrics?.revenue?.yoy} digits={0} /></td>
          <td className="n"><Delta v={r.day} /></td><td><Bar v={r.day} max={0.15} w={60} /></td><td className="n"><Delta v={r.d5} /></td></tr>
      ))}</tbody></table>
    </div>
  )
}

export function InsidersW({ t }: { t: string }) {
  const { data } = useApi<InsiderTxn[]>(`c/${t}/insiders/txns?codes=P,S&limit=60`)
  if (!data) return <Loading />
  if (!data.length) return <div className="empty">No open-market insider trades archived</div>
  return (
    <div style={fill}><table className="t"><tbody>{data.map((x) => (
      <tr key={x.accession + x.row}><td className="mono dim">{x.txn_date}</td><td style={{ maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis' }}>{x.name}</td>
        <td className={'n ' + (x.code === 'P' ? 'up' : 'down')}>{x.code === 'P' ? 'buy' : 'sell'} {compact(x.shares_adj)}</td>
        <td className="n dim">{money((x.shares ?? 0) * (x.price ?? 0))}</td></tr>
    ))}</tbody></table></div>
  )
}

export function FilingsW({ t }: { t: string }) {
  const nav = useNavigate()
  const { data } = useApi<FilingsPage>(`c/${t}/filings?limit=40`)
  if (!data) return <Loading />
  return (
    <div style={fill}><table className="t"><tbody>{data.rows.map((r) => (
      <tr key={r.accession} className="click" onClick={() => nav(`/c/${t}/filings/${r.accession}`)}>
        <td className="mono dim">{r.filed}</td><td>{formTag(r.form)}</td><td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.primary_desc || r.form}</td></tr>
    ))}</tbody></table></div>
  )
}

export function NewsW({ t }: { t: string }) {
  const { data } = useApi<NewsPage>(`c/${t}/news?limit=60`)
  if (!data) return <Loading />
  if (!data.rows.length) return <div className="empty">No headlines archived for {t}</div>
  return (
    <div style={fill}>{data.rows.map((n) => (
      <a key={n.url} href={n.url} target="_blank" rel="noreferrer noopener" className="ev" style={{ color: 'var(--text)', gridTemplateColumns: '64px 1fr' }}>
        <span className="d">{n.published?.slice(5, 10)}</span><span><span className="t" style={{ fontWeight: 450 }}>{n.title}</span> <span className="dimmer" style={{ fontSize: 11 }}>{n.source}</span></span>
      </a>
    ))}</div>
  )
}

export function EventsW({ t }: { t: string }) {
  const nav = useNavigate()
  const { data } = useApi<EventRow[]>(`c/${t}/events?min_importance=2`)
  if (!data) return <Loading />
  return (
    <div style={fill}>{data.slice(0, 80).map((e, i) => (
      <div key={i} className="ev" style={{ cursor: e.accession ? 'pointer' : 'default', gridTemplateColumns: '74px 1fr' }} onClick={() => e.accession && nav(`/c/${t}/filings/${e.accession}`)}>
        <div className="d">{e.date}</div>
        <div><span className="bar" style={{ background: EVENT_KINDS[e.kind]?.color ?? C.text3 }} />{e.title}{e.detail ? <span className="dimmer" style={{ fontSize: 11 }}> · {e.detail}</span> : null}</div>
      </div>
    ))}</div>
  )
}

export function MacroW({ series }: { series: string }) {
  const { data } = useApi<Macro>(`macro?keys=${series}&since=2016-01-01`)
  const s = data?.[series]
  const option = useMemo(() => s && {
    ...base, grid: { left: 36, right: 8, top: 8, bottom: 20 },
    tooltip: { ...base.tooltip, valueFormatter: (v: number) => v?.toFixed(2) },
    xAxis: { type: 'time', ...axis, splitLine: { show: false } }, yAxis: { type: 'value', scale: true, ...axis },
    series: [{ type: 'line', data: s.points, showSymbol: false, color: C.gold, areaStyle: { color: 'rgba(212,175,55,.08)' }, name: s.label }],
  }, [s])
  if (!data) return <Loading />
  if (!s) return <div className="empty">No data for {series}</div>
  const last = s.points[s.points.length - 1]
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '6px 12px' }}><span className="mono" style={{ fontSize: 16 }}>{last[1].toFixed(2)}</span> <span className="dimmer" style={{ fontSize: 11 }}>{s.unit} · {date(last[0])}</span></div>
      <div style={{ flex: 1, minHeight: 0 }}><EChart option={option!} height="100%" /></div>
    </div>
  )
}

export function WatchlistW({ onPick }: { onPick: (t: string) => void }) {
  const { data } = useApi<WatchRow[]>('watchlist')
  const rows = useMemo(() => [...(data ?? [])].sort((a, b) => Number(b.tier !== 'core') - Number(a.tier !== 'core') || (b.market_cap ?? 0) - (a.market_cap ?? 0)).slice(0, 80), [data])
  if (!data) return <Loading />
  return (
    <div style={fill}><table className="t"><tbody>{rows.map((r) => (
      <tr key={r.ticker} className="click" onClick={() => onPick(r.ticker)} title="send to this panel's link group">
        <td className="mono gold" style={{ fontWeight: 700 }}>{r.ticker}</td><td className="n mono">{price(r.price)}</td>
        <td className="n"><Delta v={r.change} digits={2} /></td><td><Spark vals={r.spark.slice(-60)} w={70} h={18} /></td></tr>
    ))}</tbody></table></div>
  )
}
