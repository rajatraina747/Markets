import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { Diff, TenK } from '../api'
import { useApi } from '../hooks'
import { date } from '../format'

const PRESET = ['1A', '7', '1', '7A', '9A', '3', '1C']

export default function Compare({ t }: { t: string }) {
  const { data: list, error } = useApi<TenK[]>(`c/${t}/tenk`)
  const [sp, setSp] = useSearchParams()
  const avail = (list ?? []).filter((x) => x.has_text)
  const b = sp.get('b') ?? avail[0]?.accession ?? ''
  const a = sp.get('a') ?? avail[1]?.accession ?? ''
  const item = sp.get('item') ?? '1A'
  const [onlyChanges, setOnlyChanges] = useState(true)
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); n.set(k, v); setSp(n, { replace: true }) }
  const { data: d, loading } = useApi<Diff>(a && b ? `c/${t}/diff?a=${a}&b=${b}&item=${item}` : null)
  useEffect(() => { window.scrollTo(0, 0) }, [item, a, b])

  if (error) return <div className="err">{error}</div>
  const label = (x: TenK) => `FY${x.report_date?.slice(0, 4) ?? x.filed.slice(0, 4)} · filed ${x.filed}`
  return (
    <div className="grid">
      <div className="page-title"><h1>10-K compare</h1><span className="sub">What changed in the annual report, paragraph by paragraph · older on the left of each change, newer highlighted</span></div>
      <div className="filters">
        <span className="dimmer">Older</span>
        <select className="input" value={a} onChange={(e) => set('a', e.target.value)}>{avail.map((x) => <option key={x.accession} value={x.accession}>{label(x)}</option>)}</select>
        <span className="dimmer">→ Newer</span>
        <select className="input" value={b} onChange={(e) => set('b', e.target.value)}>{avail.map((x) => <option key={x.accession} value={x.accession}>{label(x)}</option>)}</select>
        <span style={{ width: 16 }} />
        {PRESET.map((k) => <span key={k} className={'chip' + (item === k ? ' on' : '')} onClick={() => set('item', k)}>Item {k}<span className="n">{d?.item_labels?.[k]}</span></span>)}
        <span className="grow" style={{ flex: 1 }} />
        <div className="seg"><button className={onlyChanges ? 'on' : ''} onClick={() => setOnlyChanges(!onlyChanges)}>changes only</button></div>
      </div>
      {list && avail.length < 2 && <div className="empty">Need at least two 10-Ks with extracted text — they appear as the archive downloads and the search index rebuilds.</div>}
      {loading && <div className="loading">diffing</div>}
      {d?.error && <div className="err">{d.error}</div>}
      {d?.stats && (
        <section className="panel">
          <div className="stats" style={{ gridTemplateColumns: 'repeat(6, 1fr)' }}>
            <div className="stat"><div className="l">Item</div><div className="v gold">{d.item} · {d.label}</div></div>
            <div className="stat"><div className="l">Similarity</div><div className="v">{(d.stats.similarity * 100).toFixed(0)}%</div></div>
            <div className="stat"><div className="l">Added ¶</div><div className="v up">+{d.stats.added}</div></div>
            <div className="stat"><div className="l">Removed ¶</div><div className="v down">−{d.stats.removed}</div></div>
            <div className="stat"><div className="l">Changed ¶</div><div className="v">{d.stats.changed}</div></div>
            <div className="stat"><div className="l">Words</div><div className="v">{d.stats.words_a.toLocaleString()} → {d.stats.words_b.toLocaleString()}</div><div className="s">{d.stats.words_b >= d.stats.words_a ? '+' : ''}{(((d.stats.words_b / d.stats.words_a) - 1) * 100).toFixed(0)}%</div></div>
          </div>
        </section>
      )}
      {d?.blocks && (
        <section className="panel">
          <header>{d.item} · {d.label}<span className="grow" /><span className="mono dimmer" style={{ textTransform: 'none', letterSpacing: 0 }}>{date(avail.find((x) => x.accession === a)?.filed)} → {date(avail.find((x) => x.accession === b)?.filed)}</span></header>
          <div style={{ padding: '6px 0', maxWidth: 1100 }}>
            {d.blocks.map((blk, i) => {
              if (blk.op === 'equal') return onlyChanges
                ? <div key={i} className="dimmer" style={{ padding: '4px 20px', fontSize: 11, fontFamily: 'var(--mono)' }}>· · · {blk.n} unchanged paragraph{blk.n > 1 ? 's' : ''} — “{blk.first.slice(0, 90)}…”</div>
                : <div key={i} className="dim" style={{ padding: '6px 20px' }}>{blk.first}…</div>
              if (blk.op === 'add') return <p key={i} style={{ margin: 0, padding: '8px 20px', borderLeft: '3px solid var(--up)', background: 'rgba(47,191,113,.07)' }}>{blk.text}</p>
              if (blk.op === 'remove') return <p key={i} style={{ margin: 0, padding: '8px 20px', borderLeft: '3px solid var(--down)', background: 'rgba(240,82,79,.06)', color: 'var(--text-2)', textDecoration: 'line-through', textDecorationColor: 'rgba(240,82,79,.5)' }}>{blk.text}</p>
              if (blk.op !== 'change') return null
              return (
                <p key={i} style={{ margin: 0, padding: '8px 20px', borderLeft: '3px solid var(--gold)', lineHeight: 1.6 }}>
                  {blk.words.map(([op, w], j) => op === '=' ? <span key={j}>{w} </span>
                    : op === '+' ? <span key={j} style={{ background: 'rgba(47,191,113,.22)', color: '#bff0d2', borderRadius: 3 }}>{w} </span>
                      : <span key={j} style={{ background: 'rgba(240,82,79,.18)', color: '#f6b3b2', textDecoration: 'line-through', borderRadius: 3 }}>{w} </span>)}
                </p>
              )
            })}
          </div>
        </section>
      )}
    </div>
  )
}
