import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Comp, Insider, InsiderTxn, ProxyComp } from '../api'
import { useApi } from '../hooks'
import { EChart, base, axis, C } from '../components/EChart'
import { compact, date, money, price } from '../format'

const CODE: Record<string, string> = {
  P: 'Buy', S: 'Sale', A: 'Award', M: 'Exercise', F: 'Tax w/h', G: 'Gift', C: 'Convert', D: 'To issuer',
  X: 'Exercise', J: 'Other', W: 'Inherit', I: 'Discretionary',
}

function roleBadges(p: Insider) {
  return (
    <span className="badges">
      {p.is_officer ? <span className="tag k10">Officer</span> : null}
      {p.is_director ? <span className="tag q10">Director</span> : null}
      {p.is_ten_pct ? <span className="tag px">10% owner</span> : null}
    </span>
  )
}

function ActivityChart({ txns }: { txns: InsiderTxn[] }) {
  const option = useMemo(() => {
    const m = new Map<string, { buy: number; sell: number }>()
    for (const t of txns) {
      if (!t.txn_date || !t.shares || !t.price || (t.code !== 'P' && t.code !== 'S')) continue
      const k = t.txn_date.slice(0, 7)
      const r = m.get(k) ?? { buy: 0, sell: 0 }
      if (t.code === 'P') r.buy += t.shares * t.price; else r.sell -= t.shares * t.price
      m.set(k, r)
    }
    const keys = [...m.keys()].sort()
    if (!keys.length) return null
    // fill months
    const all: string[] = []
    let [y, mo] = keys[0].split('-').map(Number)
    const [ey, em] = keys[keys.length - 1].split('-').map(Number)
    while (y < ey || (y === ey && mo <= em)) { all.push(`${y}-${String(mo).padStart(2, '0')}`); mo++; if (mo > 12) { mo = 1; y++ } }
    return {
      ...base, grid: { left: 64, right: 16, top: 24, bottom: 46 },
      legend: { top: 0, right: 0, textStyle: { color: C.text2, fontSize: 11 } },
      tooltip: { ...base.tooltip, axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => money(v) },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 14, bottom: 6, borderColor: C.line, fillerColor: 'rgba(212,175,55,.12)', textStyle: { color: C.text3 } }],
      xAxis: { type: 'category', data: all, ...axis },
      yAxis: { type: 'value', ...axis, axisLabel: { ...axis.axisLabel, formatter: (v: number) => compact(v, 0) } },
      series: [
        { name: 'Open-market buys', type: 'bar', stack: 'x', data: all.map((k) => m.get(k)?.buy || null), itemStyle: { color: C.up } },
        { name: 'Open-market sales', type: 'bar', stack: 'x', data: all.map((k) => m.get(k)?.sell || null), itemStyle: { color: C.down } },
      ],
    }
  }, [txns])
  return option ? <EChart option={option} height={230} /> : <div className="empty">No open-market trades in the archive yet.</div>
}

function HoldingChart({ txns }: { txns: InsiderTxn[] }) {
  const option = useMemo(() => {
    const pts = txns.filter((t) => t.table_kind === 'nonDerivative' && t.shares_after_adj !== null && t.txn_date && t.ownership === 'D')
      .map((t) => [t.txn_date!, t.shares_after_adj!] as [string, number]).sort((a, b) => (a[0] < b[0] ? -1 : 1))
    if (pts.length < 2) return null
    return {
      ...base, grid: { left: 64, right: 16, top: 16, bottom: 26 },
      tooltip: { ...base.tooltip, valueFormatter: (v: number) => compact(v) + ' sh' },
      xAxis: { type: 'time', ...axis }, yAxis: { type: 'value', ...axis, axisLabel: { ...axis.axisLabel, formatter: (v: number) => compact(v, 0) } },
      series: [{ type: 'line', step: 'end', data: pts, symbol: 'none', lineStyle: { color: C.gold, width: 2 }, areaStyle: { color: 'rgba(212,175,55,.12)' }, name: 'Direct holding (split-adj.)' }],
    }
  }, [txns])
  return option ? <EChart option={option} height={170} /> : null
}

