import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { EventRow, Overview as OverviewT, Prices, Statements } from '../api'
import { useApi, useLocal } from '../hooks'
import { PriceChart, EVENT_KINDS } from '../components/PriceChart'
import { EChart, base, axis, C } from '../components/EChart'
import { compact, date, money, mult, pct, price, tone } from '../format'

function Stat({ l, v, s, cls }: { l: string; v: string; s?: string; cls?: string }) {
  return <div className="stat"><div className="l">{l}</div><div className={'v ' + (cls ?? '')}>{v}</div>{s ? <div className="s">{s}</div> : null}</div>
}

export function EventList({ events, onOpen }: { events: EventRow[]; onOpen: (e: EventRow) => void }) {
  return (
    <div className="evlist">
      {events.map((e, i) => (
        <div key={i} className="ev" style={{ cursor: e.accession ? 'pointer' : 'default' }} onClick={() => e.accession && onOpen(e)}>
          <div className="d">{date(e.date)}</div>
          <div>
            <div className="t"><span className="bar" style={{ background: EVENT_KINDS[e.kind]?.color ?? C.text3 }} />{e.title}</div>
            {e.detail ? <div className="x">{e.detail}</div> : null}
          </div>
        </div>
      ))}
    </div>
  )
}

function Fundamentals({ st }: { st: Statements }) {
  const option = useMemo(() => {
    const periods = [...st.periods].reverse().slice(-20)
    const val = (k: string) => periods.map((p) => st.cells[k]?.[p.end]?.v ?? null)
    const rev = val('revenue'), ni = val('net_income'), gp = val('gross_profit'), op = val('operating_income')
    const margin = (a: (number | null)[]) => a.map((v, i) => (v !== null && rev[i] ? +(v / rev[i]! * 100).toFixed(1) : null))
    return {
      ...base,
      grid: { left: 56, right: 46, top: 34, bottom: 26 },
      legend: { top: 0, right: 0, textStyle: { color: C.text2, fontSize: 11 }, itemWidth: 10, itemHeight: 8 },
      tooltip: { ...base.tooltip, valueFormatter: (v: number) => (typeof v === 'number' && Math.abs(v) > 1000 ? money(v) : v + '%') },
      xAxis: { type: 'category', data: periods.map((p) => `${p.fp} ${String(p.fy).slice(2)}`), ...axis },
      yAxis: [
        { type: 'value', ...axis, axisLabel: { ...axis.axisLabel, formatter: (v: number) => compact(v, 0) } },
        { type: 'value', ...axis, splitLine: { show: false }, axisLabel: { ...axis.axisLabel, formatter: '{value}%' } },
      ],
      series: [
        { name: 'Revenue', type: 'bar', data: rev, color: C.gold, itemStyle: { color: 'rgba(212,175,55,.75)', borderRadius: [3, 3, 0, 0] }, barMaxWidth: 18 },
        { name: 'Net income', type: 'bar', data: ni, color: C.up, itemStyle: { color: (p: { value: number }) => (p.value < 0 ? C.down : C.up), borderRadius: [3, 3, 0, 0] }, barMaxWidth: 18 },
        { name: 'Gross margin', type: 'line', yAxisIndex: 1, data: margin(gp), symbol: 'none', lineStyle: { color: C.blue, width: 2 }, itemStyle: { color: C.blue }, smooth: 0.2 },
        { name: 'Op. margin', type: 'line', yAxisIndex: 1, data: margin(op), symbol: 'none', lineStyle: { color: C.violet, width: 2 }, itemStyle: { color: C.violet }, smooth: 0.2 },
      ],
    }
  }, [st])
  return <EChart option={option} height={260} />
}

