export function Spark({ vals, w = 110, h = 30 }: { vals: number[]; w?: number; h?: number }) {
  if (vals.length < 2) return null
  const min = Math.min(...vals), max = Math.max(...vals)
  const x = (i: number) => (i / (vals.length - 1)) * w
  const y = (v: number) => h - 2 - ((v - min) / (max - min || 1)) * (h - 4)
  const d = vals.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('')
  const up = vals[vals.length - 1] >= vals[0]
  const c = up ? '#2fbf71' : '#f0524f'
  const id = 'g' + Math.round(vals[0] * 1000 + vals.length)
  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={c} stopOpacity=".28" /><stop offset="1" stopColor={c} stopOpacity="0" /></linearGradient></defs>
      <path d={`${d}L${w},${h}L0,${h}Z`} fill={`url(#${id})`} />
      <path d={d} fill="none" stroke={c} strokeWidth="1.5" />
    </svg>
  )
}
