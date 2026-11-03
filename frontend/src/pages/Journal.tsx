import { useEffect, useState } from 'react'
import type { Journal as JournalT, Note, Trade } from '../api'
import { get, send } from '../api'
import { date, money, pct, price, tone } from '../format'

const today = () => new Date().toISOString().slice(0, 10)

function useJournal(t: string) {
  const [data, setData] = useState<JournalT | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const reload = () => get<JournalT>(`c/${t}/journal`, { fresh: true }).then(setData, (e) => setErr(e.message))
  useEffect(() => { reload() }, [t]) // eslint-disable-line react-hooks/exhaustive-deps
  return { data, err, reload, setErr }
}

function TradeForm({ t, last, onDone }: { t: string; last: number | null; onDone: () => void }) {
  const [f, setF] = useState({ side: 'long', qty: '10', entry_date: today(), entry_price: last ? last.toFixed(2) : '', stop: '', target: '', thesis: '' })
  const [err, setErr] = useState<string | null>(null)
  const up = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value })
  const risk = f.stop && f.entry_price ? Math.abs(+f.entry_price - +f.stop) * +f.qty : null
  const reward = f.target && f.entry_price ? Math.abs(+f.target - +f.entry_price) * +f.qty : null
  return (
    <form className="body" style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8, alignItems: 'end' }}
      onSubmit={async (e) => {
        e.preventDefault()
        try { await send('POST', `c/${t}/journal/trades`, f); setF({ ...f, thesis: '', stop: '', target: '' }); setErr(null); onDone() } catch (x) { setErr((x as Error).message) }
      }}>
      <label className="dimmer" style={{ fontSize: 11 }}>Side<select className="input" style={{ width: '100%' }} value={f.side} onChange={up('side')}><option value="long">Long</option><option value="short">Short</option></select></label>
      <label className="dimmer" style={{ fontSize: 11 }}>Shares<input className="input" style={{ width: '100%' }} value={f.qty} onChange={up('qty')} inputMode="decimal" /></label>
      <label className="dimmer" style={{ fontSize: 11 }}>Entry date<input className="input" type="date" style={{ width: '100%' }} value={f.entry_date} onChange={up('entry_date')} /></label>
      <label className="dimmer" style={{ fontSize: 11 }}>Entry price<input className="input" style={{ width: '100%' }} value={f.entry_price} onChange={up('entry_price')} inputMode="decimal" /></label>
      <label className="dimmer" style={{ fontSize: 11 }}>Stop<input className="input" style={{ width: '100%' }} value={f.stop} onChange={up('stop')} inputMode="decimal" placeholder="required for R" /></label>
      <label className="dimmer" style={{ fontSize: 11 }}>Target<input className="input" style={{ width: '100%' }} value={f.target} onChange={up('target')} inputMode="decimal" /></label>
      <label className="dimmer" style={{ fontSize: 11, gridColumn: '1 / 6' }}>Thesis — why, what would prove you wrong<textarea className="input" rows={2} style={{ width: '100%', resize: 'vertical' }} value={f.thesis} onChange={up('thesis')} /></label>
      <button className="chip on" style={{ justifyContent: 'center', height: 36 }} type="submit">+ Paper trade</button>
      <div className="mono dimmer" style={{ gridColumn: '1 / -1', fontSize: 11 }}>
        Notional {money(+f.qty * +f.entry_price || null)}{risk !== null ? ` · risk ${money(risk)}` : ''}{reward !== null ? ` · reward ${money(reward)}` : ''}{risk && reward ? ` · R:R ${(reward / risk).toFixed(2)}` : ''}
        {err ? <span className="down"> · {err}</span> : null}
      </div>
    </form>
  )
}

function TradeRow({ t, x, onDone }: { t: string; x: Trade; onDone: () => void }) {
  const [closing, setClosing] = useState(false)
  const [ex, setEx] = useState({ exit_date: today(), exit_price: x.mark?.toFixed(2) ?? '', exit_reason: '' })
  return (
    <>
      <tr>
        <td className="mono dim">{x.entry_date}</td>
        <td><span className={'tag ' + (x.side === 'long' ? 'f4' : 'px')}>{x.side}</span></td>
        <td className="n">{x.qty}</td>
        <td className="n">{price(x.entry_price)}</td>
        <td className="n dim">{x.stop ? price(x.stop) : '—'} / {x.target ? price(x.target) : '—'}</td>
        <td className="n">{price(x.mark)}{x.open ? <span className="dimmer"> mark</span> : <span className="dimmer"> exit</span>}</td>
        <td className={'n ' + tone(x.pnl)}>{money(x.pnl)} <span className="dimmer">{pct(x.pnl_pct)}</span></td>
        <td className={'n ' + tone(x.r)}>{x.r !== undefined && x.r !== null ? x.r.toFixed(2) + 'R' : '—'}</td>
        <td style={{ whiteSpace: 'normal', maxWidth: 300 }} className="dim">{x.thesis}{x.exit_reason ? <div className="dimmer">exit: {x.exit_reason}</div> : null}</td>
        <td className="nowrap">
          {x.open && <button className="chip" onClick={() => setClosing(!closing)}>close</button>}{' '}
          <button className="chip" onClick={async () => { if (confirm('Delete this trade? (kept in journal.log.jsonl)')) { await send('DELETE', `c/${t}/journal/trades/${x.id}`); onDone() } }}>✕</button>
        </td>
      </tr>
      {closing && (
        <tr><td colSpan={10}>
          <form style={{ display: 'flex', gap: 8 }} onSubmit={async (e) => { e.preventDefault(); await send('POST', `c/${t}/journal/trades/${x.id}`, ex); setClosing(false); onDone() }}>
            <input className="input" type="date" value={ex.exit_date} onChange={(e) => setEx({ ...ex, exit_date: e.target.value })} />
            <input className="input" placeholder="exit price" value={ex.exit_price} onChange={(e) => setEx({ ...ex, exit_price: e.target.value })} />
            <input className="input" style={{ flex: 1 }} placeholder="why did you exit? (stop / target / thesis broken / time)" value={ex.exit_reason} onChange={(e) => setEx({ ...ex, exit_reason: e.target.value })} />
            <button className="chip on" type="submit">Close trade</button>
          </form>
        </td></tr>
      )}
    </>
  )
}

