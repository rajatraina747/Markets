import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { WatchRow } from '../api'
import { useApi, useLocal } from '../hooks'
import { money, mult, pct, tone } from '../format'

type Field = { key: string; label: string; get: (r: WatchRow) => number | null | undefined; kind: 'pct' | 'x' | 'usd' }
const FIELDS: Field[] = [
  { key: 'growth', label: 'Revenue growth', get: (r) => r.revenue_growth, kind: 'pct' },
  { key: 'gm', label: 'Gross margin', get: (r) => r.margins.gross, kind: 'pct' },
  { key: 'om', label: 'Operating margin', get: (r) => r.margins.operating, kind: 'pct' },
  { key: 'nm', label: 'Net margin', get: (r) => r.margins.net, kind: 'pct' },
  { key: 'fcfm', label: 'FCF margin', get: (r) => r.margins.fcf, kind: 'pct' },
  { key: 'pe', label: 'P/E', get: (r) => r.valuation.pe, kind: 'x' },
  { key: 'ps', label: 'P/S', get: (r) => r.valuation.ps, kind: 'x' },
  { key: 'mcap', label: 'Market cap ($B)', get: (r) => (r.market_cap ? r.market_cap / 1e9 : null), kind: 'usd' },
  { key: '1y', label: '1-year return', get: (r) => r.returns['1y'], kind: 'pct' },
  { key: 'off_high', label: '% below 52w high', get: (r) => (r.price && r.high_52w ? r.price / r.high_52w - 1 : null), kind: 'pct' },
]
type Rule = { key: string; op: '>' | '<'; v: string }

const PRESETS: { label: string; rules: Rule[] }[] = [
  { label: 'Profitable growers', rules: [{ key: 'growth', op: '>', v: '10' }, { key: 'om', op: '>', v: '0' }] },
  { label: 'Cash burners', rules: [{ key: 'fcfm', op: '<', v: '0' }] },
  { label: 'Cheap on sales', rules: [{ key: 'ps', op: '<', v: '1' }] },
  { label: 'Beaten down', rules: [{ key: 'off_high', op: '<', v: '-30' }] },
]

const fmtField = (f: Field, v: number | null | undefined) => (f.kind === 'pct' ? pct(v, 1) : f.kind === 'x' ? mult(v) : v === null || v === undefined ? '—' : money(v * 1e9))

export default function Screener() {
  const nav = useNavigate()
  const { data, error } = useApi<WatchRow[]>('watchlist')
  const [rules, setRules] = useLocal<Rule[]>('screener-rules', [{ key: 'om', op: '>', v: '0' }])
  const [sector, setSector] = useState('')
  const [onlyPass, setOnlyPass] = useState(true)
  const sectors = useMemo(() => [...new Set((data ?? []).map((r) => r.sector).filter(Boolean) as string[])].sort(), [data])
  const pass = useMemo(() => (data ?? []).filter((r) => !sector || r.sector === sector).map((r) => {
    const checks = rules.map((ru) => {
      const f = FIELDS.find((x) => x.key === ru.key)!
      const val = f.get(r)
      const thr = f.kind === 'pct' ? +ru.v / 100 : +ru.v
      return val !== null && val !== undefined && ru.v !== '' && (ru.op === '>' ? val > thr : val < thr)
    })
    return { r, ok: checks.every(Boolean), score: checks.filter(Boolean).length }
  }).sort((a, b) => b.score - a.score || (b.r.market_cap ?? 0) - (a.r.market_cap ?? 0)), [data, rules, sector])
  if (error) return <div className="err">{error}</div>
  const upd = (i: number, patch: Partial<Rule>) => setRules(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  return (
    <div className="grid">
      <div className="page-title"><h1>Screener</h1><span className="sub">Filters run over every tracked company in the local database · percentages in % · add more companies with <code>./markets add TICKER --lite</code></span></div>
      <section className="panel">
        <header>Rules<span className="grow" />{PRESETS.map((p) => <span key={p.label} className="chip" style={{ textTransform: 'none', letterSpacing: 0 }} onClick={() => setRules(p.rules)}>{p.label}</span>)}</header>
        <div className="body" style={{ display: 'grid', gap: 8 }}>
          {rules.map((ru, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <select className="input" value={ru.key} onChange={(e) => upd(i, { key: e.target.value })}>{FIELDS.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}</select>
              <div className="seg"><button className={ru.op === '>' ? 'on' : ''} onClick={() => upd(i, { op: '>' })}>&gt;</button><button className={ru.op === '<' ? 'on' : ''} onClick={() => upd(i, { op: '<' })}>&lt;</button></div>
              <input className="input mono" style={{ width: 110 }} value={ru.v} onChange={(e) => upd(i, { v: e.target.value })} inputMode="decimal" />
              <span className="dimmer">{FIELDS.find((f) => f.key === ru.key)?.kind === 'pct' ? '%' : FIELDS.find((f) => f.key === ru.key)?.kind === 'x' ? '×' : '$B'}</span>
              <button className="chip" onClick={() => setRules(rules.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
          <div><button className="chip" onClick={() => setRules([...rules, { key: 'gm', op: '>', v: '20' }])}>+ rule</button></div>
        </div>
      </section>
      <section className="panel">
        <header>Results · {pass.filter((p) => p.ok).length} of {pass.length} pass<span className="grow" />
          <span style={{ display: 'flex', gap: 8, textTransform: 'none', letterSpacing: 0 }}>
            <select className="input" value={sector} onChange={(e) => setSector(e.target.value)}><option value="">All sectors</option>{sectors.map((x) => <option key={x}>{x}</option>)}</select>
            <span className={'chip' + (onlyPass ? ' on' : '')} onClick={() => setOnlyPass(!onlyPass)}>passing only</span>
          </span>
        </header>
        <table className="t">
          <thead><tr><th></th><th>Ticker</th><th>Name</th><th>Sector</th>{FIELDS.map((f) => <th key={f.key} className="n" style={rules.some((r) => r.key === f.key) ? { color: 'var(--gold)' } : undefined}>{f.label}</th>)}</tr></thead>
          <tbody>
            {pass.filter((p) => !onlyPass || p.ok).slice(0, 300).map(({ r, ok, score }) => (
              <tr key={r.ticker} className="click" style={{ opacity: ok ? 1 : 0.45 }} onClick={() => nav(`/c/${r.ticker}/overview`)}>
                <td>{ok ? <span className="up">●</span> : <span className="dimmer">{score}/{rules.length}</span>}</td>
                <td className="mono gold" style={{ fontWeight: 700 }}>{r.ticker}</td>
                <td className="dim" style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</td>
                <td className="dimmer" style={{ fontSize: 12 }}>{r.sector}</td>
                {FIELDS.map((f) => { const v = f.get(r); return <td key={f.key} className={'n ' + (f.kind === 'pct' ? tone(v) : '')}>{fmtField(f, v)}</td> })}
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
