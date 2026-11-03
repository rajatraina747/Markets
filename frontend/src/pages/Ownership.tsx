import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Institutions, Ownership as OwnershipT, Prices } from '../api'
import { useApi } from '../hooks'
import { EChart, base, axis, C } from '../components/EChart'
import { compact, date, money, pct } from '../format'
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

function InstitutionsPanel({ inst }: { inst: Institutions }) {
  const option = useMemo(() => {
    const q = inst.quarters
    const opt = (pc: string) => q.map((x) => inst.options.find((o) => o.period === x.period && o.put_call === pc)?.shares ?? null)
    return {
      ...base, grid: { left: 56, right: 56, top: 30, bottom: 26 },
      legend: { top: 0, right: 0, textStyle: { color: C.text2, fontSize: 11 } },
      tooltip: { ...base.tooltip, valueFormatter: (v: number) => (v < 5 ? (v * 100).toFixed(1) + '%' : compact(v)) },
      xAxis: { type: 'category', data: q.map((x) => x.period.slice(0, 7)), ...axis },
      yAxis: [{ type: 'value', ...axis, axisLabel: { ...axis.axisLabel, formatter: (v: number) => compact(v, 0) } },
        { type: 'value', ...axis, splitLine: { show: false }, axisLabel: { ...axis.axisLabel, formatter: (v: number) => (v * 100).toFixed(0) + '%' }, min: 0 }],
      series: [
        { name: 'Shares held by 13F filers', type: 'bar', data: q.map((x) => x.shares), color: C.gold, itemStyle: { color: 'rgba(212,175,55,.75)', borderRadius: [3, 3, 0, 0] }, barMaxWidth: 26 },
        { name: 'Calls (underlying)', type: 'line', data: opt('Call'), color: C.up, symbolSize: 5 },
        { name: 'Puts (underlying)', type: 'line', data: opt('Put'), color: C.down, symbolSize: 5 },
        { name: '% of shares outstanding', type: 'line', yAxisIndex: 1, data: q.map((x) => x.pct_of_shares), color: C.blue, symbolSize: 5, lineStyle: { type: 'dashed' } },
      ],
    }
  }, [inst])
  const lastQ = inst.quarters[inst.quarters.length - 1]
  return (
    <>
      <section className="panel">
        <header>Institutional ownership (13F)<span className="grow" />
          {lastQ && <span className="mono dimmer" style={{ textTransform: 'none', letterSpacing: 0 }}>{lastQ.period}: {lastQ.managers.toLocaleString()} managers · {compact(lastQ.shares)} sh · {money(lastQ.value)} · {pct(lastQ.pct_of_shares, 1, false)} of shares</span>}
        </header>
        <div className="body"><EChart option={option} height={260} /></div>
      </section>
      <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1.3fr) minmax(0, 1fr)' }}>
        <section className="panel">
          <header>Top institutions · {inst.last}</header>
          <div style={{ maxHeight: 460, overflow: 'auto' }}>
            <table className="t">
              <thead><tr><th>#</th><th>Manager</th><th className="n">Shares</th><th className="n">% out</th><th className="n">Value</th><th className="n">QoQ</th></tr></thead>
              <tbody>{inst.top.map((r, i) => (
                <tr key={r.manager_cik}><td className="dimmer mono">{i + 1}</td><td style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.manager}</td>
                  <td className="n">{compact(r.shares)}</td><td className="n">{pct(r.pct_of_shares, 2, false)}</td><td className="n dim">{money(r.value)}</td>
                  <td className={'n ' + (r.change === null ? 'gold' : r.change > 0 ? 'up' : r.change < 0 ? 'down' : 'dimmer')}>{r.change === null ? 'new' : (r.change > 0 ? '+' : '') + compact(r.change)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </section>
        <section className="panel">
          <header>Biggest moves · {inst.prev?.slice(0, 7)} → {inst.last?.slice(0, 7)}</header>
          <div style={{ maxHeight: 460, overflow: 'auto' }}>
            <table className="t">
              <thead><tr><th>Manager</th><th className="n">Change</th><th></th></tr></thead>
              <tbody>{inst.movers.map((m, i) => (
                <tr key={i}><td style={{ maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.manager}</td>
                  <td className={'n ' + (m.delta > 0 ? 'up' : 'down')}>{m.delta > 0 ? '+' : ''}{compact(m.delta)}</td>
                  <td>{m.status !== 'changed' ? <span className={'tag ' + (m.status === 'new' ? 'f4' : 'px')}>{m.status}</span> : null}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  )
}

export default function Ownership({ t }: { t: string }) {
  const nav = useNavigate()
  const { data: o, error } = useApi<OwnershipT>(`c/${t}/ownership`)
  const { data: prices } = useApi<Prices>(`c/${t}/prices`)
  const { data: inst } = useApi<Institutions>(`c/${t}/institutions`)
  if (error) return <div className="err">{error}</div>
  if (!o) return <div className="loading">loading ownership</div>
  const lastSi = o.short_interest[o.short_interest.length - 1]
  return (
    <div className="grid">
      <div className="page-title"><h1>Ownership</h1><span className="sub">13F institutions (SEC quarterly data sets) · Schedule 13D/13G (&gt;5% holders) · FINRA short interest · split-adjusted</span></div>
      {inst && inst.quarters.length > 0 ? <InstitutionsPanel inst={inst} /> : inst ? <div className="empty">No 13F data yet — run <code>./markets update {t} --only 13f</code> (CUSIP comes from 13D/G filings).</div> : null}
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
      {o.psc.length > 0 && (
        <section className="panel">
          <header>Persons with significant control (Companies House)</header>
          <table className="t">
            <thead><tr><th>Name</th><th>Kind</th><th>Nature of control</th><th>Notified</th><th>Ceased</th></tr></thead>
            <tbody>{o.psc.map((p, i) => (
              <tr key={i} style={{ opacity: p.ceased ? 0.5 : 1 }}><td style={{ fontWeight: 550 }}>{p.name}</td><td className="dim">{p.kind?.replace(/-/g, ' ')}</td>
                <td style={{ whiteSpace: 'normal' }} className="dim">{p.natures.split(',').map((n) => n.replace(/-/g, ' ')).join(' · ')}</td>
                <td className="mono dim">{p.notified}</td><td className="mono dim">{p.ceased ?? '—'}</td></tr>
            ))}</tbody>
          </table>
        </section>
      )}
      {o.holders.length > 0 && <section className="panel">
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
      </section>}
    </div>
  )
}
