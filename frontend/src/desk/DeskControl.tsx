// Desk controller — define desks (displays × panes × functions), detect monitors, launch each
// display onto its own screen, and run the desk: who's live, identify, load a security
// everywhere, close all.
import { useEffect, useMemo, useState } from 'react'
import {
  type Desk, type DeskMsg, type Display, type Link, FUNCTIONS, LINKS, LINK_COLORS, PRESET_DESKS,
  channel, fitPanes, loadDesks, savedGeometry, saveDesks,
} from './model'
import { Panel, PageTitle } from '../ui'

interface ScreenInfo { label: string; left: number; top: number; width: number; height: number; primary: boolean }
type ScreenDetails = { screens: { label?: string; availLeft: number; availTop: number; availWidth: number; availHeight: number; isPrimary?: boolean }[] }

const LAYOUT_LABEL: Record<string, string> = { '1': '1 pane', '2h': '2 · side by side', '2v': '2 · stacked', '3': '3 panes', '4': '4 panes' }

function MiniLayout({ d }: { d: Display }) {
  const g = { '1': '1fr/1fr', '2h': '1fr/1fr 1fr', '2v': '1fr 1fr/1fr', '3': '1fr 1fr/1.4fr 1fr', '4': '1fr 1fr/1fr 1fr' }[d.layout]
  return (
    <div style={{ display: 'grid', gridTemplate: g, gridTemplateAreas: d.layout === '3' ? '"a b" "a c"' : undefined, gap: 3, width: 150, height: 86,
      background: '#05070a', border: '2px solid var(--line-2)', borderRadius: 6, padding: 3 }}>
      {fitPanes(d).panes.map((p, i) => (
        <div key={p.id} style={{ gridArea: d.layout === '3' ? ['a', 'b', 'c'][i] : undefined, background: 'var(--bg-2)', borderTop: `2px solid ${LINK_COLORS[p.link]}`,
          borderRadius: 2, display: 'grid', placeItems: 'center', font: '700 10px var(--mono)', color: 'var(--text-2)' }}>{p.fn}</div>
      ))}
    </div>
  )
}

