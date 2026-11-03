// One physical monitor of a desk. Opened by the Desk controller as /display?desk=…&id=N.
// Each pane is the full terminal in an iframe (chrome-less, see EmbedBridge) so it can navigate
// freely; panes report their route back, which drives cross-display security linking.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  type Desk, type Display as DisplayT, type DeskMsg, type Link, type Pane, FUNCTIONS, LINKS, LINK_COLORS,
  channel, fitPanes, loadDesks, parseCommand, parsePath, pathFor, rememberGeometry, saveDesks,
} from './model'

const GRID: Record<string, React.CSSProperties> = {
  '1': { gridTemplate: '1fr / 1fr' },
  '2h': { gridTemplate: '1fr / 1fr 1fr' },
  '2v': { gridTemplate: '1fr 1fr / 1fr' },
  '3': { gridTemplate: '1fr 1fr / 1.4fr 1fr', gridTemplateAreas: '"a b" "a c"' },
  '4': { gridTemplate: '1fr 1fr / 1fr 1fr' },
}

function Clock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => { const id = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(id) }, [])
  const f = (tz: string) => now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: tz })
  const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))
  const mins = et.getHours() * 60 + et.getMinutes(), wd = et.getDay()
  const open = wd > 0 && wd < 6 && mins >= 570 && mins < 960
  return (
    <span className="mono dim" style={{ fontSize: 11, display: 'flex', gap: 12 }}>
      <span>NY {f('America/New_York')} <span className={open ? 'up' : 'dimmer'}>{open ? '● open' : '○ closed'}</span></span>
      <span>LDN {f('Europe/London')}</span>
      <span>LOCAL {now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span>
    </span>
  )
}

function PaneView({ pane, ticker, active, onActivate, onRoute, onCommand, onLink, maximized, onMax, index, area }: {
  pane: Pane; ticker: string; active: boolean; onActivate: () => void; index: number; area?: string
  onRoute: (fn: string, ticker: string | null) => void; onCommand: (cmd: string) => string | null
  onLink: (l: Link) => void; maximized: boolean; onMax: () => void
}) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [cmd, setCmd] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const cmdRef = useRef<HTMLInputElement>(null)
  const want = pathFor(pane.fn, ticker)
  const [src] = useState(() => want)                       // iframe loads once; later moves are postMessages
  const lastSent = useRef(want)
  const fn = FUNCTIONS[pane.fn]

  // drive the embedded app when the pane's function/security changes from outside
  useEffect(() => {
    const cur = parsePath(lastSent.current)
    const company = FUNCTIONS[pane.fn]?.company
    // already showing this function for this security (maybe deeper, e.g. one filing) — leave it
    if (cur.fn === pane.fn && (!company || cur.ticker === ticker.toUpperCase())) return
    lastSent.current = want
    frame.current?.contentWindow?.postMessage({ type: 'markets:navigate', path: want }, location.origin)
  }, [want, pane.fn, ticker])

  // routes reported by the embedded app
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.origin !== location.origin || e.source !== frame.current?.contentWindow) return
      if (e.data?.type === 'markets:route') {
        lastSent.current = e.data.path
        const p = parsePath(e.data.path)
        onRoute(p.fn, p.ticker)
      }
      if (e.data?.type === 'markets:focus-command') cmdRef.current?.focus()
      if (e.data?.type === 'markets:activate') onActivate()
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [onRoute, onActivate])

  useEffect(() => { if (active) cmdRef.current?.focus() }, [active])
  const color = LINK_COLORS[pane.link]
  return (
    <div className={'dk-pane' + (active ? ' active' : '')} style={{ borderTopColor: color, gridArea: area, ...(maximized ? { gridArea: '1 / 1 / -1 / -1', zIndex: 3 } : {}) }}
      onMouseDown={onActivate}>
      <div className="dk-phead">
        <span className="dk-num">{index + 1}</span>
        <select className="ws-link" value={pane.link} style={{ background: color }} onChange={(e) => onLink(e.target.value as Link)} title="link group — panes of one colour share a security across every screen">
          {LINKS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
        <span className="dk-sec mono" style={{ color }}>{fn?.company || pane.fn === 'RV' ? ticker : ''}</span>
        <span className="dk-fn mono">{pane.fn}</span>
        <span className="dimmer" style={{ fontSize: 11 }}>{fn?.label}</span>
        <form className="dk-cmd" onSubmit={(e) => { e.preventDefault(); const r = onCommand(cmd); setErr(r); if (!r) setCmd('') }}>
          <span className="gold mono" style={{ fontSize: 11 }}>›</span>
          <input ref={cmdRef} className="mono" value={cmd} spellCheck={false} placeholder="TICKER FUNCTION <GO>  e.g. NVDA ERN"
            onChange={(e) => { setCmd(e.target.value.toUpperCase()); setErr(null) }} onKeyDown={(e) => { if (e.key === 'Escape') { setCmd(''); setErr(null) } }} />
          {err && <span className="down" style={{ fontSize: 11 }}>{err}</span>}
          <button className="dk-go" type="submit">GO</button>
        </form>
        <button className="ws-btn" title="back" onClick={() => frame.current?.contentWindow?.history.back()}>‹</button>
        <button className="ws-btn" title={maximized ? 'restore' : 'maximise pane'} onClick={onMax}>{maximized ? '▣' : '□'}</button>
      </div>
      <iframe ref={frame} className="dk-frame" src={src} title={`pane ${index + 1}`} />
    </div>
  )
}