function NoteEditor({ t, note, onDone }: { t: string; note?: Note; onDone: () => void }) {
  const [title, setTitle] = useState(note?.title ?? '')
  const [body, setBody] = useState(note?.body ?? '')
  const [saved, setSaved] = useState(true)
  const save = async () => {
    if (!title && !body) return
    await send('POST', `c/${t}/journal/notes` + (note ? `/${note.id}` : ''), { title, body })
    setSaved(true)
    if (!note) { setTitle(''); setBody('') }
    onDone()
  }
  return (
    <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--line)' }}>
      <input className="input" style={{ width: '100%', marginBottom: 6, fontWeight: 600 }} placeholder={note ? 'Title' : 'New note title'} value={title} onChange={(e) => { setTitle(e.target.value); setSaved(false) }} />
      <textarea className="input" rows={note ? 4 : 3} style={{ width: '100%', resize: 'vertical', lineHeight: 1.55 }} placeholder="Observations, questions, what to check next earnings…" value={body}
        onChange={(e) => { setBody(e.target.value); setSaved(false) }} onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') save() }} />
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 11 }} className="dimmer">
        {note ? `updated ${date(note.updated)}` : '⌘↵ to save'}
        <span style={{ flex: 1 }} />
        {!saved && <button className="chip on" onClick={save}>save</button>}
        {note && <button className="chip" onClick={async () => { if (confirm('Delete note? (kept in journal.log.jsonl)')) { await send('DELETE', `c/${t}/journal/notes/${note.id}`); onDone() } }}>delete</button>}
      </div>
    </div>
  )
}

export default function Journal({ t }: { t: string }) {
  const { data, err, reload } = useJournal(t)
  if (err) return <div className="err">{err}</div>
  if (!data) return <div className="loading">loading journal</div>
  const closed = data.trades.filter((x) => !x.open)
  const open = data.trades.filter((x) => x.open)
  const realized = closed.reduce((s, x) => s + (x.pnl ?? 0), 0)
  const unreal = open.reduce((s, x) => s + (x.pnl ?? 0), 0)
  const wins = closed.filter((x) => (x.pnl ?? 0) > 0).length
  const rs = closed.map((x) => x.r).filter((r): r is number => r !== null && r !== undefined)
  return (
    <div className="grid">
      <div className="page-title"><h1>Journal</h1><span className="sub">Your notes and paper trades — stored in data/journal.db (back it up; it's the only data that isn't rebuildable) · marks use the last close {data.last ? `(${date(data.last.date)})` : ''}</span></div>
      <section className="panel">
        <div className="stats" style={{ gridTemplateColumns: 'repeat(6, 1fr)' }}>
          <div className="stat"><div className="l">Open trades</div><div className="v">{open.length}</div></div>
          <div className="stat"><div className="l">Unrealized</div><div className={'v ' + tone(unreal)}>{money(unreal)}</div></div>
          <div className="stat"><div className="l">Closed trades</div><div className="v">{closed.length}</div></div>
          <div className="stat"><div className="l">Realized</div><div className={'v ' + tone(realized)}>{money(realized)}</div></div>
          <div className="stat"><div className="l">Win rate</div><div className="v">{closed.length ? Math.round(wins / closed.length * 100) + '%' : '—'}</div><div className="s">{wins}W / {closed.length - wins}L</div></div>
          <div className="stat"><div className="l">Avg R (with stop)</div><div className={'v ' + tone(rs.length ? rs.reduce((a, b) => a + b, 0) : null)}>{rs.length ? (rs.reduce((a, b) => a + b, 0) / rs.length).toFixed(2) + 'R' : '—'}</div><div className="s">{rs.length} trades</div></div>
        </div>
      </section>
      <section className="panel">
        <header>New paper trade · {t}</header>
        <TradeForm t={t} last={data.last?.close ?? null} onDone={reload} />
      </section>
      <section className="panel">
        <header>Trades</header>
        {data.trades.length ? (
          <table className="t">
            <thead><tr><th>Entry</th><th>Side</th><th className="n">Qty</th><th className="n">Entry $</th><th className="n">Stop / target</th><th className="n">Mark / exit</th><th className="n">P&amp;L</th><th className="n">R</th><th>Thesis</th><th></th></tr></thead>
            <tbody>{data.trades.map((x) => <TradeRow key={x.id} t={t} x={x} onDone={reload} />)}</tbody>
          </table>
        ) : <div className="empty">No paper trades yet. Write the thesis and the stop <i>before</i> you enter — that's the habit this page exists to build.</div>}
      </section>
      <section className="panel">
        <header>Notes</header>
        <NoteEditor t={t} onDone={reload} />
        {data.notes.map((n) => <NoteEditor key={n.id + n.updated} t={t} note={n} onDone={reload} />)}
      </section>
    </div>
  )
}