export default function DeskControl({ t }: { t: string }) {
  const [store, setStore] = useState(() => loadDesks(t))
  const desk = store.desks[store.current]
  const [screens, setScreens] = useState<ScreenInfo[] | null>(null)
  const [screenErr, setScreenErr] = useState<string | null>(null)
  const [live, setLive] = useState<Record<string, number>>({})
  const [loadT, setLoadT] = useState('')
  const [blocked, setBlocked] = useState<number[]>([])
  const ch = useMemo(() => channel(), [])
  const [, tick] = useState(0)

  useEffect(() => { saveDesks(store) }, [store])
  useEffect(() => {
    if (!ch) return
    ch.onmessage = (e: MessageEvent<DeskMsg>) => {
      const m = e.data
      if (m.type === 'hello') setLive((l) => ({ ...l, [`${m.desk}:${m.id}`]: m.at }))
      if (m.type === 'link') setStore((s) => {
        const dk = s.desks[s.current]
        return dk && dk.groups[m.group] !== m.ticker ? { ...s, desks: { ...s.desks, [s.current]: { ...dk, groups: { ...dk.groups, [m.group]: m.ticker } } } } : s
      })
    }
    const iv = setInterval(() => tick((x) => x + 1), 1500)
    return () => { clearInterval(iv); ch.close() }
  }, [ch])

  const update = (fn: (d: Desk) => Desk, notify = true) => {
    setStore((s) => {
      const next = fn(s.desks[s.current])
      const out = { ...s, desks: { ...s.desks, [s.current]: next } }
      saveDesks(out)
      return out
    })
    if (notify) setTimeout(() => ch?.postMessage({ type: 'config', desk: desk.name } satisfies DeskMsg), 50)
  }
  const updDisplay = (id: number, fn: (d: Display) => Display) => update((dk) => ({ ...dk, displays: dk.displays.map((d) => (d.id === id ? fn(d) : d)) }))
  const isLive = (id: number) => Date.now() - (live[`${desk.name}:${id}`] ?? 0) < 5000

  async function detect() {
    setScreenErr(null)
    const w = window as unknown as { getScreenDetails?: () => Promise<ScreenDetails> }
    if (!w.getScreenDetails) {
      setScreenErr('This browser has no Window Management API (Chrome/Edge do). Displays will open where you last left them — drag each to its monitor once and it is remembered.')
      const sc = window.screen as Screen & { availLeft?: number; availTop?: number }
      setScreens([{ label: 'This screen', left: sc.availLeft ?? 0, top: sc.availTop ?? 0, width: sc.availWidth, height: sc.availHeight, primary: true }])
      return
    }
    try {
      const sd = await w.getScreenDetails()
      setScreens(sd.screens.map((s, i) => ({ label: s.label || `Screen ${i + 1}`, left: s.availLeft, top: s.availTop, width: s.availWidth, height: s.availHeight, primary: !!s.isPrimary })))
    } catch (e) {
      setScreenErr(`Screen access was refused (${(e as Error).message}). Allow “Window management” for this site in the address-bar settings.`)
    }
  }

  function geometryFor(d: Display, i: number) {
    const sc = screens?.find((s) => s.label === d.screen) ?? (screens && screens.length > 1 ? screens[i % screens.length] : null)
    if (sc) return { left: sc.left, top: sc.top, width: sc.width, height: sc.height }
    return savedGeometry(desk.name, d.id) ?? { left: 40 + i * 60, top: 40 + i * 40, width: Math.round(window.screen.availWidth * 0.8), height: Math.round(window.screen.availHeight * 0.85) }
  }

  function open(d: Display, i: number): boolean {
    const g = geometryFor(d, i)
    const w = window.open(`/display?desk=${encodeURIComponent(desk.name)}&id=${d.id}`, `markets-${desk.name}-${d.id}`,
      `popup,left=${g.left},top=${g.top},width=${g.width},height=${g.height}`)
    return !!w
  }

  function launchAll() {
    const failed: number[] = []
    desk.displays.forEach((d, i) => { if (!open(d, i)) failed.push(d.id) })
    setBlocked(failed)
  }

  const names = Object.keys(store.desks)
  return (
    <div className="grid">
      <PageTitle title="Desk" sub="Multi-monitor terminal — one window per screen, every screen split into panes, securities linked across all of them" />

      <Panel title="Run" right={<span>{desk.displays.filter((d) => isLive(d.id)).length} / {desk.displays.length} displays live</span>}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <select className="input" value={store.current} onChange={(e) => setStore({ ...store, current: e.target.value })}>{names.map((n) => <option key={n}>{n}</option>)}</select>
          <button className="chip on" style={{ fontSize: 13, padding: '6px 16px' }} onClick={launchAll}>▶ Launch desk</button>
          <button className="chip" onClick={() => ch?.postMessage({ type: 'identify' } satisfies DeskMsg)}>Identify screens</button>
          <button className="chip" onClick={() => ch?.postMessage({ type: 'close', desk: desk.name } satisfies DeskMsg)}>Close all</button>
          <span style={{ width: 16 }} />
          <form style={{ display: 'flex', gap: 6 }} onSubmit={(e) => {
            e.preventDefault()
            const [tk, grp = 'gold'] = loadT.trim().toUpperCase().split(/\s+/)
            if (!tk) return
            const g = grp.toLowerCase()
            ch?.postMessage({ type: 'link', group: g, ticker: tk, from: 'controller' } satisfies DeskMsg)
            update((dk) => ({ ...dk, groups: { ...dk.groups, [g]: tk } }), false)
            setLoadT('')
          }}>
            <input className="input mono" placeholder="NVDA  (or: NVDA blue)" value={loadT} onChange={(e) => setLoadT(e.target.value)} style={{ width: 200 }} />
            <button className="chip" type="submit">load everywhere</button>
          </form>
          <span style={{ flex: 1 }} />
          {(['gold', 'blue', 'violet', 'green'] as Link[]).map((g) => (
            <span key={g} className="dk-group mono" style={{ color: LINK_COLORS[g], borderColor: LINK_COLORS[g] }}>{desk.groups[g]}</span>
          ))}
        </div>
        {blocked.length > 0 && (
          <div style={{ marginTop: 10, fontSize: 12 }} className="gold">
            The browser blocked {blocked.length} window{blocked.length > 1 ? 's' : ''} (pop-up blocker allows one per click without “Window management” permission).
            Open the rest one by one: {blocked.map((id) => <button key={id} className="chip" style={{ marginLeft: 6 }}
              onClick={() => { const i = desk.displays.findIndex((d) => d.id === id); if (open(desk.displays[i], i)) setBlocked(blocked.filter((b) => b !== id)) }}>display {id}</button>)}
          </div>
        )}
      </Panel>

      <Panel title="Monitors" right={<button className="chip" onClick={detect}>{screens ? 're-detect' : 'detect monitors'}</button>}>
        {screens ? (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            {screens.map((s) => (
              <div key={s.label} style={{ border: '1px solid var(--line-2)', borderRadius: 8, padding: 10, width: Math.max(140, s.width / 14), height: Math.max(80, s.height / 14), display: 'flex', flexDirection: 'column', justifyContent: 'space-between', background: 'var(--bg-2)' }}>
                <span style={{ fontWeight: 600 }}>{s.label}{s.primary ? <span className="gold"> · primary</span> : ''}</span>
                <span className="mono dimmer" style={{ fontSize: 11 }}>{s.width}×{s.height} @ {s.left},{s.top}</span>
              </div>
            ))}
          </div>
        ) : <div className="dimmer">Detect your monitors to pin each display to a screen. Without it, displays open where you last placed them.</div>}
        {screenErr && <div className="dimmer" style={{ marginTop: 8, fontSize: 12 }}>{screenErr}</div>}
      </Panel>

      <Panel title={`Displays · ${desk.name}`} right={
        <span style={{ display: 'flex', gap: 6 }}>
          <button className="chip" onClick={() => update((dk) => ({ ...dk, displays: [...dk.displays, fitPanes({ id: Math.max(0, ...dk.displays.map((d) => d.id)) + 1, name: `Display ${dk.displays.length + 1}`, layout: '1', panes: [] })] }))}>+ display</button>
          <button className="chip" onClick={() => {
            const n = prompt('Save this desk as…', desk.name + ' copy')
            if (n) setStore({ current: n, desks: { ...store.desks, [n]: { ...JSON.parse(JSON.stringify(desk)), name: n } } })
          }}>save as</button>
          {PRESET_DESKS[desk.name]
            ? <button className="chip" onClick={() => confirm(`Reset “${desk.name}”?`) && update(() => PRESET_DESKS[desk.name](desk.groups.gold || t))}>reset</button>
            : <button className="chip" onClick={() => { if (confirm(`Delete “${desk.name}”?`)) { const { [desk.name]: _d, ...rest } = store.desks; setStore({ current: Object.keys(rest)[0], desks: rest }) } }}>delete</button>}
        </span>}>
        <div style={{ display: 'grid', gap: 12 }}>
          {desk.displays.map((d, i) => (
            <div key={d.id} className="dk-row">
              <div style={{ display: 'grid', gap: 6, justifyItems: 'center' }}>
                <span className="dk-id" style={{ fontSize: 18, width: 34, height: 34 }}>{d.id}</span>
                <span className={isLive(d.id) ? 'up mono' : 'dimmer mono'} style={{ fontSize: 10 }}>{isLive(d.id) ? '● live' : '○ off'}</span>
              </div>
              <MiniLayout d={d} />
              <div style={{ display: 'grid', gap: 8, flex: 1 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <input className="input" value={d.name} onChange={(e) => updDisplay(d.id, (x) => ({ ...x, name: e.target.value }))} style={{ width: 160 }} />
                  <select className="input" value={d.layout} onChange={(e) => updDisplay(d.id, (x) => fitPanes({ ...x, layout: e.target.value as Display['layout'] }))}>
                    {Object.entries(LAYOUT_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                  <select className="input" value={d.screen ?? ''} onChange={(e) => updDisplay(d.id, (x) => ({ ...x, screen: e.target.value || undefined }))} disabled={!screens}>
                    <option value="">{screens ? 'auto screen' : 'screen: detect first'}</option>
                    {screens?.map((s) => <option key={s.label} value={s.label}>{s.label}</option>)}
                  </select>
                  <button className="chip" onClick={() => open(d, i)}>open</button>
                  {desk.displays.length > 1 && <button className="chip" onClick={() => update((dk) => ({ ...dk, displays: dk.displays.filter((x) => x.id !== d.id) }))}>remove</button>}
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {fitPanes(d).panes.map((p, j) => (
                    <span key={p.id} className="dk-pcfg" style={{ borderTopColor: LINK_COLORS[p.link] }}>
                      <span className="dimmer mono" style={{ fontSize: 10 }}>{j + 1}</span>
                      <select className="input ws-small" value={p.fn} onChange={(e) => updDisplay(d.id, (x) => ({ ...fitPanes(x), panes: fitPanes(x).panes.map((q) => (q.id === p.id ? { ...q, fn: e.target.value } : q)) }))}>
                        {Object.entries(FUNCTIONS).map(([k, f]) => <option key={k} value={k}>{k} · {f.label}</option>)}
                      </select>
                      <select className="input ws-small" value={p.link} style={{ color: LINK_COLORS[p.link] }} onChange={(e) => updDisplay(d.id, (x) => ({ ...fitPanes(x), panes: fitPanes(x).panes.map((q) => (q.id === p.id ? { ...q, link: e.target.value as Link } : q)) }))}>
                        {LINKS.map((l) => <option key={l} value={l}>{l}</option>)}
                      </select>
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="How it works">
        <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 18 }}>
          <ul className="dim" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
            <li><b>Launch desk</b> opens one window per display, placed on its monitor (Chrome/Edge: allow “Window management” once).</li>
            <li>Each pane runs the full terminal. Type in its command line: <code>NVDA ERN</code>, <code>FA</code>, <code>GM</code> — then Enter.</li>
            <li><b>Link colours span every screen.</b> Change the security in any gold pane and every gold pane on every monitor follows, each keeping its function. <i>none</i> panes stay put.</li>
            <li>Click through inside a pane (a filing, a peer) and the pane follows; open a different company and its link group moves with it.</li>
            <li>In a display: <code>⌃1–4</code> pane command line · <code>⌃M</code> maximise pane · <code>⌃I</code> identify · ⛶ fullscreen that monitor.</li>
          </ul>
          <div>
            <div className="dimmer" style={{ fontSize: 11, marginBottom: 6 }}>FUNCTIONS</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '4px 16px' }}>
              {Object.entries(FUNCTIONS).map(([k, f]) => (
                <span key={k} style={{ fontSize: 12 }}><span className="mono gold" style={{ display: 'inline-block', width: 44 }}>{k}</span>{f.label}
                  {f.aliases?.length ? <span className="dimmer mono" style={{ fontSize: 10 }}> {f.aliases.join(' ')}</span> : null}</span>
              ))}
            </div>
          </div>
        </div>
      </Panel>
    </div>
  )
}

