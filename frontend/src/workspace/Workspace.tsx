// Workspace — a Bloomberg-style launchpad: a 12-column snapping grid of panels, each a widget.
// Panels join a colour link group; changing the ticker in any panel of a group moves the whole
// group. Groups sync across windows (pop-outs on a second monitor) via BroadcastChannel.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { tokens } from '../ui'
import { WIDGETS, type WidgetKind, ChartW, StatsW, FundamentalsW, SegmentsW, EarningsW, InsidersW, FilingsW, NewsW, EventsW, MacroW, WatchlistW } from './widgets'

export type Link = 'gold' | 'blue' | 'violet' | 'green' | 'none'
export interface PanelCfg { id: string; kind: WidgetKind; x: number; y: number; w: number; h: number; link: Link; ticker?: string; series?: string }
export interface Layout { panels: PanelCfg[]; groups: Record<string, string> }
interface Store { current: string; layouts: Record<string, Layout> }

const COLS = 12
const ROW = 44
const GAP = 8
const LINKS: Link[] = ['gold', 'blue', 'violet', 'green', 'none']
const KEY = 'markets:workspace'
const CHANNEL = 'markets-link'

let _n = 0
const uid = () => `p${Date.now().toString(36)}${(_n++).toString(36)}`

export const PRESETS: Record<string, (t: string) => Layout> = {
  Research: (t) => ({
    groups: { gold: t, blue: t === 'GM' ? 'F' : 'GM', violet: t, green: t },
    panels: [
      { id: uid(), kind: 'chart', x: 0, y: 0, w: 8, h: 9, link: 'gold' },
      { id: uid(), kind: 'stats', x: 8, y: 0, w: 4, h: 9, link: 'gold' },
      { id: uid(), kind: 'fundamentals', x: 0, y: 9, w: 4, h: 7, link: 'gold' },
      { id: uid(), kind: 'segments', x: 4, y: 9, w: 4, h: 7, link: 'gold' },
      { id: uid(), kind: 'earnings', x: 8, y: 9, w: 4, h: 7, link: 'gold' },
      { id: uid(), kind: 'events', x: 0, y: 16, w: 4, h: 7, link: 'gold' },
      { id: uid(), kind: 'insiders', x: 4, y: 16, w: 4, h: 7, link: 'gold' },
      { id: uid(), kind: 'news', x: 8, y: 16, w: 4, h: 7, link: 'gold' },
    ],
  }),
  'Head to head': (t) => ({
    groups: { gold: t, blue: t === 'GM' ? 'F' : 'GM', violet: t, green: t },
    panels: [
      { id: uid(), kind: 'chart', x: 0, y: 0, w: 6, h: 8, link: 'gold' },
      { id: uid(), kind: 'chart', x: 6, y: 0, w: 6, h: 8, link: 'blue' },
      { id: uid(), kind: 'stats', x: 0, y: 8, w: 3, h: 9, link: 'gold' },
      { id: uid(), kind: 'fundamentals', x: 3, y: 8, w: 3, h: 9, link: 'gold' },
      { id: uid(), kind: 'stats', x: 6, y: 8, w: 3, h: 9, link: 'blue' },
      { id: uid(), kind: 'fundamentals', x: 9, y: 8, w: 3, h: 9, link: 'blue' },
    ],
  }),
  'Market desk': (t) => ({
    groups: { gold: t, blue: t, violet: t, green: t },
    panels: [
      { id: uid(), kind: 'watchlist', x: 0, y: 0, w: 3, h: 14, link: 'gold' },
      { id: uid(), kind: 'chart', x: 3, y: 0, w: 6, h: 9, link: 'gold' },
      { id: uid(), kind: 'stats', x: 9, y: 0, w: 3, h: 9, link: 'gold' },
      { id: uid(), kind: 'macro', x: 3, y: 9, w: 3, h: 5, link: 'none', series: 'DGS10' },
      { id: uid(), kind: 'macro', x: 6, y: 9, w: 3, h: 5, link: 'none', series: 'VIXCLS' },
      { id: uid(), kind: 'macro', x: 9, y: 9, w: 3, h: 5, link: 'none', series: 'T10Y2Y' },
      { id: uid(), kind: 'events', x: 0, y: 14, w: 6, h: 7, link: 'gold' },
      { id: uid(), kind: 'news', x: 6, y: 14, w: 6, h: 7, link: 'gold' },
    ],
  }),
}

