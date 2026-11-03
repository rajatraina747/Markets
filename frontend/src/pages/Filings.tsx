import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import type { FilingDetail, FilingsPage } from '../api'
import { fileUrl } from '../api'
import { useApi, useDebounced } from '../hooks'
import { bytes, date } from '../format'

const GROUPS: [string, string][] = [
  ['all', 'All'], ['annual', 'Annual'], ['quarterly', 'Quarterly'], ['current', '8-K'], ['proxy', 'Proxy'],
  ['insider', 'Insider'], ['ownership', '13D/G'], ['registration', 'Offerings'], ['other', 'Other'],
]

export function formTag(form: string) {
  const f = form.toUpperCase()
  const cls = f.startsWith('10-K') || f === 'ARS' ? 'k10' : f.startsWith('10-Q') ? 'q10' : f.startsWith('8-K') ? 'k8'
    : ['3', '4', '5', '144', '4/A', '3/A', '5/A'].includes(f) ? 'f4' : f.includes('14A') ? 'px' : ''
  return <span className={'tag ' + cls}>{form}</span>
}

export function FilingReader({ t, acc, docSeq, highlight }: { t: string; acc: string; docSeq?: number; highlight?: string }) {
  const { data, error } = useApi<FilingDetail>(`c/${t}/filings/${acc}`)
  const [seq, setSeq] = useState<number | undefined>(docSeq)
  const [asText, setAsText] = useState(!!highlight)
  useEffect(() => { setSeq(docSeq); setAsText(!!highlight) }, [acc, docSeq, highlight])
  if (error) return <div className="err">{error}</div>
  if (!data) return <div className="loading">loading filing</div>
  const f = data.filing
  const docs = data.documents
  const primary = docs.find((d) => d.filename === f.primary_doc?.split('/').pop()) ?? docs.find((d) => d.kind === 'html' || d.kind === 'text') ?? docs[0]
  const cur = docs.find((d) => d.seq === seq) ?? primary
  return (
    <>
      <header>
        {formTag(f.form)}<span style={{ textTransform: 'none', letterSpacing: 0, color: 'var(--text)' }}>{f.primary_desc || f.form}</span>
        <span className="grow" />
        <span className="mono dimmer" style={{ textTransform: 'none', letterSpacing: 0 }}>filed {date(f.filed)}{f.report_date ? ` · period ${date(f.report_date)}` : ''}</span>
        <a href={data.sec_url} target="_blank" rel="noreferrer" style={{ textTransform: 'none', letterSpacing: 0 }}>SEC ↗</a>
      </header>
      {!f.raw_path ? (f.accession.startsWith('CH-') && f.primary_doc
        ? <div className="empty">Companies House filing · <a href={f.primary_doc} target="_blank" rel="noreferrer">open the PDF at Companies House ↗</a></div>
        : <div className="empty">Not archived {t.includes('.') ? '(non-SEC company)' : <>yet — run <code>./markets update {t}</code>{' '}(lite tickers archive only ownership + proxy filings; <code>./markets add {t} --full</code> for everything)</>}</div>) : (
        <>
          <div className="doclist">
            {docs.map((d) => (
              <div key={d.seq} className={'doc' + (cur?.seq === d.seq ? ' on' : '')} onClick={() => setSeq(d.seq)}>
                <span className="tag" style={{ minWidth: 70, textAlign: 'center' }}>{d.doc_type}</span>
                <span style={{ flex: 1, minWidth: 0 }} className="fn">{d.description || d.filename}</span>
                <span className="mono dimmer" style={{ fontSize: 11 }}>{d.kind} · {bytes(d.bytes)}</span>
              </div>
            ))}
          </div>
          {cur && (cur.kind === 'html' || cur.kind === 'text') && (
            <div style={{ display: 'flex', gap: 8, padding: '6px 14px', borderBottom: '1px solid var(--line)', alignItems: 'center' }}>
              <div className="seg"><button className={!asText ? 'on' : ''} onClick={() => setAsText(false)}>original</button><button className={asText ? 'on' : ''} onClick={() => setAsText(true)}>text</button></div>
              <a href={fileUrl(t, acc, cur.filename)} target="_blank" rel="noreferrer" className="mono" style={{ fontSize: 11 }}>open in tab ↗</a>
            </div>
          )}
          {cur ? (asText && (cur.kind === 'html' || cur.kind === 'text')
            ? <TextDoc t={t} acc={acc} seq={cur.seq} highlight={highlight} />
            : cur.kind === 'binary' && !/\.(jpg|jpeg|gif|png|pdf)$/i.test(cur.filename)
              ? <div className="empty"><a href={fileUrl(t, acc, cur.filename)}>Download {cur.filename}</a></div>
              : <iframe key={cur.filename} className="reader" sandbox="" src={fileUrl(t, acc, cur.filename)} title={cur.filename}
                style={{ background: cur.kind === 'xml' ? 'var(--bg-1)' : '#fff' }} />)
            : null}
        </>
      )}
    </>
  )
}

