import { useMemo, useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { SearchResult } from '../api'
import { useApi, useDebounced } from '../hooks'
import { EChart, base, axis, C } from '../components/EChart'
import { date } from '../format'
import { FilingReader, formTag } from './Filings'

const EXAMPLES = ['robotaxi', 'Gigafactory Berlin', '"going concern"', 'recall', 'lithium', 'material weakness', 'tariff*', 'Optimus']

function Snip({ s }: { s: string }) {
  const parts = s.split(/(\u0002[^\u0003]*\u0003)/)
  return <div className="snip">{parts.map((p, i) => (p.startsWith('\u0002') ? <mark key={i}>{p.slice(1, -1)}</mark> : <span key={i}>{p}</span>))}</div>
}

export default function Search({ t }: { t: string }) {
  const [sp, setSp] = useSearchParams()
  const [qIn, setQIn] = useState(sp.get('q') ?? '')
  const q = useDebounced(qIn.trim(), 350)
  const [sort, setSort] = useState<'rank' | 'date'>('rank')
  const [sel, setSel] = useState<{ acc: string; seq: number } | null>(null)
  useEffect(() => { const n = new URLSearchParams(sp); if (q) n.set('q', q); else n.delete('q'); setSp(n, { replace: true }) }, [q]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => setQIn(sp.get('q') ?? ''), [sp.get('q')]) // eslint-disable-line react-hooks/exhaustive-deps
  const { data, loading } = useApi<SearchResult>(q ? `c/${t}/search?q=${encodeURIComponent(q)}&limit=100&sort=${sort}` : null)

  const option = useMemo(() => data?.by_year?.length ? {
    ...base, grid: { left: 36, right: 8, top: 10, bottom: 22 },
    tooltip: { ...base.tooltip, axisPointer: { type: 'shadow' } },
    xAxis: { type: 'category', data: data.by_year.map((y) => y.year), ...axis },
    yAxis: { type: 'value', ...axis, minInterval: 1 },
    series: [{ type: 'bar', data: data.by_year.map((y) => y.n), itemStyle: { color: C.gold, borderRadius: [3, 3, 0, 0] }, name: 'documents' }],
  } : null, [data])

  return (
    <div className="split">
      <section className="panel">
        <header>Full-text search<span className="grow" /><span className="mono dimmer" style={{ textTransform: 'none', letterSpacing: 0 }}>{data ? `${data.total.toLocaleString()} documents` : ''}</span></header>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--line)' }}>
          <div className="filters" style={{ marginBottom: 6 }}>
            <input autoFocus className="input" style={{ flex: 1, fontSize: 14 }} placeholder='Search every filing — words, "exact phrases", prefix*, a OR b' value={qIn} onChange={(e) => setQIn(e.target.value)} />
            <div className="seg"><button className={sort === 'rank' ? 'on' : ''} onClick={() => setSort('rank')}>relevance</button><button className={sort === 'date' ? 'on' : ''} onClick={() => setSort('date')}>newest</button></div>
          </div>
          {!q && <div className="filters" style={{ marginBottom: 0 }}>{EXAMPLES.map((e) => <span key={e} className="chip" onClick={() => setQIn(e)}>{e}</span>)}</div>}
          {option && <div><div className="dimmer" style={{ fontSize: 11, marginTop: 4 }}>Mentions by filing year</div><EChart option={option} height={110} /></div>}
        </div>
        <div className="scroll">
          {data?.error && <div className="err">{data.error}</div>}
          {loading && <div className="loading">searching</div>}
          {data?.results.map((r) => (
            <div key={r.accession + r.seq} className={'hit' + (sel?.acc === r.accession && sel.seq === r.seq ? ' sel' : '')} onClick={() => setSel({ acc: r.accession, seq: r.seq })}
              style={sel?.acc === r.accession && sel.seq === r.seq ? { background: 'var(--gold-dim)' } : undefined}>
              <div className="meta">{formTag(r.form)}<span className="mono">{date(r.filed)}</span><span className="tag">{r.doc_type}</span></div>
              <Snip s={r.snip} />
            </div>
          ))}
          {data && !data.results.length && !data.error && <div className="empty">No matches.</div>}
        </div>
      </section>
      <section className="panel">
        {sel ? <FilingReader t={t} acc={sel.acc} docSeq={sel.seq} highlight={q} /> : <div className="empty">Search across every 10-K, 10-Q, 8-K, proxy and exhibit in the archive. Click a result to read it with matches highlighted.</div>}
      </section>
    </div>
  )
}