function load(t: string): Store {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || 'null') as Store | null
    if (s && s.layouts && s.layouts[s.current]) return s
  } catch { /* fall through */ }
  return { current: 'Research', layouts: Object.fromEntries(Object.entries(PRESETS).map(([k, f]) => [k, f(t)])) }
}

export function renderWidget(p: Pick<PanelCfg, 'kind' | 'series'>, t: string, onPick: (t: string) => void) {
  switch (p.kind) {
    case 'chart': return <ChartW t={t} />
    case 'stats': return <StatsW t={t} />
    case 'fundamentals': return <FundamentalsW t={t} />
    case 'segments': return <SegmentsW t={t} />
    case 'earnings': return <EarningsW t={t} />
    case 'insiders': return <InsidersW t={t} />
    case 'filings': return <FilingsW t={t} />
    case 'news': return <NewsW t={t} />
    case 'events': return <EventsW t={t} />
    case 'macro': return <MacroW series={p.series || 'DGS10'} />
    case 'watchlist': return <WatchlistW onPick={onPick} />
  }
}

export function TickerBox({ value, color, onSet }: { value: string; color: string; onSet: (t: string) => void }) {
  const [v, setV] = useState(value)
  useEffect(() => setV(value), [value])
  return (
    <input className="ws-ticker mono" value={v} spellCheck={false} style={{ borderColor: color, color }}
      onChange={(e) => setV(e.target.value.toUpperCase())} onFocus={(e) => e.target.select()}
      onKeyDown={(e) => { if (e.key === 'Enter') { onSet(v.trim()); (e.target as HTMLInputElement).blur() } if (e.key === 'Escape') setV(value) }}
      onBlur={() => setV(value)} title="type a ticker, Enter — every panel in this colour follows" />
  )
}

export function useLinkChannel(onMsg: (group: string, ticker: string) => void) {
  const ch = useRef<BroadcastChannel | null>(null)
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return
    ch.current = new BroadcastChannel(CHANNEL)
    ch.current.onmessage = (e) => { const { group, ticker } = e.data || {}; if (group && ticker) onMsg(group, ticker) }
    return () => ch.current?.close()
  }, [onMsg])
  return useCallback((group: string, ticker: string) => ch.current?.postMessage({ group, ticker }), [])
}

