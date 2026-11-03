import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Earnings as EarningsT, EarningsRow } from '../api'
import { useApi } from '../hooks'
import { EChart, base, axis, C } from '../components/EChart'
import { date, money, pct } from '../format'
import { Bar, Chip, Delta, Empty, Loading, PageTitle, Panel, Stat, StatGrid, Tag } from '../ui'

const TIMING: Record<string, string> = { amc: 'after close', bmo: 'before open', intraday: 'intraday' }
const LINES: [string, string, 'usd' | 'eps' | 'pct'][] = [
  ['revenue', 'Revenue', 'usd'], ['gross_profit', 'Gross profit', 'usd'], ['gross_profit_margin', 'Gross margin', 'pct'],
  ['operating_income', 'Operating income', 'usd'], ['operating_income_margin', 'Operating margin', 'pct'],
  ['net_income', 'Net income', 'usd'], ['eps_diluted', 'EPS (diluted, as reported)', 'eps'],
  ['cfo', 'Operating cash flow', 'usd'], ['free_cash_flow', 'Free cash flow', 'usd'],
]

function fmt(v: number | null | undefined, k: 'usd' | 'eps' | 'pct') {
  if (v === null || v === undefined) return '—'
  return k === 'usd' ? money(v) : k === 'eps' ? v.toFixed(2) : pct(v, 1, false)
}

function ReactionChart({ rows, sel, onSel }: { rows: EarningsRow[]; sel: string | null; onSel: (a: string) => void }) {
  const er = rows.filter((r) => r.day !== null).slice().reverse()
  const option = useMemo(() => ({
    ...base, grid: { left: 48, right: 16, top: 30, bottom: 30 },
    legend: { top: 0, right: 0, textStyle: { color: C.text2, fontSize: 11 } },
    tooltip: { ...base.tooltip, axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => (v === null ? '—' : (v > 0 ? '+' : '') + v + '%') },
    xAxis: { type: 'category', data: er.map((r) => (r.kind === 'earnings' ? `${r.fp} ${String(r.fy).slice(2)}` : `upd ${r.filed.slice(2, 7)}`)), ...axis },
    yAxis: { type: 'value', ...axis, axisLabel: { ...axis.axisLabel, formatter: '{value}%' } },
    series: [
      { name: 'Reaction day', type: 'bar', data: er.map((r) => ({ value: +((r.day ?? 0) * 100).toFixed(2), itemStyle: {
        color: (r.day ?? 0) >= 0 ? C.up : C.down, opacity: r.kind === 'earnings' ? (sel && sel !== r.accession ? 0.45 : 1) : 0.35,
        borderColor: sel === r.accession ? C.gold : undefined, borderWidth: sel === r.accession ? 2 : 0 } })), barMaxWidth: 16, color: C.up },
      { name: '+5 days', type: 'line', data: er.map((r) => (r.d5 === null ? null : +((r.d5 ?? 0) * 100).toFixed(2))), color: C.gold, symbolSize: 4, lineStyle: { width: 1 } },
    ],
  }), [er, sel])
  return <EChart option={option} height={240} onClick={(p) => { const i = (p as { dataIndex: number }).dataIndex; if (er[i]) onSel(er[i].accession) }} />
}

function Window({ t, r }: { t: string; r: EarningsRow }) {
  const { data } = useApi<[string, number][]>(r.react_date ? `c/${t}/window?date=${r.react_date}&before=15&after=25` : null)
  const option = useMemo(() => {
    if (!data || !r.base_close) return null
    return {
      ...base, grid: { left: 44, right: 12, top: 12, bottom: 24 },
      tooltip: { ...base.tooltip, valueFormatter: (v: number) => (v > 0 ? '+' : '') + v.toFixed(1) + '%' },
      xAxis: { type: 'category', data: data.map((d) => d[0].slice(5)), ...axis },
      yAxis: { type: 'value', ...axis, scale: true, axisLabel: { ...axis.axisLabel, formatter: '{value}%' } },
      series: [{ type: 'line', data: data.map((d) => +((d[1] / r.base_close! - 1) * 100).toFixed(2)), showSymbol: false, color: C.gold,
        areaStyle: { color: 'rgba(212,175,55,.08)' }, name: 'vs base close',
        markLine: { silent: true, symbol: 'none', data: [{ xAxis: r.react_date!.slice(5) }, { yAxis: 0 }], lineStyle: { color: C.text3, type: 'dashed' }, label: { show: false } } }],
    }
  }, [data, r])
  return option ? <EChart option={option} height={170} /> : null
}

