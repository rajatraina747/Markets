import { useMemo, useState } from 'react'
import type { Statements } from '../api'
import { useApi, useLocal } from '../hooks'
import { EChart, base, axis, C } from '../components/EChart'
import { cellValue, compact, money, pct } from '../format'

const STMTS: [string, string][] = [['IS', 'Income statement'], ['BS', 'Balance sheet'], ['CF', 'Cash flow']]

function Spark({ vals }: { vals: (number | null)[] }) {
  const v = vals.filter((x): x is number => x !== null)
  if (v.length < 2) return null
  const min = Math.min(...v, 0), max = Math.max(...v, 0)
  const w = 70, h = 18
  const pts = vals.map((x, i) => (x === null ? null : [i / (vals.length - 1) * w, h - ((x - min) / (max - min || 1)) * h] as const))
  const d = pts.filter(Boolean).map((p, i) => `${i ? 'L' : 'M'}${p![0].toFixed(1)},${p![1].toFixed(1)}`).join('')
  const zero = h - ((0 - min) / (max - min || 1)) * h
  const lastUp = v[v.length - 1] >= v[0]
  return (
    <svg className="spark" width={w} height={h}>
      <line x1="0" x2={w} y1={zero} y2={zero} stroke="#222834" />
      <path d={d} fill="none" stroke={lastUp ? C.gold : C.down} strokeWidth="1.4" />
    </svg>
  )
}

function LineChart({ st, line }: { st: Statements; line: string }) {
  const meta = st.lines.find((l) => l.key === line)!
  const option = useMemo(() => {
    const periods = [...st.periods].reverse()
    const vals = periods.map((p) => st.cells[line]?.[p.end]?.v ?? null)
    const lag = st.period === 'quarterly' ? 4 : 1
    const growth = vals.map((v, i) => (i >= lag && v !== null && vals[i - lag] ? +((v / Math.abs(vals[i - lag]!) - Math.sign(vals[i - lag]!)) * 100).toFixed(1) : null))
    const isMoney = meta.unit === 'USD'
    return {
      ...base,
      grid: { left: 64, right: 52, top: 30, bottom: 50 },
      legend: { top: 0, right: 0, textStyle: { color: C.text2, fontSize: 11 } },
      tooltip: { ...base.tooltip, valueFormatter: (v: number) => (v === null ? '—' : typeof v === 'number' && Math.abs(v) >= 1000 ? (isMoney ? money(v) : compact(v)) : String(v)) },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 6, borderColor: C.line, fillerColor: 'rgba(212,175,55,.12)', handleStyle: { color: C.gold }, textStyle: { color: C.text3 } }],
      xAxis: { type: 'category', data: periods.map((p) => (st.period === 'quarterly' ? `${p.fp} ${p.fy}` : `FY${p.fy}`)), ...axis },
      yAxis: [
        { type: 'value', ...axis, axisLabel: { ...axis.axisLabel, formatter: (v: number) => (meta.unit === 'USD/shares' ? v.toFixed(2) : compact(v, 0)) } },
        { type: 'value', ...axis, splitLine: { show: false }, axisLabel: { ...axis.axisLabel, formatter: '{value}%' } },
      ],
      series: [
        { name: meta.label, type: 'bar', data: vals, barMaxWidth: 22, color: C.gold, itemStyle: { color: (p: { value: number }) => (p.value < 0 ? C.down : 'rgba(212,175,55,.8)'), borderRadius: [3, 3, 0, 0] } },
        { name: st.period === 'quarterly' ? 'YoY growth' : 'Growth', type: 'line', yAxisIndex: 1, data: growth, symbol: 'circle', symbolSize: 4, lineStyle: { color: C.blue, width: 1.5 }, itemStyle: { color: C.blue }, connectNulls: true },
      ],
    }
  }, [st, line, meta])
  return <EChart option={option} height={300} />
}