export default function Workspace({ t }: { t: string }) {
  const [sp] = useSearchParams()
  const [store, setStore] = useState<Store>(() => load(sp.get('t') || t))
  const layout = store.layouts[store.current]
  const wrap = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(1200)
  const [drag, setDrag] = useState<{ id: string; mode: 'move' | 'size'; sx: number; sy: number; orig: PanelCfg } | null>(null)
  const [adding, setAdding] = useState(false)
  const [focus, setFocus] = useState<string | null>(null)

  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(store)) } catch { /* private mode */ } }, [store])
  useEffect(() => {
    if (!wrap.current) return
    const ro = new ResizeObserver((e) => setWidth(e[0].contentRect.width))
    ro.observe(wrap.current)
    return () => ro.disconnect()
  }, [])

  const update = useCallback((fn: (l: Layout) => Layout) => setStore((s) => ({ ...s, layouts: { ...s.layouts, [s.current]: fn(s.layouts[s.current]) } })), [])
  const setGroupLocal = useCallback((g: string, tk: string) => update((l) => ({ ...l, groups: { ...l.groups, [g]: tk } })), [update])
  const broadcast = useLinkChannel(setGroupLocal)
  const setGroup = (g: string, tk: string) => { if (!tk) return; setGroupLocal(g, tk); broadcast(g, tk) }
  const setPanel = (id: string, patch: Partial<PanelCfg>) => update((l) => ({ ...l, panels: l.panels.map((p) => (p.id === id ? { ...p, ...patch } : p)) }))
  const tickerOf = (p: PanelCfg) => (p.link === 'none' ? p.ticker || layout.groups.gold || t : layout.groups[p.link] || t)

  const colW = (width - GAP * (COLS - 1)) / COLS
  const onMove = useCallback((e: PointerEvent) => {
    if (!drag) return
    const dx = Math.round((e.clientX - drag.sx) / (colW + GAP)), dy = Math.round((e.clientY - drag.sy) / (ROW + GAP))
    const o = drag.orig
    if (drag.mode === 'move') setPanel(o.id, { x: Math.max(0, Math.min(COLS - o.w, o.x + dx)), y: Math.max(0, o.y + dy) })
    else setPanel(o.id, { w: Math.max(2, Math.min(COLS - o.x, o.w + dx)), h: Math.max(3, o.h + dy) })
  }, [drag, colW]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!drag) return
    const up = () => setDrag(null)
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', up)
    return () => { window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', up) }
  }, [drag, onMove])

  const rows = Math.max(...layout.panels.map((p) => p.y + p.h), 12)
  const addPanel = (kind: WidgetKind) => {
    const d = WIDGETS[kind]
    update((l) => ({ ...l, panels: [...l.panels, { id: uid(), kind, x: 0, y: rows, w: d.w, h: d.h, link: d.linked ? 'gold' : 'none', series: kind === 'macro' ? 'DGS10' : undefined }] }))
    setAdding(false)
  }
  const popOut = (p: PanelCfg) => {
    const q = new URLSearchParams({ w: p.kind, link: p.link, t: tickerOf(p), ...(p.series ? { series: p.series } : {}) })
    window.open(`/popout?${q}`, `markets-${p.id}`, `width=${Math.round(p.w * 110)},height=${Math.round(p.h * 60 + 60)}`)
  }
  const layoutNames = Object.keys(store.layouts)

  return (
    <div className="ws">
      <div className="ws-bar">
        <span className="ws-title">WORKSPACE</span>
        <select className="input" value={store.current} onChange={(e) => setStore({ ...store, current: e.target.value })}>
          {layoutNames.map((n) => <option key={n}>{n}</option>)}
        </select>
        <button className="chip" onClick={() => {
          const name = prompt('Save current layout as…', store.current + ' copy')
          if (name) setStore({ current: name, layouts: { ...store.layouts, [name]: JSON.parse(JSON.stringify(layout)) } })
        }}>save as</button>
        <button className="chip" onClick={() => {
          const base = PRESETS[store.current]
          if (base && confirm(`Reset “${store.current}” to its default arrangement?`)) update(() => base(layout.groups.gold || t))
          else if (!base && confirm(`Delete layout “${store.current}”?`)) {
            const { [store.current]: _gone, ...rest } = store.layouts
            setStore({ current: Object.keys(rest)[0], layouts: rest })
          }
        }}>{PRESETS[store.current] ? 'reset' : 'delete'}</button>
        <span style={{ width: 14 }} />
        {(['gold', 'blue', 'violet', 'green'] as Link[]).map((g) => (
          <span key={g} className="ws-group"><span className="ws-dot" style={{ background: tokens.link[g] }} />
            <TickerBox value={layout.groups[g] || t} color={tokens.link[g]} onSet={(tk) => setGroup(g, tk)} />
          </span>
        ))}
        <span style={{ flex: 1 }} />
        <div style={{ position: 'relative' }}>
          <button className="chip on" onClick={() => setAdding(!adding)}>+ panel</button>
          {adding && (
            <div className="ws-menu">
              {(Object.keys(WIDGETS) as WidgetKind[]).map((k) => (
                <div key={k} className="opt" onClick={() => addPanel(k)}><span style={{ width: 16 }}>{WIDGETS[k].icon}</span>{WIDGETS[k].label}</div>
              ))}
            </div>
          )}
        </div>
      </div>
      <div ref={wrap} className="ws-grid" style={{ height: rows * (ROW + GAP) }}>
        {layout.panels.map((p) => {
          const color = tokens.link[p.link]
          const tk = tickerOf(p)
          return (
            <div key={p.id} className={'ws-panel' + (drag?.id === p.id ? ' dragging' : '')} onPointerDown={() => setFocus(p.id)}
              style={{ left: p.x * (colW + GAP), top: p.y * (ROW + GAP), width: p.w * colW + (p.w - 1) * GAP, height: p.h * ROW + (p.h - 1) * GAP,
                borderTopColor: color, zIndex: focus === p.id ? 5 : drag?.id === p.id ? 6 : 1 }}>
              <div className="ws-head" onPointerDown={(e) => {
                if ((e.target as HTMLElement).closest('input,select,button')) return
                e.preventDefault(); setDrag({ id: p.id, mode: 'move', sx: e.clientX, sy: e.clientY, orig: p })
              }}>
                <select className="ws-link" value={p.link} style={{ background: color }} title="link group"
                  onChange={(e) => setPanel(p.id, { link: e.target.value as Link, ticker: e.target.value === 'none' ? tk : undefined })}>
                  {LINKS.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
                {p.kind === 'macro'
                  ? <select className="input ws-small" value={p.series} onChange={(e) => setPanel(p.id, { series: e.target.value })}>
                      {['DGS10', 'DGS2', 'T10Y2Y', 'FEDFUNDS', 'BOE_BANK_RATE', 'CPIAUCSL', 'UNRATE', 'VIXCLS', 'DCOILWTICO', 'DTWEXBGS', 'DEXUSUK'].map((s) => <option key={s}>{s}</option>)}
                    </select>
                  : WIDGETS[p.kind].linked && <TickerBox value={tk} color={color} onSet={(v) => (p.link === 'none' ? setPanel(p.id, { ticker: v }) : setGroup(p.link, v))} />}
                <select className="ws-kind" value={p.kind} onChange={(e) => setPanel(p.id, { kind: e.target.value as WidgetKind })}>
                  {(Object.keys(WIDGETS) as WidgetKind[]).map((k) => <option key={k} value={k}>{WIDGETS[k].label}</option>)}
                </select>
                <span style={{ flex: 1 }} />
                <button className="ws-btn" title="pop out (second monitor) — stays linked" onClick={() => popOut(p)}>⧉</button>
                <button className="ws-btn" title="close panel" onClick={() => update((l) => ({ ...l, panels: l.panels.filter((x) => x.id !== p.id) }))}>✕</button>
              </div>
              <div className="ws-body">{renderWidget(p, tk, (v) => setGroup(p.link === 'none' ? 'gold' : p.link, v))}</div>
              <div className="ws-resize" onPointerDown={(e) => { e.preventDefault(); e.stopPropagation(); setDrag({ id: p.id, mode: 'size', sx: e.clientX, sy: e.clientY, orig: p }) }} />
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** A single widget in its own window (second monitor). Linked groups follow the main window. */
export function Popout() {
  const [sp] = useSearchParams()
  const kind = (sp.get('w') || 'chart') as WidgetKind
  const link = (sp.get('link') || 'gold') as Link
  const [tk, setTk] = useState(sp.get('t') || 'TSLA')
  const onMsg = useCallback((g: string, v: string) => { if (g === link) setTk(v) }, [link])
  const broadcast = useLinkChannel(onMsg)
  useEffect(() => { document.title = `${tk} · ${WIDGETS[kind]?.label} · Markets` }, [tk, kind])
  const color = tokens.link[link]
  const p = useMemo(() => ({ kind, series: sp.get('series') || undefined }), [kind, sp])
  return (
    <div className="ws-panel popout" style={{ borderTopColor: color }}>
      <div className="ws-head">
        <span className="ws-link" style={{ background: color, padding: '2px 8px' }}>{link}</span>
        {WIDGETS[kind].linked && <TickerBox value={tk} color={color} onSet={(v) => { setTk(v); if (link !== 'none') broadcast(link, v) }} />}
        <span className="dim">{WIDGETS[kind].label}</span>
      </div>
      <div className="ws-body">{renderWidget(p, tk, (v) => { setTk(v); broadcast(link, v) })}</div>
    </div>
  )
}
