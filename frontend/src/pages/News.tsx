import { useMemo, useState } from 'react'
import type { NewsPage, Prices } from '../api'
import { useApi, useDebounced } from '../hooks'
import { EChart, base, axis, C } from '../components/EChart'

function ago(iso: string | null) {
  if (!iso) return ''
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 3600) return Math.max(1, Math.round(s / 60)) + 'm'
  if (s < 86400) return Math.round(s / 3600) + 'h'
  return Math.round(s / 86400) + 'd'
}

export default function News({ t }: { t: string }) {
  const [qIn, setQIn] = useState('')
  const q = useDebounced(qIn)
  const [source, setSource] = useState('')
  const { data, error } = useApi<NewsPage>(`c/${t}/news?limit=500` + (q ? `&q=${encodeURIComponent(q)}` : '') + (source ? `&source=${encodeURIComponent(source)}` : ''))
  const { data: prices } = useApi<Prices>(`c/${t}/prices`)

  const option = useMemo(() => {
    if (!data?.per_day.length) return null
    const from = data.per_day[0].day
    const px = (prices?.rows ?? []).filter((r) => r[0] >= from).map((r) => [r[0], r[4]])
    return {
      ...base, grid: { left: 40, right: 56, top: 30, bottom: 26 },
      legend: { top: 0, right: 0, textStyle: { color: C.text2, fontSize: 11 } },
      xAxis: { type: 'time', ...axis },
      yAxis: [{ type: 'value', ...axis, minInterval: 1 }, { type: 'value', ...axis, splitLine: { show: false }, scale: true }],
      series: [
        { name: 'Headlines / day', type: 'bar', data: data.per_day.map((d) => [d.day, d.n]), itemStyle: { color: 'rgba(90,169,255,.6)' }, barMaxWidth: 14 },
        { name: 'Close', type: 'line', yAxisIndex: 1, data: px, showSymbol: false, lineStyle: { color: C.gold, width: 1.5 }, itemStyle: { color: C.gold } },
      ],
    }
  }, [data, prices])

  if (error) return <div className="err">{error}</div>
  return (
    <div className="grid">
      <div className="page-title">
        <h1>News</h1>
        <span className="sub">Google News RSS + GDELT headlines, archived every update{data?.first ? ` · ${data.total.toLocaleString()} since ${data.first.slice(0, 10)}` : ''} · headlines only, read at the source</span>
      </div>
      {option && <section className="panel"><header>Coverage vs price</header><div className="body"><EChart option={option} height={200} /></div></section>}
      <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 260px' }}>
        <section className="panel">
          <header>Headlines<span className="grow" />
            <input className="input" style={{ width: 280, textTransform: 'none', letterSpacing: 0 }} placeholder="Filter headlines…" value={qIn} onChange={(e) => setQIn(e.target.value)} />
          </header>
          <div style={{ maxHeight: 'calc(100vh - 420px)', minHeight: 300, overflow: 'auto' }}>
            {!data ? <div className="loading">loading</div> : data.rows.length ? data.rows.map((n) => (
              <a key={n.url} href={n.url} target="_blank" rel="noreferrer noopener" className="ev" style={{ color: 'var(--text)', gridTemplateColumns: '110px 1fr 44px' }}>
                <span className="d" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.source}</span>
                <span className="t">{n.title}</span>
                <span className="d right">{ago(n.published)}</span>
              </a>
            )) : <div className="empty">No headlines yet — run ./markets update {t} --only news (each run adds the last 7 days).</div>}
          </div>
        </section>
        <section className="panel">
          <header>Sources</header>
          <div style={{ maxHeight: 520, overflow: 'auto' }}>
            <div className={'doc'} />
            {data?.sources.map((s) => (
              <div key={s.source} className="ev" style={{ gridTemplateColumns: '1fr auto', cursor: 'pointer', background: source === s.source ? 'var(--gold-dim)' : undefined }}
                onClick={() => setSource(source === s.source ? '' : s.source)}>
                <span>{s.source || '—'}</span><span className="mono dimmer">{s.n}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
