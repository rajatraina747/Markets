// Markets design system — the small set of primitives every page and workspace widget is built
// from. Visual tokens live in styles.css (:root custom properties); chart tokens in components/EChart.
// Rule of thumb: pages compose these; they don't invent new panel/stat/toggle styles.
import type { ReactNode } from 'react'
import { pct } from '../format'

export const tokens = {
  color: {
    bg: 'var(--bg)', surface: 'var(--bg-1)', raised: 'var(--bg-2)', line: 'var(--line)',
    text: 'var(--text)', text2: 'var(--text-2)', text3: 'var(--text-3)',
    gold: 'var(--gold)', up: 'var(--up)', down: 'var(--down)', blue: 'var(--blue)', violet: 'var(--violet)',
    cyan: 'var(--cyan)', orange: 'var(--orange)',
  },
  // link groups for workspace panels (Bloomberg-style colour linking)
  link: { gold: '#d4af37', blue: '#5aa9ff', violet: '#a68bff', green: '#2fbf71', none: '#3a4350' } as Record<string, string>,
  space: [0, 4, 8, 12, 14, 18, 24],
  radius: { sm: 4, md: 8, lg: 10, pill: 999 },
  font: { sans: 'var(--sans)', mono: 'var(--mono)' },
}

export function Panel({ title, right, children, flush, style, className }: {
  title?: ReactNode; right?: ReactNode; children: ReactNode; flush?: boolean; style?: React.CSSProperties; className?: string
}) {
  return (
    <section className={'panel ' + (className ?? '')} style={style}>
      {title !== undefined && <header>{title}<span className="grow" />{right && <span className="hdr-right">{right}</span>}</header>}
      <div className={flush ? 'body flush' : 'body'}>{children}</div>
    </section>
  )
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'up' | 'down' | 'gold' | '' }) {
  return <div className="stat"><div className="l">{label}</div><div className={'v ' + (tone ?? '')}>{value}</div>{sub ? <div className="s">{sub}</div> : null}</div>
}

export function StatGrid({ children, cols }: { children: ReactNode; cols?: number }) {
  return <div className="stats" style={cols ? { gridTemplateColumns: `repeat(${cols}, 1fr)` } : undefined}>{children}</div>
}

export function Seg<T extends string | number>({ options, value, onChange, labels }: {
  options: readonly T[]; value: T; onChange: (v: T) => void; labels?: Partial<Record<T, ReactNode>>
}) {
  return (
    <div className="seg">
      {options.map((o) => <button key={String(o)} className={o === value ? 'on' : ''} onClick={() => onChange(o)}>{labels?.[o] ?? String(o)}</button>)}
    </div>
  )
}

export function Chip({ on, onClick, children, dot, count, title }: {
  on?: boolean; onClick?: () => void; children: ReactNode; dot?: string; count?: ReactNode; title?: string
}) {
  return (
    <span className={'chip' + (on ? ' on' : '')} onClick={onClick} title={title}>
      {dot && <span className="dot" style={{ background: dot }} />}{children}{count !== undefined && <span className="n">{count}</span>}
    </span>
  )
}

export function Tag({ kind, children, title }: { kind?: 'k10' | 'q10' | 'k8' | 'f4' | 'px' | ''; children: ReactNode; title?: string }) {
  return <span className={'tag ' + (kind ?? '')} title={title}>{children}</span>
}

/** Signed percentage, coloured. */
export function Delta({ v, digits = 1, signed = true }: { v: number | null | undefined; digits?: number; signed?: boolean }) {
  const cls = v === null || v === undefined || v === 0 ? 'dimmer' : v > 0 ? 'up' : 'down'
  return <span className={'mono ' + cls}>{pct(v, digits, signed)}</span>
}

export function Empty({ children }: { children: ReactNode }) { return <div className="empty">{children}</div> }
export function Loading({ what }: { what?: string }) { return <div className="loading">loading{what ? ' ' + what : ''}</div> }

export function PageTitle({ title, sub, right }: { title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="page-title">
      <h1>{title}</h1>{sub && <span className="sub">{sub}</span>}
      {right && <><span style={{ flex: 1 }} />{right}</>}
    </div>
  )
}

/** Horizontal bar for a value in [-1, 1] (reactions, margins) — tiny, table-friendly. */
export function Bar({ v, max = 0.2, w = 80 }: { v: number | null | undefined; max?: number; w?: number }) {
  if (v === null || v === undefined) return <span className="dimmer">—</span>
  const frac = Math.min(Math.abs(v) / max, 1)
  return (
    <span style={{ display: 'inline-flex', width: w, height: 8, background: 'var(--bg-3)', borderRadius: 4, position: 'relative', verticalAlign: 'middle' }}>
      <span style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: 'var(--line-2)' }} />
      <span style={{ position: 'absolute', top: 0, bottom: 0, borderRadius: 4, background: v >= 0 ? 'var(--up)' : 'var(--down)',
        left: v >= 0 ? '50%' : `${50 - frac * 50}%`, width: `${frac * 50}%` }} />
    </span>
  )
}
