import { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, NavLink, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import type { Overview as OverviewT } from './api'
import { useApi } from './hooks'
import { pct, price, tone } from './format'
import Overview from './pages/Overview'
import Financials from './pages/Financials'
import Filings from './pages/Filings'
import Search from './pages/Search'
import People from './pages/People'
import Ownership from './pages/Ownership'
import News from './pages/News'
import Compare from './pages/Compare'
import Journal from './pages/Journal'

const NAV = [
  { to: 'overview', label: 'Overview', key: 'o', icon: '◉' },
  { to: 'financials', label: 'Financials', key: 'f', icon: '▤' },
  { to: 'filings', label: 'Filings', key: 'l', icon: '▦' },
  { to: 'search', label: 'Search', key: 's', icon: '⌕' },
  { to: 'people', label: 'People', key: 'p', icon: '◎' },
  { to: 'ownership', label: 'Ownership', key: 'w', icon: '◔' },
  { to: 'news', label: 'News', key: 'n', icon: '≋' },
  { to: 'compare', label: '10-K compare', key: 'c', icon: '⇄' },
]
const MINE = [{ to: 'journal', label: 'Journal', key: 'j', icon: '✎' }]

function Brand() {
  return (
    <div className="brand">
      <svg width="20" height="20" viewBox="0 0 32 32"><path d="M4 23 L11 14 L17 19 L28 7" fill="none" stroke="#d4af37" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" /><circle cx="28" cy="7" r="2.6" fill="#d4af37" /></svg>
      MARKETS
    </div>
  )
}

function Palette({ ticker, onClose }: { ticker: string; onClose: () => void }) {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [i, setI] = useState(0)
  const { data: companies } = useApi<{ ticker: string; name: string }[]>('companies')
  const opts = useMemo(() => {
    const base: { label: string; hint: string; go: () => void }[] = [
      ...[...NAV, ...MINE].map((n) => ({ label: n.label, hint: 'g ' + n.key, go: () => nav(`/c/${ticker}/${n.to}`) })),
      ...(companies ?? []).map((c) => ({ label: `${c.ticker} — ${c.name}`, hint: 'company', go: () => nav(`/c/${c.ticker}/overview`) })),
    ]
    if (q.trim()) base.push({ label: `Search filings for “${q.trim()}”`, hint: '↵', go: () => nav(`/c/${ticker}/search?q=${encodeURIComponent(q.trim())}`) })
    const ql = q.toLowerCase()
    const filtered = base.filter((o) => !ql || o.label.toLowerCase().includes(ql) || o.hint === '↵')
    return filtered
  }, [q, companies, nav, ticker])
  useEffect(() => setI(0), [q])
  return (
    <div className="palette-bg" onMouseDown={onClose}>
      <div className="palette" onMouseDown={(e) => e.stopPropagation()}>
        <input autoFocus placeholder="Jump to a page, a company, or search every filing…" value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onClose()
            if (e.key === 'ArrowDown') { e.preventDefault(); setI(Math.min(i + 1, opts.length - 1)) }
            if (e.key === 'ArrowUp') { e.preventDefault(); setI(Math.max(i - 1, 0)) }
            if (e.key === 'Enter' && opts[i]) { opts[i].go(); onClose() }
          }} />
        {opts.slice(0, 12).map((o, j) => (
          <div key={o.label} className={'opt' + (j === i ? ' on' : '')} onMouseEnter={() => setI(j)} onClick={() => { o.go(); onClose() }}>
            {o.label}<span className="k kbd">{o.hint}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Company() {
  const { ticker = '' } = useParams()
  const t = ticker.toUpperCase()
  const nav = useNavigate()
  const { data: ov, error } = useApi<OverviewT>(`c/${t}/overview`)
  const [palette, setPalette] = useState(false)
  const pendingG = useRef(0)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.metaKey || e.ctrlKey) {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); setPalette(true) }
        return
      }
      if (e.key === '/') { e.preventDefault(); setPalette(true); return }
      if (e.key === 'g') { pendingG.current = Date.now(); return }
      if (Date.now() - pendingG.current < 900) {
        const n = [...NAV, ...MINE].find((x) => x.key === e.key)
        if (n) nav(`/c/${t}/${n.to}`)
        pendingG.current = 0
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [nav, t])

  useEffect(() => { document.title = ov ? `${t} ${price(ov.price)} · Markets` : 'Markets' }, [ov, t])

  return (
    <div className="shell">
      <div className="topbar">
        <Brand />
        <div className="ticker-pill" onClick={() => setPalette(true)} title="Switch company (/)">
          <span className="sym">{t}</span>
          <span className="nm">{ov?.company.name ?? '…'}</span>
        </div>
        {ov && (
          <div className="quote">
            <span className="px">{price(ov.price)}</span>
            <span className={'chg ' + tone(ov.change)}>
              {ov.price && ov.prev_close ? (ov.price - ov.prev_close > 0 ? '+' : '') + (ov.price - ov.prev_close).toFixed(2) : ''} ({pct(ov.change, 2)})
            </span>
            <span className="dimmer mono" style={{ fontSize: 11 }}>{ov.quote?.exchange} · {ov.quote?.currency} · {ov.quote?.partial
              ? <span className="gold" title="Fetched during the session: the last bar is a live snapshot, not a close">intraday {new Date(ov.quote.as_of).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/New_York' })} ET</span>
              : <>close {ov.last_bar}</>}</span>
          </div>
        )}
        <div className="spacer" />
        <div className="searchbox" onClick={() => setPalette(true)} style={{ cursor: 'text' }}>
          <span>⌕</span><span style={{ flex: 1 }} className="dimmer">Search pages, companies, filings…</span><span className="kbd">/</span>
        </div>
      </div>
      <nav className="sidenav">
        <div className="sect">COMPANY</div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={`/c/${t}/${n.to}`} className={({ isActive }) => (isActive ? 'active' : '')}>
            <span style={{ width: 14, textAlign: 'center' }}>{n.icon}</span>{n.label}<span className="k">g {n.key}</span>
          </NavLink>
        ))}
        <div className="sect">MINE</div>
        {MINE.map((n) => (
          <NavLink key={n.to} to={`/c/${t}/${n.to}`} className={({ isActive }) => (isActive ? 'active' : '')}>
            <span style={{ width: 14, textAlign: 'center' }}>{n.icon}</span>{n.label}<span className="k">g {n.key}</span>
          </NavLink>
        ))}
        <div className="foot">
          {ov ? <>
            <div>{ov.counts.filings_archived.toLocaleString()} / {ov.counts.filings.toLocaleString()} filings archived</div>
            <div>{ov.counts.facts.toLocaleString()} XBRL facts</div>
            <div>{ov.counts.price_days.toLocaleString()} trading days</div>
          </> : null}
          <div style={{ marginTop: 8 }}>Free public data · not advice</div>
        </div>
      </nav>
      <main className="main">
        {error ? <div className="err">{error}</div> : (
          <Routes>
            <Route path="overview" element={<Overview t={t} ov={ov} />} />
            <Route path="financials" element={<Financials t={t} />} />
            <Route path="filings" element={<Filings t={t} />} />
            <Route path="filings/:acc" element={<Filings t={t} />} />
            <Route path="search" element={<Search t={t} />} />
            <Route path="people" element={<People t={t} />} />
            <Route path="ownership" element={<Ownership t={t} />} />
            <Route path="news" element={<News t={t} />} />
            <Route path="compare" element={<Compare t={t} />} />
            <Route path="journal" element={<Journal t={t} />} />
            <Route path="*" element={<Navigate to="overview" replace />} />
          </Routes>
        )}
      </main>
      {palette && <Palette ticker={t} onClose={() => setPalette(false)} />}
    </div>
  )
}

function Home() {
  const { data, error } = useApi<{ ticker: string }[]>('companies')
  if (error) return <div className="err">{error}</div>
  if (!data) return <div className="loading">loading</div>
  if (!data.length) return <div className="empty">No companies yet — run <code>./markets add TSLA &amp;&amp; ./markets update TSLA</code></div>
  return <Navigate to={`/c/${data[0].ticker}/overview`} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/c/:ticker/*" element={<Company />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