function ProxyTables({ px }: { px: ProxyComp }) {
  const years = [...new Set(px.sct.map((r) => r.fy))].sort((a, b) => b - a)
  const [fy, setFy] = useState(years[0])
  const dirYears = [...new Set(px.directors.map((r) => r.proxy_year))].sort((a, b) => b - a)
  const [dy, setDy] = useState(dirYears[0])
  const rows = px.sct.filter((r) => r.fy === fy)
  const cols: [keyof typeof rows[0], string][] = [['salary', 'Salary'], ['bonus', 'Bonus'], ['stock', 'Stock awards'], ['option', 'Option awards'], ['non_equity', 'Non-equity'], ['other', 'All other'], ['total', 'Total']]
  return (
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1.5fr) minmax(0, 1fr)' }}>
      <section className="panel">
        <header>Summary compensation table<span className="grow" />
          <select className="input" style={{ textTransform: 'none' }} value={fy} onChange={(e) => setFy(+e.target.value)}>{years.map((y) => <option key={y} value={y}>FY{y}</option>)}</select>
        </header>
        <div style={{ overflow: 'auto' }}>
          <table className="t">
            <thead><tr><th>Executive</th>{cols.map(([k, l]) => <th key={k} className="n">{l}</th>)}</tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.name}><td style={{ whiteSpace: 'normal' }}><div style={{ fontWeight: 550 }}>{r.name}</div><div className="dimmer" style={{ fontSize: 11 }}>{r.position}</div></td>
                {cols.map(([k]) => <td key={k} className={'n' + (k === 'total' ? ' gold' : '')} style={k === 'total' ? { fontWeight: 600 } : undefined}>{r[k] ? money(r[k] as number) : <span className="dimmer">—</span>}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
        <div className="dimmer" style={{ padding: '8px 14px', fontSize: 11 }}>From the DEF 14A proxy (grant-date values — not what was realized). Parsed from HTML; every row's components were checked to sum to its total.</div>
      </section>
      {px.directors.length > 0 && (
        <section className="panel">
          <header>Director compensation<span className="grow" />
            <select className="input" style={{ textTransform: 'none' }} value={dy} onChange={(e) => setDy(+e.target.value)}>{dirYears.map((y) => <option key={y} value={y}>FY{y}</option>)}</select>
          </header>
          <table className="t">
            <thead><tr><th>Director</th><th className="n">Fees</th><th className="n">Awards</th><th className="n">Total</th></tr></thead>
            <tbody>{px.directors.filter((r) => r.proxy_year === dy).map((r) => (
              <tr key={r.name}><td>{r.name}</td><td className="n">{money(r.fees)}</td><td className="n">{money((r.stock ?? 0) + (r.option ?? 0))}</td><td className="n gold">{money(r.total)}</td></tr>
            ))}</tbody>
          </table>
        </section>
      )}
    </div>
  )
}

