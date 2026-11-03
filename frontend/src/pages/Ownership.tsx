import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Ownership as OwnershipT, Prices } from '../api'
import { useApi } from '../hooks'
import { EChart, base, axis, C } from '../components/EChart'
import { compact, date } from '../format'
import { formTag } from './Filings'

const PALETTE = [C.gold, C.blue, C.violet, C.cyan, C.orange, C.up, '#e879a8', '#9ad14b']

function HoldersChart({ o }: { o: OwnershipT }) {
  const option = useMemo(() => {
    const series = o.holders.filter((h) => h.filings.some((f) => f.percent !== null)).map((h, i) => ({
      name: h.name, type: 'line', step: 'end', symbol: 'circle', symbolSize: 6,
      data: h.filings.filter((f) => f.percent !== null).map((f) => [f.event_date || f.filed, f.percent]),
      lineStyle: { width: 2, color: PALETTE[i % PALETTE.length] }, itemStyle: { color: PALETTE[i % PALETTE.length] },
    }))
    return {
      ...base, grid: { left: 48, right: 16, top: 34, bottom: 28 },
      legend: { top: 0, left: 0, textStyle: { color: C.text2, fontSize: 11 }, type: 'scroll' },
      tooltip: { ...base.tooltip, trigger: 'item', formatter: (p: { seriesName: string; value: [string, number] }) => `${p.seriesName}<br/>${date(p.value[0])}: <b>${p.value[1]}%</b>` },
      xAxis: { type: 'time', ...axis },
      yAxis: { type: 'value', ...axis, axisLabel: { ...axis.axisLabel, formatter: '{value}%' } },
      series,
    }
  }, [o])
  return <EChart option={option} height={280} />
}

function ShortChart({ o, prices }: { o: OwnershipT; prices: Prices | null }) {
  const option = useMemo(() => {
    const si = o.short_interest
    const pct = si.map((s) => [s.date, o.shares_outstanding ? +(s.shares_short / o.shares_outstanding * 100).toFixed(2) : null])
    const from = si[0]?.date ?? ''
    const px = (prices?.rows ?? []).filter((r) => r[0] >= from).map((r) => [r[0], r[4]])
    return {
      ...base, grid: { left: 60, right: 60, top: 34, bottom: 46 },
      legend: { top: 0, right: 0, textStyle: { color: C.text2, fontSize: 11 } },
      tooltip: { ...base.tooltip },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 14, bottom: 6, borderColor: C.line, fillerColor: 'rgba(212,175,55,.12)', textStyle: { color: C.text3 } }],
      xAxis: { type: 'time', ...axis },
      yAxis: [
        { type: 'value', ...axis, name: 'shares short', nameTextStyle: { color: C.text3, fontSize: 10 }, axisLabel: { ...axis.axisLabel, formatter: (v: number) => compact(v, 0) } },
        { type: 'value', ...axis, splitLine: { show: false }, name: 'price', nameTextStyle: { color: C.text3, fontSize: 10 }, axisLabel: { ...axis.axisLabel } },
      ],
      series: [
        { name: 'Shares short (split-adj.)', type: 'bar', data: si.map((s) => [s.date, Math.round(s.shares_short)]), itemStyle: { color: 'rgba(240,82,79,.6)' }, barMaxWidth: 6 },
        { name: '% of shares out', type: 'line', data: pct, showSymbol: false, lineStyle: { opacity: 0 }, itemStyle: { color: C.orange }, yAxisIndex: 0, tooltip: { valueFormatter: (v: number) => v + '%' } },
        { name: 'Close', type: 'line', yAxisIndex: 1, data: px, showSymbol: false, lineStyle: { color: C.gold, width: 1.5 }, itemStyle: { color: C.gold } },
      ],
    }
  }, [o, prices])
  return <EChart option={option} height={300} />
}

export default function Ownership({ t }: { t: string }) {
  const nav = useNavigate()
  const { data: o, error } = useApi<OwnershipT>(`c/${t}/ownership`)
  const { data: prices } = useApi<Prices>(`c/${t}/prices`)
  if (error) return <div className="err">{error}</div>
  if (!o) return <div className="loading">loading ownership</div>
  const lastSi = o.short_interest[o.short_interest.length - 1]
  return (
    <div className="grid">
      <div className="page-title"><h1>Ownership</h1><span className="sub">Schedule 13D/13G (&gt;5% holders) from the archive · FINRA short interest · split-adjusted</span></div>
      <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)' }}>
        <section className="panel">
          <header>Beneficial owners &gt;5% (reported % of class)</header>
          <div className="body">{o.holders.length ? <HoldersChart o={o} /> : <div className="empty">No 13D/13G filings archived yet.</div>}</div>
        </section>
        <section className="panel">
          <header>Short interest<span className="grow" />
            {lastSi && <span className="mono dimmer" style={{ textTransform: 'none', letterSpacing: 0 }}>{date(lastSi.date)}: {compact(lastSi.shares_short)} sh · {lastSi.days_to_cover?.toFixed(2)} days to cover{o.shares_outstanding ? ` · ${(lastSi.shares_short / o.shares_outstanding * 100).toFixed(2)}% of shares` : ''}</span>}
          </header>
          <div className="body">{o.short_interest.length ? <ShortChart o={o} prices={prices} /> : <div className="empty">Run ./markets update {t} --only shorts</div>}</div>
        </section>
      </div>
      <section className="panel">
        <header>Holders &amp; filings</header>
        <table className="t">
          <thead><tr><th>Holder</th><th>Type</th><th className="n">Latest %</th><th className="n">Shares (adj.)</th><th>Latest filing</th><th>History</th></tr></thead>
          <tbody>
            {o.holders.map((h) => (
              <tr key={h.name + h.latest_filed}>
                <td style={{ fontWeight: 550 }}>{h.name}</td>
                <td>{h.is_13d ? <span className="tag px">13D · active</span> : <span className="tag q10">13G · passive</span>}</td>
                <td className="n">{h.latest_percent !== null ? h.latest_percent.toFixed(2) + '%' : '—'}</td>
                <td className="n">{compact(h.latest_shares_adj)}</td>
                <td className="mono dim">{h.latest_filed}</td>
                <td style={{ whiteSpace: 'normal' }}>
                  <div className="badges">
                    {h.filings.slice().reverse().map((f) => (
                      <span key={f.accession} className="chip" style={{ padding: '2px 8px' }} onClick={() => nav(`/c/${t}/filings/${f.accession}`)} title={f.form}>
                        {f.filed.slice(0, 4)}<span className="n">{f.percent !== null ? f.percent + '%' : '?'}</span>
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="dimmer" style={{ padding: '8px 14px', fontSize: 11 }}>13G = passive investor; 13D = may seek to influence control. Percent is as reported on the cover page. {formTag('SC 13G')} filings older than Dec 2024 are parsed from text and may miss joint filers.</div>
      </section>
    </div>
  )
}
