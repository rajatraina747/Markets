import { useMemo, useState } from 'react'
import type { Macro as MacroT, Prices } from '../api'
import { useApi } from '../hooks'
import { EChart, base, axis, C } from '../components/EChart'
import { date } from '../format'

const SINCE: [string, string][] = [['2Y', '2y'], ['5Y', '5y'], ['10Y', '10y'], ['2000', '2000-01-01'], ['MAX', '1960-01-01']]
function sinceDate(k: string) {
  if (!k.endsWith('y')) return k
  const d = new Date(); d.setFullYear(d.getFullYear() - +k.slice(0, -1)); return d.toISOString().slice(0, 10)
}

function yoy(points: [string, number][]): [string, number][] {
  // monthly index → year-over-year % (CPI)
  const m = new Map(points.map(([d, v]) => [d.slice(0, 7), v]))
  return points.map(([d, v]) => {
    const prev = m.get(`${+d.slice(0, 4) - 1}${d.slice(4, 7)}`)
    return prev ? [d, +((v / prev - 1) * 100).toFixed(2)] as [string, number] : null
  }).filter(Boolean) as [string, number][]
}

function Tile({ k, s, since }: { k: string; s: MacroT[string]; since: string }) {
  const pts = k === 'CPIAUCSL' ? yoy(s.points) : s.points
  const shown = pts.filter((p) => p[0] >= since)
  const last = pts[pts.length - 1]
  const yearAgo = pts.find((p) => p[0] >= new Date(new Date(last[0]).getTime() - 365 * 864e5).toISOString().slice(0, 10))
  const delta = last && yearAgo ? last[1] - yearAgo[1] : null
  const option = useMemo(() => ({
    ...base, grid: { left: 40, right: 10, top: 8, bottom: 22 },
    tooltip: { ...base.tooltip, valueFormatter: (v: number) => v?.toFixed(2) },
    xAxis: { type: 'time', ...axis, splitLine: { show: false } },
    yAxis: { type: 'value', scale: true, ...axis },
    series: [{ type: 'line', data: shown, showSymbol: false, lineStyle: { color: C.gold, width: 1.5 }, areaStyle: { color: 'rgba(212,175,55,.08)' }, name: s.label,
      markLine: k === 'T10Y2Y' ? { silent: true, symbol: 'none', data: [{ yAxis: 0 }], lineStyle: { color: C.down, type: 'dashed' }, label: { show: false } } : undefined }],
  }), [shown, s.label, k])
  const unit = k === 'CPIAUCSL' ? '% YoY' : s.unit
  return (
    <section className="panel">
      <header style={{ textTransform: 'none', letterSpacing: 0 }}>
        <span style={{ color: 'var(--text)', fontWeight: 600 }}>{k === 'CPIAUCSL' ? 'US CPI inflation' : s.label}</span>
        <span className="grow" />
        <span className="mono" style={{ fontSize: 15, color: 'var(--text)' }}>{last?.[1].toFixed(2)}<span className="dimmer" style={{ fontSize: 11 }}> {unit}</span></span>
      </header>
      <div style={{ padding: '2px 14px', fontSize: 11 }} className="mono dimmer">
        {date(last?.[0])}{delta !== null ? <> · 1y <span className={delta > 0 ? 'up' : delta < 0 ? 'down' : ''}>{delta > 0 ? '+' : ''}{delta.toFixed(2)}</span></> : null}
      </div>
      <EChart option={option} height={150} />
    </section>
  )
}

export default function Macro({ t }: { t?: string }) {
  const [since, setSince] = useState('5y')
  const { data, error } = useApi<MacroT>('macro?since=1960-01-01')
  const { data: prices } = useApi<Prices>(t ? `c/${t}/prices` : null)
  const s0 = sinceDate(since)
  const groups = useMemo(() => {
    const g: Record<string, [string, MacroT[string]][]> = {}
    for (const [k, s] of Object.entries(data ?? {})) (g[s.group] ??= []).push([k, s])
    return g
  }, [data])
  const overlay = useMemo(() => {
    if (!data?.DGS10 || !prices) return null
    return {
      ...base, grid: { left: 50, right: 50, top: 30, bottom: 26 },
      legend: { top: 0, right: 0, textStyle: { color: C.text2, fontSize: 11 } },
      xAxis: { type: 'time', ...axis },
      yAxis: [{ type: 'log', ...axis, name: t, nameTextStyle: { color: C.text3 } }, { type: 'value', scale: true, ...axis, splitLine: { show: false }, axisLabel: { ...axis.axisLabel, formatter: '{value}%' } }],
      series: [
        { name: `${t} close`, type: 'line', data: prices.rows.filter((r) => r[0] >= s0).map((r) => [r[0], r[4]]), showSymbol: false, lineStyle: { color: C.gold, width: 1.5 }, itemStyle: { color: C.gold } },
        { name: 'US 10y yield', type: 'line', yAxisIndex: 1, data: data.DGS10.points.filter((p) => p[0] >= s0), showSymbol: false, lineStyle: { color: C.blue, width: 1.5 }, itemStyle: { color: C.blue } },
        ...(data.VIXCLS ? [{ name: 'VIX', type: 'line', yAxisIndex: 1, data: data.VIXCLS.points.filter((p) => p[0] >= s0), showSymbol: false, lineStyle: { color: C.violet, width: 1, opacity: 0.7 }, itemStyle: { color: C.violet } }] : []),
      ],
    }
  }, [data, prices, s0, t])
  if (error) return <div className="err">{error}</div>
  if (!data) return <div className="loading">loading macro</div>
  if (!Object.keys(data).length) return <div className="empty">No macro data — run <code>./markets update TSLA --only macro</code></div>
  return (
    <div className="grid">
      <div className="page-title">
        <h1>Macro</h1><span className="sub">FRED + Bank of England · the weather every stock trades in</span>
        <span style={{ flex: 1 }} />
        <div className="seg">{SINCE.map(([l, k]) => <button key={k} className={since === k ? 'on' : ''} onClick={() => setSince(k)}>{l}</button>)}</div>
      </div>
      {overlay && <section className="panel"><header>{t} vs rates &amp; volatility</header><div className="body"><EChart option={overlay} height={280} /></div></section>}
      {Object.entries(groups).map(([g, items]) => (
        <div key={g}>
          <div className="sect" style={{ font: '600 10px var(--sans)', letterSpacing: '.14em', color: 'var(--text-3)', margin: '6px 2px 8px' }}>{g.toUpperCase()}</div>
          <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))' }}>
            {items.map(([k, s]) => <Tile key={k} k={k} s={s} since={s0} />)}
          </div>
        </div>
      ))}
    </div>
  )
}