export default function DisplayWindow() {
  const [sp] = useSearchParams()
  const deskName = sp.get('desk') || ''
  const id = Number(sp.get('id') || 1)
  const [desk, setDesk] = useState<Desk | null>(() => loadDesks('TSLA').desks[deskName] ?? null)
  const [active, setActive] = useState(0)
  const [maxPane, setMaxPane] = useState<number | null>(null)
  const [flash, setFlash] = useState(false)
  const ch = useMemo(() => channel(), [])
  const display: DisplayT | undefined = desk?.displays.find((d) => d.id === id)

  const updateDisplay = useCallback((fn: (d: DisplayT) => DisplayT) => setDesk((dk) => {
    if (!dk) return dk
    const next = { ...dk, displays: dk.displays.map((d) => (d.id === id ? fn(d) : d)) }
    const s = loadDesks('TSLA'); s.desks[next.name] = next; saveDesks(s)
    return next
  }), [id])

  const setGroup = useCallback((group: string, ticker: string, broadcast = true) => {
    setDesk((dk) => {
      if (!dk || dk.groups[group] === ticker) return dk
      const next = { ...dk, groups: { ...dk.groups, [group]: ticker } }
      const s = loadDesks('TSLA'); s.desks[next.name] = next; saveDesks(s)
      return next
    })
    if (broadcast) ch?.postMessage({ type: 'link', group, ticker, from: `${deskName}:${id}` } satisfies DeskMsg)
  }, [ch, deskName, id])

  // channel: heartbeats out; link / identify / close / config in
  useEffect(() => {
    if (!ch) return
    const hello = () => ch.postMessage({ type: 'hello', id, desk: deskName, at: Date.now(), title: display?.name } satisfies DeskMsg)
    hello()
    const hb = setInterval(hello, 2000)
    ch.onmessage = (e: MessageEvent<DeskMsg>) => {
      const m = e.data
      if (m.type === 'link' && m.from !== `${deskName}:${id}`) setGroup(m.group, m.ticker, false)
      if (m.type === 'identify') { setFlash(true); setTimeout(() => setFlash(false), 2200) }
      if (m.type === 'close' && (!m.desk || m.desk === deskName)) window.close()
      if (m.type === 'config' && m.desk === deskName) setDesk(loadDesks('TSLA').desks[deskName] ?? null)
    }
    return () => { clearInterval(hb); ch.onmessage = null }
  }, [ch, id, deskName, display?.name, setGroup])
  useEffect(() => () => ch?.close(), [ch])

  // remember where this window lives (fallback placement when the screen API isn't available)
  useEffect(() => {
    const save = () => rememberGeometry(deskName, id)
    const iv = setInterval(save, 5000)
    window.addEventListener('beforeunload', save)
    return () => { clearInterval(iv); window.removeEventListener('beforeunload', save) }
  }, [deskName, id])

  // keyboard: ⌃1–4 focus a pane's command line, ⌃M maximise, ⌃I identify
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.ctrlKey) return
      if (/^[1-4]$/.test(e.key)) { e.preventDefault(); setActive(+e.key - 1) }
      if (e.key === 'm') { e.preventDefault(); setMaxPane((p) => (p === null ? active : null)) }
      if (e.key === 'i') { e.preventDefault(); ch?.postMessage({ type: 'identify' } satisfies DeskMsg); setFlash(true); setTimeout(() => setFlash(false), 2200) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, ch])

  useEffect(() => { document.title = `${id} · ${display?.name ?? 'Display'} · ${deskName} · Markets` }, [id, display?.name, deskName])

  if (!desk || !display) {
    return <div className="empty">Unknown display “{deskName} #{id}” — open the <a href="/desk">Desk controller</a>.</div>
  }
  const d = fitPanes(display)
  const tickerOf = (p: Pane) => (p.link === 'none' ? p.ticker || desk.groups.gold || 'TSLA' : desk.groups[p.link] || 'TSLA')

  return (
    <div className="dk">
      <div className="dk-bar">
        <span className="dk-id">{id}</span>
        <span style={{ fontWeight: 650 }}>{d.name}</span>
        <span className="dimmer" style={{ fontSize: 11 }}>{desk.name}</span>
        <span style={{ width: 10 }} />
        {(['gold', 'blue', 'violet', 'green'] as Link[]).map((g) => (
          <span key={g} className="dk-group mono" style={{ color: LINK_COLORS[g], borderColor: LINK_COLORS[g] }} title={`${g} link group`}>{desk.groups[g]}</span>
        ))}
        <span style={{ flex: 1 }} />
        <Clock />
        <select className="input ws-small" value={d.layout} onChange={(e) => updateDisplay((x) => fitPanes({ ...x, layout: e.target.value as DisplayT['layout'] }))} title="pane layout">
          <option value="1">1 pane</option><option value="2h">2 side by side</option><option value="2v">2 stacked</option><option value="3">3 panes</option><option value="4">4 panes</option>
        </select>
        <button className="chip" title="fullscreen this screen (⌃⌘F)" onClick={() => (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen())}>⛶</button>
        <button className="chip" title="flash display numbers on every screen (⌃I)" onClick={() => ch?.postMessage({ type: 'identify' } satisfies DeskMsg)}>identify</button>
      </div>
      <div className="dk-grid" style={GRID[d.layout]}>
        {d.panes.map((p, i) => (
          <PaneView key={p.id} pane={p} index={i} area={d.layout === '3' ? ['a', 'b', 'c'][i] : undefined} ticker={tickerOf(p)} active={active === i} onActivate={() => setActive(i)}
            maximized={maxPane === i} onMax={() => setMaxPane(maxPane === i ? null : i)}
            onLink={(l) => updateDisplay((x) => ({ ...x, panes: x.panes.map((q) => (q.id === p.id ? { ...q, link: l, ticker: l === 'none' ? tickerOf(p) : undefined } : q)) }))}
            onRoute={(fn, tk) => {
              updateDisplay((x) => ({ ...x, panes: x.panes.map((q) => (q.id === p.id ? { ...q, fn, ...(p.link === 'none' && tk ? { ticker: tk } : {}) } : q)) }))
              if (tk && p.link !== 'none' && tk !== desk.groups[p.link]) setGroup(p.link, tk)
            }}
            onCommand={(c) => {
              const r = parseCommand(c)
              if (r.error) return r.error
              if (!r.fn && !r.ticker) return null
              const fn = r.fn ?? (FUNCTIONS[p.fn]?.company || p.fn === 'RV' ? p.fn : 'DES')
              updateDisplay((x) => ({ ...x, panes: x.panes.map((q) => (q.id === p.id ? { ...q, fn, ...(p.link === 'none' && r.ticker ? { ticker: r.ticker } : {}) } : q)) }))
              if (r.ticker && p.link !== 'none') setGroup(p.link, r.ticker)
              return null
            }} />
        ))}
      </div>
      {flash && <div className="dk-flash"><div>{id}</div><span>{d.name}</span></div>}
    </div>
  )
}
