// Desk — multi-monitor terminal. A desk is a set of displays (one per physical monitor); each
// display is split into 1–4 panes; each pane runs one terminal function for one security.
// Panes join colour link groups that span every display: load a ticker in any gold pane on any
// screen and every gold pane everywhere follows, keeping its own function.
//
// Windows talk over BroadcastChannel('markets-desk'):
//   hello     {id, desk, at}                 display heartbeat (controller shows who's live)
//   link      {group, ticker, from}          a group's security changed
//   identify  {}                             flash the display number on every screen
//   close     {desk?}                        close display windows
//   config    {desk}                         a desk definition changed — displays re-read storage

export type Link = 'gold' | 'blue' | 'violet' | 'green' | 'none'
export type PaneLayout = '1' | '2h' | '2v' | '3' | '4'

export interface Pane { id: string; fn: string; link: Link; ticker?: string }
export interface Display { id: number; name: string; layout: PaneLayout; panes: Pane[]; screen?: string }
export interface Desk { name: string; displays: Display[]; groups: Record<string, string> }

export const LINK_COLORS: Record<Link, string> = { gold: '#d4af37', blue: '#5aa9ff', violet: '#a68bff', green: '#2fbf71', none: '#5b6473' }
export const LINKS: Link[] = ['gold', 'blue', 'violet', 'green', 'none']
export const PANES_FOR: Record<PaneLayout, number> = { '1': 1, '2h': 2, '2v': 2, '3': 3, '4': 4 }

// Bloomberg-flavoured mnemonics → app routes. {T} is the pane's security.
export const FUNCTIONS: Record<string, { label: string; path: string; company: boolean; aliases?: string[] }> = {
  DES: { label: 'Overview', path: '/c/{T}/overview', company: true, aliases: ['GP', 'Q', 'OV'] },
  FA: { label: 'Financials', path: '/c/{T}/financials', company: true, aliases: ['FIN'] },
  SEG: { label: 'Segments', path: '/c/{T}/segments', company: true, aliases: ['BRK'] },
  ERN: { label: 'Earnings', path: '/c/{T}/earnings', company: true, aliases: ['EE', 'EA'] },
  CF: { label: 'Filings', path: '/c/{T}/filings', company: true, aliases: ['FIL', 'SEC'] },
  SRCH: { label: 'Search filings', path: '/c/{T}/search', company: true, aliases: ['FTS'] },
  MGMT: { label: 'People & insiders', path: '/c/{T}/people', company: true, aliases: ['INS', 'PPL'] },
  HDS: { label: 'Ownership', path: '/c/{T}/ownership', company: true, aliases: ['OWN', 'SI'] },
  N: { label: 'News', path: '/c/{T}/news', company: true, aliases: ['CN', 'NEWS'] },
  CMP: { label: '10-K compare', path: '/c/{T}/compare', company: true, aliases: ['DIFF'] },
  JRN: { label: 'Journal', path: '/c/{T}/journal', company: true, aliases: ['NOTE'] },
  WL: { label: 'Watchlist', path: '/', company: false, aliases: ['W', 'MON'] },
  RV: { label: 'Compare peers', path: '/peers?t={T}', company: false, aliases: ['COMP', 'PEER'] },
  EQS: { label: 'Screener', path: '/screener', company: false, aliases: ['SCR'] },
  ECO: { label: 'Macro', path: '/macro', company: false, aliases: ['MACRO', 'WECO'] },
  WS: { label: 'Widget workspace', path: '/workspace', company: false },
}

const ALIAS: Record<string, string> = Object.fromEntries(
  Object.entries(FUNCTIONS).flatMap(([k, f]) => [[k, k], ...(f.aliases ?? []).map((a) => [a, k])]))

export function pathFor(fn: string, ticker: string): string {
  const f = FUNCTIONS[fn] ?? FUNCTIONS.DES
  return f.path.replace('{T}', encodeURIComponent(ticker))
}