export default function Financials({ t }: { t: string }) {
  const [period, setPeriod] = useLocal<'annual' | 'quarterly'>('fin-period', 'annual')
  const [stmt, setStmt] = useLocal<string>('fin-stmt', 'IS')
  const [sel, setSel] = useState('revenue')
  const { data: st, error } = useApi<Statements>(`c/${t}/statements?period=${period}`)

  const rows = useMemo(() => st?.lines.filter((l) => stmt === 'ALL' || l.statement === stmt) ?? [], [st, stmt])
  if (error) return <div className="err">{error}</div>
  const selLine = st?.lines.find((l) => l.key === sel) ? sel : rows[0]?.key

  return (
    <div className="grid">
      <div className="page-title">
        <h1>Financials</h1>
        <span className="sub">From SEC XBRL · USD millions unless noted · latest filing wins on restatements{st?.split_adjusted ? ' · per-share & share counts split-adjusted' : ''}</span>
      </div>
      <div className="filters">
        <div className="seg">
          {(['annual', 'quarterly'] as const).map((p) => <button key={p} className={period === p ? 'on' : ''} onClick={() => setPeriod(p)}>{p}</button>)}
        </div>
        <div className="seg">
          {[...STMTS, ['ALL', 'All']].map(([k, l]) => <button key={k} className={stmt === k ? 'on' : ''} onClick={() => setStmt(k)}>{l}</button>)}
        </div>
        <span className="dimmer" style={{ marginLeft: 'auto', fontSize: 12 }}><i>Italic</i> = derived (e.g. Q4 = FY − 9M) · hover a cell for its source tag</span>
      </div>
      {!st ? <div className="loading">loading statements</div> : (
        <>
          {selLine && (
            <section className="panel">
              <header>{st.lines.find((l) => l.key === selLine)?.label}<span className="grow" /><span className="dimmer" style={{ textTransform: 'none', letterSpacing: 0 }}>click any row to chart it · scroll to zoom</span></header>
              <div className="body"><LineChart st={st} line={selLine} /></div>
            </section>
          )}
          <section className="panel">
            <div className="fin-wrap">
              <table className="t fin">
                <thead>
                  <tr>
                    <th>{period === 'annual' ? 'Fiscal year' : 'Quarter'}</th>
                    {st.periods.map((p) => <th key={p.end} className="n">{period === 'annual' ? `FY${p.fy}` : `${p.fp} ${p.fy}`}<div className="dimmer" style={{ fontWeight: 400, letterSpacing: 0 }}>{p.end}</div></th>)}
                  </tr>
                </thead>
                <tbody>
                  {STMTS.filter(([k]) => stmt === 'ALL' || stmt === k).map(([k, label]) => (
                    <FinSection key={k} st={st} label={stmt === 'ALL' ? label : null} rows={rows.filter((r) => r.statement === k)} sel={selLine} onSel={setSel} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <Ratios st={st} />
        </>
      )}
    </div>
  )
}

function FinSection({ st, label, rows, sel, onSel }: {
  st: Statements; label: string | null; rows: Statements['lines']; sel?: string; onSel: (k: string) => void
}) {
  return (
    <>
      {label && <tr className="section"><td colSpan={st.periods.length + 1}>{label}</td></tr>}
      {rows.map((l) => {
        const cells = st.cells[l.key] ?? {}
        const spark = [...st.periods].reverse().slice(-12).map((p) => cells[p.end]?.v ?? null)
        return (
          <tr key={l.key} className={'click' + (sel === l.key ? ' sel' : '')} onClick={() => onSel(l.key)}>
            <td>{l.label}{l.unit !== 'USD' ? <span className="dimmer" style={{ fontSize: 11 }}> {l.unit === 'shares' ? '(shares)' : '($)'}</span> : null}<Spark vals={spark} /></td>
            {st.periods.map((p) => {
              const c = cells[p.end]
              return (
                <td key={p.end} className={'n' + (c?.derived ? ' derived' : '') + (c && c.v < 0 ? ' neg' : '')}
                  title={c ? `${c.concept}${c.derived ? ' (derived)' : ''}\n${c.acc ?? ''}` : 'not reported'}>
                  {c ? cellValue(c.v, l.unit) : <span className="dimmer">·</span>}
                </td>
              )
            })}
          </tr>
        )
      })}
    </>
  )
}

function Ratios({ st }: { st: Statements }) {
  const g = (k: string, e: string) => st.cells[k]?.[e]?.v ?? null
  const ratio = (a: number | null, b: number | null) => (a !== null && b ? a / b : null)
  const defs: [string, (e: string) => number | null][] = [
    ['Gross margin', (e) => ratio(g('gross_profit', e), g('revenue', e))],
    ['Operating margin', (e) => ratio(g('operating_income', e), g('revenue', e))],
    ['Net margin', (e) => ratio(g('net_income', e), g('revenue', e))],
    ['FCF margin', (e) => ratio(g('free_cash_flow', e), g('revenue', e))],
    ['R&D / revenue', (e) => ratio(g('rnd', e), g('revenue', e))],
    ['Capex / revenue', (e) => ratio(g('capex', e), g('revenue', e))],
    ['SBC / revenue', (e) => ratio(g('sbc', e), g('revenue', e))],
    ['Effective tax rate', (e) => ratio(g('income_tax', e), g('pretax_income', e))],
    ['Current ratio', (e) => ratio(g('current_assets', e), g('current_liabilities', e))],
    ['Debt / equity', (e) => ratio((g('debt_current', e) ?? 0) + (g('long_term_debt', e) ?? 0), g('equity', e))],
    ['Return on equity', (e) => (st.period === 'annual' ? ratio(g('net_income', e), g('equity', e)) : null)],
  ]
  return (
    <section className="panel">
      <header>Ratios</header>
      <div className="fin-wrap">
        <table className="t fin">
          <thead><tr><th>Ratio</th>{st.periods.map((p) => <th key={p.end} className="n">{st.period === 'annual' ? `FY${p.fy}` : `${p.fp} ${p.fy}`}</th>)}</tr></thead>
          <tbody>
            {defs.map(([label, fn]) => (
              <tr key={label}>
                <td>{label}</td>
                {st.periods.map((p) => {
                  const v = fn(p.end)
                  const isX = label === 'Current ratio' || label === 'Debt / equity'
                  return <td key={p.end} className={'n' + (v !== null && v < 0 ? ' neg' : '')}>{v === null ? <span className="dimmer">·</span> : isX ? v.toFixed(2) : pct(v, 1, false)}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