function Returns({ r }: { r: Record<string, number | null> }) {
  const keys: [string, string][] = [['1m', '1M'], ['3m', '3M'], ['ytd', 'YTD'], ['1y', '1Y'], ['3y', '3Y'], ['5y', '5Y'], ['since_ipo', 'IPO']]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${keys.length}, 1fr)`, gap: 4, padding: 12 }}>
      {keys.map(([k, l]) => {
        const v = r[k]
        const a = v === null || v === undefined ? 0 : Math.min(Math.abs(v), 1)
        const bg = v === null || v === undefined ? 'var(--bg-2)' : v >= 0 ? `rgba(47,191,113,${0.1 + a * 0.5})` : `rgba(240,82,79,${0.1 + a * 0.5})`
        return (
          <div key={k} style={{ background: bg, borderRadius: 6, padding: '8px 6px', textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: 'var(--text-2)' }}>{l}</div>
            <div className="mono" style={{ fontWeight: 600 }}>{v === null || v === undefined ? '—' : (Math.abs(v) >= 10 ? (v > 0 ? '+' : '') + Math.round(v * 100).toLocaleString() + '%' : pct(v, 0))}</div>
          </div>
        )
      })}
    </div>
  )
}

export default function Overview({ t, ov }: { t: string; ov: OverviewT | null }) {
  const nav = useNavigate()
  const { data: prices } = useApi<Prices>(`c/${t}/prices`)
  const { data: events } = useApi<EventRow[]>(`c/${t}/events`)
  const { data: st } = useApi<Statements>(`c/${t}/statements?period=quarterly`)
  const [kindsArr, setKindsArr] = useLocal<string[]>('chart-kinds', ['earnings', 'split', 'insider'])
  const kinds = useMemo(() => new Set(kindsArr), [kindsArr])
  const [minImp, setMinImp] = useState(2)
  const shown = useMemo(() => (events ?? []).filter((e) => e.importance >= minImp), [events, minImp])
  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const e of shown) c[e.kind] = (c[e.kind] ?? 0) + 1
    return c
  }, [shown])
  const open = useCallback((e: EventRow) => e.accession && nav(`/c/${t}/filings/${e.accession}`), [nav, t])

  if (!ov) return <div className="loading">loading {t}</div>
  const co = ov.company
  const addr = co.business_address ? JSON.parse(co.business_address) : null
  const formerNames: { name: string; from: string; to: string }[] = co.former_names ? JSON.parse(co.former_names) : []

  return (
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1fr) 380px' }}>
      <section className="panel" style={{ gridColumn: '1 / 2' }}>
        <header>
          Price · daily since {date(prices?.rows[0]?.[0])}
          <span className="grow" />
          <div className="legend-row" style={{ textTransform: 'none', letterSpacing: 0 }}>
            {Object.entries(EVENT_KINDS).map(([k, v]) => (
              <span key={k} className={'chip' + (kinds.has(k) ? ' on' : '')}
                onClick={() => setKindsArr(kinds.has(k) ? kindsArr.filter((x) => x !== k) : [...kindsArr, k])}>
                <span className="dot" style={{ background: v.color }} />{v.label}<span className="n">{counts[k] ?? 0}</span>
              </span>
            ))}
            <div className="seg" title="Event importance threshold">
              {[1, 2, 3].map((i) => <button key={i} className={minImp === i ? 'on' : ''} onClick={() => setMinImp(i)}>{'●'.repeat(i)}</button>)}
            </div>
          </div>
        </header>
        {prices ? <PriceChart prices={prices} events={shown} kinds={kinds} onEvent={open} /> : <div className="loading" style={{ height: 520 }}>loading prices</div>}
      </section>

      <div className="grid" style={{ alignContent: 'start' }}>
        <section className="panel">
          <header>Key stats<span className="grow" /><span className="dimmer mono" style={{ textTransform: 'none', letterSpacing: 0 }}>TTM to {date(ov.ttm.period_end)}</span></header>
          <div className="stats">
            <Stat l="Market cap" v={money(ov.market_cap)} s={`${compact(ov.shares_outstanding)} sh`} />
            <Stat l="Enterprise value" v={money(ov.enterprise_value)} />
            <Stat l="P/E" v={mult(ov.valuation.pe)} />
            <Stat l="P/S" v={mult(ov.valuation.ps)} />
            <Stat l="P/FCF" v={mult(ov.valuation.p_fcf)} />
            <Stat l="EV/Sales" v={mult(ov.valuation.ev_sales)} />
            <Stat l="Revenue" v={money(ov.ttm.revenue)} />
            <Stat l="Net income" v={money(ov.ttm.net_income)} cls={tone(ov.ttm.net_income)} />
            <Stat l="Free cash flow" v={money(ov.ttm.free_cash_flow)} cls={tone(ov.ttm.free_cash_flow)} />
            <Stat l="Gross margin" v={pct(ov.margins.gross, 1, false)} />
            <Stat l="Op. margin" v={pct(ov.margins.operating, 1, false)} />
            <Stat l="R&D / sales" v={pct(ov.margins.rnd, 1, false)} />
            <Stat l="Cash + ST inv." v={money(ov.balance.total_cash)} s={date(ov.balance.as_of)} />
            <Stat l="Total debt" v={money(ov.balance.total_debt)} />
            <Stat l="52w range" v={`${price(ov.low_52w)}`} s={`→ ${price(ov.high_52w)}`} />
          </div>
        </section>
        <section className="panel">
          <header>Returns</header>
          <Returns r={ov.returns} />
        </section>
      </div>

      <section className="panel">
        <header>Quarterly revenue, profit &amp; margins<span className="grow" />
          <a style={{ textTransform: 'none', letterSpacing: 0 }} onClick={() => nav(`/c/${t}/financials`)}>Open financials →</a></header>
        <div className="body">{st ? <Fundamentals st={st} /> : <div className="loading">loading</div>}</div>
      </section>

      <section className="panel" style={{ gridRow: 'span 2' }}>
        <header>Recent events</header>
        <EventList events={ov.recent_events} onOpen={open} />
      </section>

      <section className="panel">
        <header>Profile</header>
        <div className="body" style={{ display: 'grid', gridTemplateColumns: '150px 1fr', rowGap: 6, columnGap: 12 }}>
          <span className="dimmer">Legal name</span><span>{co.name}</span>
          <span className="dimmer">Industry</span><span>{co.sic_desc} <span className="dimmer mono">SIC {co.sic}</span></span>
          <span className="dimmer">Filer status</span><span>{co.category}</span>
          <span className="dimmer">Incorporated</span><span>{co.state_of_inc} · FYE {co.fiscal_year_end?.slice(0, 2)}/{co.fiscal_year_end?.slice(2)}</span>
          <span className="dimmer">HQ</span><span>{addr ? `${addr.street1}, ${addr.city}, ${addr.stateOrCountry} ${addr.zipCode}` : '—'}</span>
          <span className="dimmer">SEC CIK</span><span className="mono"><a href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${co.cik}`} target="_blank" rel="noreferrer">{co.cik}</a> · EIN {co.ein}</span>
          {formerNames.length ? <><span className="dimmer">Former names</span><span>{formerNames.map((f) => `${f.name} (to ${f.to?.slice(0, 4)})`).join(' · ')}</span></> : null}
          <span className="dimmer">Archive</span><span className="mono">{ov.counts.filings_archived.toLocaleString()} filings · {ov.counts.documents.toLocaleString()} docs · {ov.counts.insider_txns.toLocaleString()} insider txns · {ov.counts.people} people</span>
        </div>
      </section>
    </div>
  )
}
