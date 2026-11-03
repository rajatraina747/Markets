// Number/date formatting used everywhere. Tabular, compact, honest about nulls.

export const DASH = '—'

export function money(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !isFinite(v)) return DASH
  const a = Math.abs(v)
  const s = v < 0 ? '-' : ''
  if (a >= 1e12) return `${s}$${(a / 1e12).toFixed(digits + 1)}T`
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(digits)}B`
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(digits)}M`
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(digits)}K`
  return `${s}$${a.toFixed(2)}`
}

export function compact(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !isFinite(v)) return DASH
  const a = Math.abs(v)
  const s = v < 0 ? '-' : ''
  if (a >= 1e12) return `${s}${(a / 1e12).toFixed(digits)}T`
  if (a >= 1e9) return `${s}${(a / 1e9).toFixed(digits)}B`
  if (a >= 1e6) return `${s}${(a / 1e6).toFixed(digits)}M`
  if (a >= 1e3) return `${s}${(a / 1e3).toFixed(digits)}K`
  return `${s}${a.toFixed(a < 10 && a % 1 ? 2 : 0)}`
}

export function price(v: number | null | undefined): string {
  if (v === null || v === undefined || !isFinite(v)) return DASH
  return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function pct(v: number | null | undefined, digits = 1, signed = true): string {
  if (v === null || v === undefined || !isFinite(v)) return DASH
  const s = (v * 100).toFixed(digits)
  return (signed && v > 0 ? '+' : '') + s + '%'
}

export function mult(v: number | null | undefined): string {
  if (v === null || v === undefined || !isFinite(v)) return DASH
  return v.toFixed(v >= 100 ? 0 : 1) + '×'
}

export function int(v: number | null | undefined): string {
  if (v === null || v === undefined || !isFinite(v)) return DASH
  return Math.round(v).toLocaleString('en-US')
}

export function bytes(v: number | null | undefined): string {
  if (!v) return DASH
  if (v >= 1e6) return (v / 1e6).toFixed(1) + ' MB'
  if (v >= 1e3) return (v / 1e3).toFixed(0) + ' KB'
  return v + ' B'
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export function date(s: string | null | undefined): string {
  if (!s) return DASH
  const [y, m, d] = s.slice(0, 10).split('-')
  return `${+d} ${MONTHS[+m - 1]} ${y}`
}

export function cellValue(v: number | null | undefined, unit: string): string {
  if (v === null || v === undefined) return DASH
  if (unit === 'USD/shares') return v.toFixed(2)
  if (unit === 'shares') return compact(v, 2)
  const m = v / 1e6
  return Math.abs(m) >= 1000 ? Math.round(m).toLocaleString('en-US') : m.toFixed(Math.abs(m) < 10 ? 1 : 0)
}

export const tone = (v: number | null | undefined) =>
  v === null || v === undefined || v === 0 ? '' : v > 0 ? 'up' : 'down'
