import { useMemo, useState } from 'react'
import type { Segments as SegmentsT } from '../api'
import { useApi, useLocal } from '../hooks'
import { EChart, base, axis, C } from '../components/EChart'
import { compact, money, pct } from '../format'
import { Chip, Empty, Loading, PageTitle, Panel, Seg } from '../ui'

const PALETTE = [C.gold, C.blue, C.violet, C.cyan, C.orange, C.up, '#e879a8', '#9ad14b', '#f5c26b', '#7dd3fc', '#c4b5fd', '#94a3b8']
const METRIC_LABEL: Record<string, string> = {
  revenue: 'Revenue', CostOfRevenue: 'Cost of revenue', GrossProfit: 'Gross profit', OperatingIncomeLoss: 'Operating income',
  Assets: 'Assets', DepreciationDepletionAndAmortization: 'D&A', PaymentsToAcquirePropertyPlantAndEquipment: 'Capex',
}

export default function Segments({ t }: { t: string }) {
  const [period, setPeriod] = useLocal<'annual' | 'quarterly'>('seg-period', 'annual')
  const { data, error } = useApi<SegmentsT>(`c/${t}/segments?period=${period}`)
  const [axisKey, setAxisKey] = useState<string | null>(null)
  const [metric, setMetric] = useState('revenue')
  const [showSub, setShowSub] = useState(false)
  const [mode, setMode] = useState<'stack' | 'share' | 'lines'>('stack')
  const ax = data?.axes.find((a) => a.axis === axisKey) ?? data?.axes[0]
  const m = ax?.metrics[metric] ?? (ax ? Object.values(ax.metrics)[0] : undefined)
  const metricKey = ax && m ? Object.keys(ax.metrics).find((k) => ax.metrics[k] === m)! : metric

  const members = useMemo(() => (m?.members ?? []).filter((x) => showSub || !x.is_subtotal), [m, showSub])
  const periods = useMemo(() => (m?.periods ?? []).slice(period === 'quarterly' ? -24 : -16), [m, period])

  const option = useMemo(() => {
    if (!m) return null
    const lbl = (e: string) => {
      const v = members.find((x) => x.values[e])?.values[e]
      return period === 'quarterly' ? `${v?.fp} ${String(v?.fy).slice(2)}` : `FY${v?.fy}`
    }
    const totals = periods.map((e) => members.reduce((s, x) => s + (x.values[e]?.v ?? 0), 0))
    const series = members.map((x, i) => ({
      name: x.label, type: mode === 'lines' ? 'line' : 'bar', stack: mode === 'lines' ? undefined : 'a',
      data: periods.map((e, j) => {
        const v = x.values[e]?.v ?? null
        return mode === 'share' && v !== null && totals[j] ? +(v / totals[j] * 100).toFixed(2) : v
      }),
      color: PALETTE[i % PALETTE.length], barMaxWidth: 34, symbol: 'circle', symbolSize: 5,
      emphasis: { focus: 'series' },
    }))
    if (metricKey === 'revenue' && mode === 'stack' && data) {
      series.push({ name: 'Reported total revenue', type: 'line', stack: undefined, data: periods.map((e) => data.total_revenue[e] ?? null),
        color: '#f5f5f5', barMaxWidth: 0, symbol: 'none', symbolSize: 0, emphasis: { focus: 'series' } } as never)
    }
    return {
      ...base, grid: { left: 64, right: 20, top: 40, bottom: 30 },
      legend: { top: 0, left: 0, type: 'scroll', textStyle: { color: C.text2, fontSize: 11 } },
      tooltip: { ...base.tooltip, axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => (v === null ? '—' : mode === 'share' ? v + '%' : money(v)) },
      xAxis: { type: 'category', data: periods.map(lbl), ...axis },
      yAxis: { type: 'value', ...axis, max: mode === 'share' ? 100 : undefined, axisLabel: { ...axis.axisLabel, formatter: (v: number) => (mode === 'share' ? v + '%' : compact(v, 0)) } },
      series,
    }
  }, [m, members, periods, mode, period, metricKey, data])

  if (error) return <div className="err">{error}</div>
  if (!data) return <Loading what="segments" />
  if (!data.axes.length) return <Empty>No segment data — segments come from each 10-K/10-Q's XBRL instance. Run <code>./markets update {t} --only segments</code> (lite) or check the filing archive (full).</Empty>
  const overlaps = metricKey === 'revenue' ? periods.filter((e) => {
    const tot = data.total_revenue[e], sum = members.reduce((a, x) => a + (x.values[e]?.v ?? 0), 0)
    return tot && sum > tot * 1.02
  }) : []
  const last = periods[periods.length - 1], prev = periods[periods.length - (period === 'quarterly' ? 5 : 2)]
  const lastTotal = members.reduce((s, x) => s + (x.values[last]?.v ?? 0), 0)

  return (
    <div className="grid">
      <PageTitle title="Segments" sub="Product, business-segment and geographic breakdowns from each filing's XBRL · latest filing wins · subtotals detected automatically"
        right={<Seg options={['annual', 'quarterly'] as const} value={period} onChange={setPeriod} />} />
      <div className="filters">
        {data.axes.map((a) => <Chip key={a.axis} on={ax?.axis === a.axis} onClick={() => { setAxisKey(a.axis); setMetric('revenue') }} count={a.n_points}>{a.label}</Chip>)}
        <span style={{ width: 12 }} />
        {ax && Object.keys(ax.metrics).map((k) => <Chip key={k} on={metricKey === k} onClick={() => setMetric(k)}>{METRIC_LABEL[k] ?? k}</Chip>)}
        <span style={{ flex: 1 }} />
        <Seg options={['stack', 'share', 'lines'] as const} value={mode} onChange={setMode} />
        <Chip on={showSub} onClick={() => setShowSub(!showSub)} title="Members that are the sum of other members (e.g. 'Automotive revenues')">subtotals</Chip>
      </div>
      <Panel title={`${METRIC_LABEL[metricKey] ?? metricKey} by ${ax?.label.toLowerCase()}`}>
        {option ? <EChart option={option} height={380} /> : null}
        {overlaps.length > 0 && !showSub && (
          <div className="dimmer" style={{ fontSize: 11, marginTop: 6 }}>
            ⚠ In {overlaps.map((e) => e.slice(0, 7)).join(', ')} the members add up to more than reported revenue — that filing tagged a parent
            line without all its children, so some bars overlap. The white line is the reported total.
          </div>
        )}
      </Panel>
      <Panel title="Breakdown" flush right={<span className="mono dimmer">{last}</span>}>
        <div style={{ overflow: 'auto' }}>
          <table className="t">
            <thead><tr><th>Member</th>{periods.slice().reverse().slice(0, 10).map((e) => <th key={e} className="n">{e.slice(0, 7)}</th>)}<th className="n">Mix</th><th className="n">{period === 'quarterly' ? 'YoY' : 'Growth'}</th></tr></thead>
            <tbody>
              {(m?.members ?? []).filter((x) => showSub || !x.is_subtotal).map((x, i) => {
                const v = x.values[last]?.v, p = prev ? x.values[prev]?.v : undefined
                return (
                  <tr key={x.member} style={x.is_subtotal ? { fontWeight: 600 } : undefined}>
                    <td><span className="dot" style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: x.is_subtotal ? 'transparent' : PALETTE[i % PALETTE.length], marginRight: 8, border: x.is_subtotal ? '1px solid var(--text-3)' : 0 }} />
                      {x.label}{x.is_subtotal ? <span className="dimmer" style={{ fontSize: 10 }}> subtotal</span> : null}</td>
                    {periods.slice().reverse().slice(0, 10).map((e) => { const c = x.values[e]; return <td key={e} className={'n' + (c?.derived ? ' derived' : '')} style={c?.derived ? { fontStyle: 'italic' } : undefined}>{c ? compact(c.v, 1) : <span className="dimmer">·</span>}</td> })}
                    <td className="n">{v !== undefined && lastTotal && !x.is_subtotal ? pct(v / lastTotal, 1, false) : ''}</td>
                    <td className={'n ' + (v !== undefined && p ? (v > p ? 'up' : 'down') : '')}>{v !== undefined && p ? pct(v / p - 1, 0) : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}