function TextDoc({ t, acc, seq, highlight }: { t: string; acc: string; seq: number; highlight?: string }) {
  const { data, error } = useApi<{ text: string }>(`c/${t}/text/${acc}/${seq}`)
  const parts = useMemo(() => {
    if (!data) return null
    const terms = (highlight ?? '').replace(/["*()]/g, ' ').split(/\s+/).filter((w) => w.length > 2 && !['AND', 'OR', 'NOT', 'NEAR'].includes(w))
    if (!terms.length) return [data.text]
    const rx = new RegExp('(' + terms.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'gi')
    return data.text.split(rx)
  }, [data, highlight])
  useEffect(() => {
    const id = setTimeout(() => document.querySelector('.textdoc mark')?.scrollIntoView({ block: 'center' }), 60)
    return () => clearTimeout(id)
  }, [parts])
  if (error) return <div className="empty">No extracted text for this document (search index covers non-insider filings).</div>
  if (!parts) return <div className="loading">loading text</div>
  return <div className="scroll" style={{ overflow: 'auto', flex: 1 }}><div className="textdoc">{parts.map((p, i) => (i % 2 ? <mark key={i}>{p}</mark> : p))}</div></div>
}

export default function Filings({ t }: { t: string }) {
  const { acc } = useParams()
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const group = sp.get('group') ?? 'all'
  const year = sp.get('year') ?? ''
  const [qIn, setQIn] = useState(sp.get('q') ?? '')
  const q = useDebounced(qIn)
  const [limit, setLimit] = useState(150)
  const path = `c/${t}/filings?limit=${limit}` + (group !== 'all' ? `&group=${group}` : '') + (year ? `&year=${year}` : '') + (q ? `&q=${encodeURIComponent(q)}` : '')
  const { data, error } = useApi<FilingsPage>(path)
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }) }

  return (
    <div className="split">
      <section className="panel">
        <header>Filings<span className="grow" /><span className="mono dimmer" style={{ textTransform: 'none', letterSpacing: 0 }}>{data ? `${data.total.toLocaleString()} shown of ${data.groups.all.toLocaleString()}` : ''}</span></header>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--line)' }}>
          <div className="filters" style={{ marginBottom: 8 }}>
            {GROUPS.map(([k, l]) => (
              <span key={k} className={'chip' + (group === k ? ' on' : '')} onClick={() => set('group', k === 'all' ? '' : k)}>
                {l}<span className="n">{data?.groups[k] ?? ''}</span>
              </span>
            ))}
          </div>
          <div className="filters" style={{ marginBottom: 0 }}>
            <input className="input" style={{ flex: 1 }} placeholder="Filter by form, description, 8-K item, accession…" value={qIn} onChange={(e) => setQIn(e.target.value)} />
            <select className="input" value={year} onChange={(e) => set('year', e.target.value)}>
              <option value="">All years</option>
              {data?.years.map((y) => <option key={y}>{y}</option>)}
            </select>
          </div>
        </div>
        <div className="scroll">
          {error ? <div className="err">{error}</div> : !data ? <div className="loading">loading</div> : (
            <table className="t">
              <thead><tr><th>Filed</th><th>Form</th><th>Description</th><th className="n">Size</th></tr></thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.accession} className={'click' + (acc === r.accession ? ' sel' : '')} onClick={() => nav(`/c/${t}/filings/${r.accession}?${sp.toString()}`)}>
                    <td className="mono dim">{r.filed}</td>
                    <td>{formTag(r.form)}</td>
                    <td style={{ whiteSpace: 'normal' }}>
                      {r.primary_desc || r.form}
                      {r.items ? <span className="dimmer mono" style={{ fontSize: 11 }}> · items {r.items}</span> : null}
                      {!r.archived ? <span className="dimmer" style={{ fontSize: 11 }}> · not archived</span> : null}
                    </td>
                    <td className="n dim">{bytes(r.size)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {data && data.total > data.rows.length && <div style={{ padding: 12, textAlign: 'center' }}><button className="chip" onClick={() => setLimit(limit + 300)}>Load more ({(data.total - data.rows.length).toLocaleString()} left)</button></div>}
        </div>
      </section>
      <section className="panel">
        {acc ? <FilingReader t={t} acc={acc} /> : <div className="empty">Select a filing to read it. Every document and exhibit is served from your local archive.</div>}
      </section>
    </div>
  )
}