function Detail({ t, r }: { t: string; r: EarningsRow }) {
  const nav = useNavigate()
  return (
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)' }}>
      <Panel title={r.kind === 'earnings' ? `${r.fp} ${r.fy} results · quarter to ${date(r.period_end)}` : `Operational update · ${date(r.filed)}`}
        right={<a onClick={() => nav(`/c/${t}/filings/${r.accession}`)}>open release →</a>} flush>
        <StatGrid cols={4}>
          <Stat label="Released" value={<span style={{ fontSize: 13 }}>{date(r.filed)}</span>} sub={`${r.accepted_et?.slice(11, 16) ?? ''} ET · ${TIMING[r.timing ?? ''] ?? '?'}`} />
          <Stat label="Gap at open" value={<Delta v={r.gap} />} sub={`from ${date(r.base_date)} close`} />
          <Stat label="Reaction day" value={<Delta v={r.day} />} sub={<>vs SPY <Delta v={r.excess_day} /></>} />
          <Stat label="+5 / +20 days" value={<Delta v={r.d5} />} sub={<>20d <Delta v={r.d20} /> · vol {r.vol_ratio?.toFixed(1)}×</>} />
        </StatGrid>
        <div className="body"><Window t={t} r={r} /></div>
        {r.metrics && (
          <table className="t">
            <thead><tr><th>Quarter</th><th className="n">This quarter</th><th className="n">Year ago</th><th className="n">YoY</th><th className="n">QoQ</th></tr></thead>
            <tbody>{LINES.map(([k, l, kind]) => {
              const c = r.metrics![k]
              if (!c) return null
              const marginDelta = kind === 'pct' && c.v !== null && c.yago !== null && c.yago !== undefined ? (c.v! - c.yago) : null
              return (
                <tr key={k}><td>{l}</td><td className="n">{fmt(c.v, kind)}</td><td className="n dim">{fmt(c.yago, kind)}</td>
                  <td className="n">{kind === 'pct' ? (marginDelta === null ? '—' : <span className={marginDelta >= 0 ? 'up' : 'down'}>{marginDelta >= 0 ? '+' : ''}{(marginDelta * 100).toFixed(1)} pp</span>) : <Delta v={c.yoy} />}</td>
                  <td className="n">{kind === 'pct' ? '' : <Delta v={c.qoq} />}</td></tr>
              )
            })}</tbody>
          </table>
        )}
      </Panel>
      <Panel title="What they said about what's next" right={<span className="dimmer">forward-looking sentences from the release</span>}>
        {r.guidance.length ? (
          <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 10, lineHeight: 1.55 }}>
            {r.guidance.map((g, i) => <li key={i} className="dim" dangerouslySetInnerHTML={{ __html: highlight(g) }} />)}
          </ul>
        ) : <div className="dimmer">No release text archived for this filing{r.kind === 'update' ? '' : ' (lite/core tickers keep only the filing index)'}.</div>}
        <div className="dimmer" style={{ fontSize: 11, marginTop: 14 }}>Company statements, not facts — and not a consensus estimate. The reaction is the market's verdict versus what it expected.</div>
      </Panel>
    </div>
  )
}