export default function People({ t }: { t: string }) {
  const nav = useNavigate()
  const { data: people, error } = useApi<Insider[]>(`c/${t}/insiders`)
  const { data: market } = useApi<InsiderTxn[]>(`c/${t}/insiders/txns?codes=P,S&limit=5000`)
  const [sel, setSel] = useState<number | null>(null)
  const [filter, setFilter] = useState<'all' | 'officer' | 'director' | 'current'>('all')
  const { data: txns } = useApi<InsiderTxn[]>(sel ? `c/${t}/insiders/txns?person=${sel}&limit=5000` : null)
  const list = useMemo(() => {
    const yearAgo = new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10)
    return (people ?? []).filter((p) => filter === 'all' || (filter === 'officer' && p.is_officer) || (filter === 'director' && p.is_director) || (filter === 'current' && p.last_seen >= yearAgo))
  }, [people, filter])
  const person = people?.find((p) => p.id === sel)
  const { data: comp } = useApi<Comp>(`c/${t}/comp`)
  const { data: px } = useApi<ProxyComp>(`c/${t}/proxy`)

  if (error) return <div className="err">{error}</div>
  return (
    <div className="grid">
      <div className="page-title"><h1>People &amp; insiders</h1><span className="sub">From every Form 3/4/5 in the archive · share counts split-adjusted · roles as self-reported to the SEC</span></div>
      <section className="panel">
        <header>Insider open-market activity (all insiders, monthly $)</header>
        <div className="body">{market ? <ActivityChart txns={market} /> : <div className="loading">loading</div>}</div>
      </section>
      {comp && comp.years.length > 0 && (
        <section className="panel">
          <header>Pay versus performance<span className="grow" /><span className="dimmer" style={{ textTransform: 'none', letterSpacing: 0 }}>proxy-statement XBRL (Item 402(v)) · “actually paid” marks equity awards to market</span></header>
          <table className="t">
            <thead><tr><th>Measure</th>{comp.years.map((y) => <th key={y} className="n">FY{y}</th>)}</tr></thead>
            <tbody>
              {comp.lines.map((l) => (
                <tr key={l.concept}>
                  <td>{l.label}</td>
                  {comp.years.map((y) => {
                    const v = l.values[String(y)]
                    const isTsr = l.concept.includes('ShareholderRtn')
                    return <td key={y} className={'n' + (v < 0 ? ' down' : '')}>{v === undefined ? <span className="dimmer">·</span> : isTsr ? '$' + v.toFixed(0) : money(v)}</td>
                  })}
                </tr>
              ))}
              <tr><td className="dimmer">Net income (10-K)</td>{comp.years.map((y) => <td key={y} className="n dim">{money(comp.net_income[String(y)])}</td>)}</tr>
            </tbody>
          </table>
        </section>
      )}
      {px && px.sct.length > 0 && <ProxyTables px={px} />}
      <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.25fr)' }}>
        <section className="panel">
          <header>
            Insiders ({list.length})<span className="grow" />
            <div className="seg" style={{ textTransform: 'none' }}>
              {(['all', 'current', 'officer', 'director'] as const).map((f) => <button key={f} className={filter === f ? 'on' : ''} onClick={() => setFilter(f)}>{f}</button>)}
            </div>
          </header>
          <div style={{ maxHeight: 620, overflow: 'auto' }}>
            <table className="t">
              <thead><tr><th>Name</th><th>Active</th><th className="n">Net open-mkt</th></tr></thead>
              <tbody>
                {!people ? <tr><td colSpan={3} className="loading">loading</td></tr> : list.map((p) => (
                  <tr key={p.id} className={'click' + (sel === p.id ? ' sel' : '')} onClick={() => setSel(p.id)}>
                    <td style={{ whiteSpace: 'normal' }}>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}><span style={{ fontWeight: 550 }}>{p.name}</span>{roleBadges(p)}</div>
                      <div className="dimmer" style={{ fontSize: 11 }}>{p.titles.join(' · ')}</div>
                    </td>
                    <td className="mono dim" style={{ fontSize: 11 }}>{p.first_seen.slice(0, 7)} → {p.last_seen.slice(0, 7)}</td>
                    <td className={'n ' + ((p.net_open_market_usd ?? 0) > 0 ? 'up' : (p.net_open_market_usd ?? 0) < 0 ? 'down' : 'dimmer')}>{p.net_open_market_usd ? money(p.net_open_market_usd) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="panel">
          {!person ? <div className="empty">Select a person to see every transaction they reported.</div> : (
            <>
              <header style={{ textTransform: 'none', letterSpacing: 0 }}>
                <span style={{ fontSize: 14, color: 'var(--text)', fontWeight: 600 }}>{person.name}</span>{roleBadges(person)}
                <span className="grow" />
                {person.cik ? <a href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${person.cik}&type=4`} target="_blank" rel="noreferrer" className="mono">CIK {person.cik} ↗</a> : null}
              </header>
              <div className="stats" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
                <div className="stat"><div className="l">Reported txns</div><div className="v">{person.txns ?? 0}</div></div>
                <div className="stat"><div className="l">Last direct holding</div><div className="v">{compact(person.last_holding)}</div><div className="s">{date(person.last_holding_date)}</div></div>
                <div className="stat"><div className="l">Net open-market</div><div className={'v ' + ((person.net_open_market_usd ?? 0) >= 0 ? 'up' : 'down')}>{money(person.net_open_market_usd)}</div></div>
                <div className="stat"><div className="l">Last 12 months</div><div className={'v ' + ((person.net_open_market_usd_1y ?? 0) >= 0 ? 'up' : 'down')}>{money(person.net_open_market_usd_1y)}</div></div>
              </div>
              {txns && <div className="body"><HoldingChart txns={txns} /></div>}
              <div style={{ maxHeight: 420, overflow: 'auto' }}>
                <table className="t">
                  <thead><tr><th>Date</th><th>Type</th><th>Security</th><th className="n">Shares*</th><th className="n">Price*</th><th className="n">After*</th><th></th></tr></thead>
                  <tbody>
                    {txns?.map((x) => (
                      <tr key={x.accession + x.row} className="click" onClick={() => nav(`/c/${t}/filings/${x.accession}`)}>
                        <td className="mono dim">{x.txn_date}</td>
                        <td><span className={'tag ' + (x.code === 'P' ? 'f4' : x.code === 'S' ? 'px' : '')}>{x.code ? `${x.code} · ${CODE[x.code] ?? x.code}` : x.table_kind}</span>{x.is_10b5_1 ? <span className="dimmer" style={{ fontSize: 10 }}> 10b5-1</span> : null}</td>
                        <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }} title={x.security ?? ''}>{x.security}{x.ownership === 'I' ? <span className="dimmer"> (indirect)</span> : null}</td>
                        <td className={'n ' + (x.acq_disp === 'D' ? 'down' : x.acq_disp === 'A' ? 'up' : '')}>{x.shares_adj !== null ? (x.acq_disp === 'D' ? '-' : '') + compact(x.shares_adj, 1) : '—'}</td>
                        <td className="n">{x.price_adj ? price(x.price_adj) : '—'}</td>
                        <td className="n dim">{compact(x.shares_after_adj)}</td>
                        <td className="dimmer mono" style={{ fontSize: 10 }}>{x.form}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="dimmer" style={{ padding: '8px 14px', fontSize: 11 }}>* adjusted for stock splits after the transaction date</div>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}