/** Inverse of pathFor: which function + ticker is a route showing? */
export function parsePath(path: string): { fn: string; ticker: string | null } {
  const m = path.match(/^\/c\/([^/?#]+)\/([a-z]+)/)
  if (m) {
    const fn = Object.entries(FUNCTIONS).find(([, f]) => f.path.endsWith('/' + m[2]))?.[0] ?? 'DES'
    return { fn, ticker: decodeURIComponent(m[1]).toUpperCase() }
  }
  const base = path.split('?')[0]
  const fn = Object.entries(FUNCTIONS).find(([, f]) => !f.company && f.path.split('?')[0] === base)?.[0] ?? 'WL'
  const t = new URLSearchParams(path.split('?')[1] ?? '').get('t')
  return { fn, ticker: t ? t.split(',')[0].toUpperCase() : null }
}

/** "TSLA ERN", "ERN", "nvda", "GM FA" → {ticker?, fn?}. Trailing GO / <GO> is ignored. */
export function parseCommand(input: string): { ticker?: string; fn?: string; error?: string } {
  const words = input.toUpperCase().replace(/<?GO>?$/, '').replace(/\bEQUITY\b|\bUS\b/g, '').trim().split(/\s+/).filter(Boolean)
  if (!words.length) return {}
  const out: { ticker?: string; fn?: string } = {}
  for (const w of words) {
    if (ALIAS[w] && !out.fn) out.fn = ALIAS[w]
    else if (/^[A-Z][A-Z0-9.\-]{0,9}$/.test(w) && !out.ticker) out.ticker = w
    else return { error: `don't understand “${w}”` }
  }
  return out
}

let _n = 0
export const uid = () => `p${Date.now().toString(36)}${(_n++).toString(36)}`
const pane = (fn: string, link: Link = 'gold', ticker?: string): Pane => ({ id: uid(), fn, link, ticker })

export const PRESET_DESKS: Record<string, (t: string) => Desk> = {
  '4-screen trader': (t) => ({
    name: '4-screen trader', groups: { gold: t, blue: t === 'GM' ? 'F' : 'GM', violet: t, green: t },
    displays: [
      { id: 1, name: 'Security', layout: '1', panes: [pane('DES')] },
      { id: 2, name: 'Fundamentals', layout: '2h', panes: [pane('FA'), pane('ERN')] },
      { id: 3, name: 'Documents', layout: '2h', panes: [pane('CF'), pane('N')] },
      { id: 4, name: 'Market', layout: '4', panes: [pane('WL', 'gold'), pane('ECO', 'none'), pane('EQS', 'none'), pane('HDS')] },
    ],
  }),
  '2-screen analyst': (t) => ({
    name: '2-screen analyst', groups: { gold: t, blue: t, violet: t, green: t },
    displays: [
      { id: 1, name: 'Numbers', layout: '2h', panes: [pane('DES'), pane('FA')] },
      { id: 2, name: 'Words', layout: '2h', panes: [pane('CF'), pane('ERN')] },
    ],
  }),
  '1 screen · 4 panels': (t) => ({
    name: '1 screen · 4 panels', groups: { gold: t, blue: t === 'GM' ? 'F' : 'GM', violet: t, green: t },
    displays: [{ id: 1, name: 'Launchpad', layout: '4', panes: [pane('DES', 'gold'), pane('DES', 'blue'), pane('ERN', 'gold'), pane('ERN', 'blue')] }],
  }),
}

const KEY = 'markets:desks'
export interface DeskStore { current: string; desks: Record<string, Desk> }

export function loadDesks(t: string): DeskStore {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || 'null') as DeskStore | null
    if (s?.desks?.[s.current]) return s
  } catch { /* fall through */ }
  const desks = Object.fromEntries(Object.entries(PRESET_DESKS).map(([k, f]) => [k, f(t)]))
  return { current: '4-screen trader', desks }
}

export function saveDesks(s: DeskStore) {
  try { localStorage.setItem(KEY, JSON.stringify(s)) } catch { /* private mode */ }
}

/** Keep a display's pane list in step with its layout. */
export function fitPanes(d: Display): Display {
  const n = PANES_FOR[d.layout]
  const panes = d.panes.slice(0, n)
  while (panes.length < n) panes.push(pane(['DES', 'FA', 'ERN', 'N'][panes.length] ?? 'DES'))
  return { ...d, panes }
}

// ------------------------------------------------------------------ cross-window channel
export type DeskMsg =
  | { type: 'hello'; id: number; desk: string; at: number; title?: string }
  | { type: 'link'; group: string; ticker: string; from: string }
  | { type: 'identify' }
  | { type: 'close'; desk?: string }
  | { type: 'config'; desk: string }

export function channel(): BroadcastChannel | null {
  return typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('markets-desk')
}

// Per-display window geometry, remembered for browsers without the Window Management API.
export function rememberGeometry(desk: string, id: number) {
  try {
    localStorage.setItem(`markets:geom:${desk}:${id}`, JSON.stringify({ left: window.screenX, top: window.screenY, width: window.outerWidth, height: window.outerHeight }))
  } catch { /* ignore */ }
}
export function savedGeometry(desk: string, id: number): { left: number; top: number; width: number; height: number } | null {
  try { return JSON.parse(localStorage.getItem(`markets:geom:${desk}:${id}`) || 'null') } catch { return null }
}