function highlight(s: string) {
  const esc = s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
  return esc.replace(/\b(expect\w*|anticipat\w*|plan\w*|guidance|outlook|target\w*|forecast\w*|on track|raise[sd]?|lower\w*|reaffirm\w*)\b/gi, '<mark>$1</mark>')
}

export default function Earnings({ t }: { t: string }) {
  const { data, error } = useApi<EarningsT>(`c/${t}/earnings`)
  const [showUpdates, setShowUpdates] = useState(false)
  const [sel, setSel] = useState<string | null>(null)
  if (error) return <div className="err">{error}</div>
  if (!data) return <Loading what="earnings" />
  if (!data.rows.length) return <Empty>No results releases (8-K item 2.02) found for {t}.</Empty>
  const rows = data.rows.filter((r) => showUpdates || r.kind === 'earnings')
  const cur = data.rows.find((r) => r.accession === sel) ?? rows[0]
  const s = data.stats
  return (
    <div className="grid">
      <PageTitle title="Earnings" sub="Every results release with the market's reaction — the free stand-in for 'beat or miss' · base = last close before the news"
        right={<Chip on={showUpdates} onClick={() => setShowUpdates(!showUpdates)} count={data.rows.length - s.n}>operational updates</Chip>} />
      <Panel flush>
        <StatGrid cols={6}>
          <Stat label="Releases" value={s.n} sub={`${s.up} up · ${s.down} down`} />
          <Stat label="Typical move (|day|)" value={pct(s.avg_abs_day, 1, false)} sub={`last 8: ${pct(s.avg_abs_day_8q, 1, false)}`} tone="gold" />
          <Stat label="Average day" value={<Delta v={s.avg_day} />} sub={<>vs SPY <Delta v={s.avg_excess_day} /></>} />
          <Stat label="Average +5d" value={<Delta v={s.avg_d5} />} />
          <Stat label="Follow-through" value={pct(s.follow_through, 0, false)} sub="day-1 direction held at +5d" />
          <Stat label="Biggest" value={<><Delta v={s.biggest_up?.day} /> / <Delta v={s.biggest_down?.day} /></>} sub={`${s.biggest_up?.fp} ${s.biggest_up?.fy} · ${s.biggest_down?.fp} ${s.biggest_down?.fy}`} />
        </StatGrid>
      </Panel>
      <Panel title="Reaction by release" right={<span className="dimmer">click a bar</span>}><ReactionChart rows={rows} sel={cur?.accession ?? null} onSel={setSel} /></Panel>
      {cur && <Detail t={t} r={cur} />}
      <Panel title="All releases" flush>
        <div style={{ maxHeight: 520, overflow: 'auto' }}>
          <table className="t">
            <thead><tr><th>Quarter</th><th>Released</th><th>When</th><th className="n">Revenue</th><th className="n">YoY</th><th className="n">Op. margin</th><th className="n">Gap</th><th className="n">Day</th><th></th><th className="n">+5d</th><th className="n">vs SPY</th><th className="n">Vol</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.accession} className={'click' + (cur?.accession === r.accession ? ' sel' : '')} onClick={() => setSel(r.accession)}>
                <td>{r.kind === 'earnings' ? <b>{r.fp} {r.fy}</b> : <Tag>update</Tag>}</td>
                <td className="mono dim">{r.filed}</td><td className="dim">{TIMING[r.timing ?? ''] ?? '—'}</td>
                <td className="n">{money(r.metrics?.revenue?.v)}</td><td className="n"><Delta v={r.metrics?.revenue?.yoy} /></td>
                <td className="n">{pct(r.metrics?.operating_income_margin?.v, 1, false)}</td>
                <td className="n"><Delta v={r.gap} /></td><td className="n"><Delta v={r.day} /></td><td><Bar v={r.day} max={0.15} /></td>
                <td className="n"><Delta v={r.d5} /></td><td className="n"><Delta v={r.excess_day} /></td>
                <td className="n dim">{r.vol_ratio ? r.vol_ratio.toFixed(1) + '×' : '—'}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}
