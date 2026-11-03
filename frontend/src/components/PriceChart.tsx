import { useEffect, useMemo, useRef, useState } from 'react'
import {
  createChart, CandlestickSeries, HistogramSeries, LineSeries, AreaSeries, createSeriesMarkers,
  type IChartApi, type ISeriesApi, type SeriesMarker, type Time, type ISeriesMarkersPluginApi,
  CrosshairMode, PriceScaleMode,
} from 'lightweight-charts'
import type { EventRow, Prices } from '../api'
import { compact, date as fdate, price as fprice } from '../format'

export const EVENT_KINDS: Record<string, { label: string; color: string; shape: 'circle' | 'square' | 'arrowUp' | 'arrowDown'; pos: 'aboveBar' | 'belowBar' }> = {
  earnings: { label: 'Results', color: '#d4af37', shape: 'circle', pos: 'aboveBar' },
  filing: { label: '10-K / 10-Q', color: '#5aa9ff', shape: 'square', pos: 'belowBar' },
  '8k': { label: '8-K', color: '#a68bff', shape: 'circle', pos: 'aboveBar' },
  insider: { label: 'Insider', color: '#3cc8d8', shape: 'arrowUp', pos: 'belowBar' },
  split: { label: 'Split', color: '#ff9d4d', shape: 'square', pos: 'aboveBar' },
  dividend: { label: 'Dividend', color: '#2fbf71', shape: 'circle', pos: 'belowBar' },
  holder: { label: '13D/G', color: '#e879a8', shape: 'square', pos: 'belowBar' },
}

const RANGES: [string, number | null][] = [['1M', 30], ['3M', 91], ['6M', 182], ['YTD', -1], ['1Y', 365], ['3Y', 1095], ['5Y', 1826], ['MAX', null]]

type Mode = 'candles' | 'line' | 'area'

function snapTo(dates: string[], d: string): string | null {
  // first trading day on/after d (binary search)
  let lo = 0, hi = dates.length - 1, ans = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (dates[mid] >= d) { ans = mid; hi = mid - 1 } else lo = mid + 1
  }
  return ans === -1 ? null : dates[ans]
}

function sma(closes: number[], n: number): (number | null)[] {
  const out: (number | null)[] = []
  let sum = 0
  for (let i = 0; i < closes.length; i++) {
    sum += closes[i]
    if (i >= n) sum -= closes[i - n]
    out.push(i >= n - 1 ? sum / n : null)
  }
  return out
}

export function PriceChart({ prices, events, kinds, height = 440, onEvent, fluid = false }: {
  prices: Prices; events: EventRow[]; kinds: Set<string>; height?: number
  onEvent?: (e: EventRow) => void
  fluid?: boolean  // fill the parent's height (workspace panels) instead of a fixed height
}) {
  const el = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const mainRef = useRef<ISeriesApi<'Candlestick'> | ISeriesApi<'Line'> | ISeriesApi<'Area'> | null>(null)
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line' | 'Area' | 'Candlestick' | 'Histogram'>[]>([])
  const [range, setRange] = useState('1Y')
  const [mode, setMode] = useState<Mode>('candles')
  const [log, setLog] = useState(false)
  const [mas, setMas] = useState(true)
  const [hover, setHover] = useState<{ d: string; o: number; h: number; l: number; c: number; v: number; ev: EventRow[] } | null>(null)

  const dates = useMemo(() => prices.rows.map((r) => r[0]), [prices])
  const evByDate = useMemo(() => {
    const m = new Map<string, EventRow[]>()
    for (const e of events) {
      if (!kinds.has(e.kind)) continue
      const d = snapTo(dates, e.date)
      if (!d) continue
      if (!m.has(d)) m.set(d, [])
      m.get(d)!.push(e)
    }
    return m
  }, [events, kinds, dates])

  // build chart once
  useEffect(() => {
    if (!el.current) return
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { color: 'transparent' }, textColor: '#9aa3b2', fontFamily: 'JetBrains Mono, monospace', fontSize: 11, attributionLogo: false },
      grid: { vertLines: { color: '#12161d' }, horzLines: { color: '#12161d' } },
      rightPriceScale: { borderColor: '#222834' },
      timeScale: { borderColor: '#222834', rightOffset: 4, minBarSpacing: 0.05 },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: '#3a4350', labelBackgroundColor: '#1a1f28' }, horzLine: { color: '#3a4350', labelBackgroundColor: '#1a1f28' } },
    })
    chartRef.current = chart
    return () => { chart.remove(); chartRef.current = null; mainRef.current = null; markersRef.current = null; seriesRef.current = [] }
  }, [])

  // (re)build series on data/mode change
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    // clear old series
    markersRef.current?.detach()
    for (const s of seriesRef.current) chart.removeSeries(s)
    const created: ISeriesApi<'Line' | 'Area' | 'Candlestick' | 'Histogram'>[] = []
    const rows = prices.rows
    let main: ISeriesApi<'Candlestick'> | ISeriesApi<'Line'> | ISeriesApi<'Area'>
    if (mode === 'candles') {
      main = chart.addSeries(CandlestickSeries, { upColor: '#2fbf71', downColor: '#f0524f', borderVisible: false, wickUpColor: '#2fbf71', wickDownColor: '#f0524f', priceLineColor: '#d4af37' })
      main.setData(rows.map((r) => ({ time: r[0] as Time, open: r[1], high: r[2], low: r[3], close: r[4] })))
    } else if (mode === 'line') {
      main = chart.addSeries(LineSeries, { color: '#d4af37', lineWidth: 2, priceLineColor: '#d4af37' })
      main.setData(rows.map((r) => ({ time: r[0] as Time, value: r[4] })))
    } else {
      main = chart.addSeries(AreaSeries, { lineColor: '#d4af37', topColor: 'rgba(212,175,55,.28)', bottomColor: 'rgba(212,175,55,0)', lineWidth: 2 })
      main.setData(rows.map((r) => ({ time: r[0] as Time, value: r[4] })))
    }
    created.push(main)
    const vol = chart.addSeries(HistogramSeries, { priceScaleId: 'vol', priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false })
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    vol.setData(rows.map((r, i) => ({ time: r[0] as Time, value: r[5], color: i && r[4] < rows[i - 1][4] ? 'rgba(240,82,79,.35)' : 'rgba(47,191,113,.35)' })))
    created.push(vol)
    if (mas) {
      const closes = rows.map((r) => r[4])
      for (const [n, color] of [[50, '#5aa9ff'], [200, '#a68bff']] as const) {
        const s = chart.addSeries(LineSeries, { color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
        s.setData(sma(closes, n).map((v, i) => (v === null ? { time: rows[i][0] as Time } : { time: rows[i][0] as Time, value: v })))
        created.push(s)
      }
    }
    seriesRef.current = created
    mainRef.current = main
    markersRef.current = createSeriesMarkers(main as ISeriesApi<'Candlestick'>, [])
    chart.priceScale('right').applyOptions({ mode: log ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal })
  }, [prices, mode, mas, log])

  // markers
  useEffect(() => {
    const mk = markersRef.current
    if (!mk) return
    const markers: SeriesMarker<Time>[] = []
    for (const [d, evs] of [...evByDate.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1))) {
      const top = [...evs].sort((a, b) => b.importance - a.importance)[0]
      const k = EVENT_KINDS[top.kind] ?? EVENT_KINDS['8k']
      let shape = k.shape
      if (top.kind === 'insider') shape = top.title.includes(' bought ') ? 'arrowUp' : 'arrowDown'
      markers.push({ time: d as Time, position: k.pos, color: top.kind === 'insider' && shape === 'arrowDown' ? '#f0524f' : k.color, shape, size: top.importance >= 3 ? 1 : 0.6 })
    }
    mk.setMarkers(markers)
  }, [evByDate, mode, mas, log, prices])

  // range
  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !dates.length) return
    const r = RANGES.find((x) => x[0] === range)!
    const last = dates[dates.length - 1]
    let from: string
    if (r[1] === null) from = dates[0]
    else if (r[1] === -1) from = last.slice(0, 4) + '-01-01'
    else { const d = new Date(last); d.setDate(d.getDate() - r[1]); from = d.toISOString().slice(0, 10) }
    chart.timeScale().setVisibleRange({ from: (snapTo(dates, from) ?? dates[0]) as Time, to: last as Time })
  }, [range, dates, mode, mas, log])

  // crosshair legend + click
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const idx = new Map(prices.rows.map((r, i) => [r[0], i]))
    const move = (p: { time?: Time }) => {
      if (!p.time) { setHover(null); return }
      const i = idx.get(p.time as string)
      if (i === undefined) return
      const r = prices.rows[i]
      setHover({ d: r[0], o: r[1], h: r[2], l: r[3], c: r[4], v: r[5], ev: evByDate.get(r[0]) ?? [] })
    }
    const click = (p: { time?: Time }) => {
      if (!p.time || !onEvent) return
      const evs = evByDate.get(p.time as string)
      if (evs?.length) onEvent([...evs].sort((a, b) => b.importance - a.importance)[0])
    }
    chart.subscribeCrosshairMove(move)
    chart.subscribeClick(click)
    return () => { chart.unsubscribeCrosshairMove(move); chart.unsubscribeClick(click) }
  }, [prices, evByDate, onEvent])

  const last = prices.rows[prices.rows.length - 1]
  const h = hover ?? (last ? { d: last[0], o: last[1], h: last[2], l: last[3], c: last[4], v: last[5], ev: evByDate.get(last[0]) ?? [] } : null)

  return (
    <div style={fluid ? { height: '100%', display: 'flex', flexDirection: 'column' } : undefined}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: fluid ? '6px 10px' : '10px 14px', flexWrap: 'wrap' }}>
        <div className="seg">{RANGES.map(([k]) => <button key={k} className={range === k ? 'on' : ''} onClick={() => setRange(k)}>{k}</button>)}</div>
        <div className="seg">
          {(['candles', 'line', 'area'] as Mode[]).map((m) => <button key={m} className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>{m}</button>)}
        </div>
        <div className="seg">
          <button className={log ? 'on' : ''} onClick={() => setLog(!log)}>log</button>
          <button className={mas ? 'on' : ''} onClick={() => setMas(!mas)}>50/200 MA</button>
        </div>
        {h && (
          <div className="mono dim" style={{ marginLeft: 'auto', display: 'flex', gap: 12 }}>
            <span className="dimmer">{fdate(h.d)}</span>
            <span>O <b>{fprice(h.o)}</b></span><span>H <b>{fprice(h.h)}</b></span>
            <span>L <b>{fprice(h.l)}</b></span><span>C <b className="gold">{fprice(h.c)}</b></span>
            <span>V <b>{compact(h.v)}</b></span>
          </div>
        )}
      </div>
      <div ref={el} style={fluid ? { flex: 1, minHeight: 0, position: 'relative' } : { height, position: 'relative' }} />
      {!fluid && <div style={{ minHeight: 30, padding: '6px 14px', fontSize: 12 }} className="dim">
        {h?.ev.length ? h.ev.map((e, i) => (
          <span key={i} style={{ marginRight: 16 }}>
            <span className="bar" style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: EVENT_KINDS[e.kind]?.color, marginRight: 6 }} />
            {e.title}{e.detail ? <span className="dimmer"> · {e.detail}</span> : null}
          </span>
        )) : <span className="dimmer">Hover the chart for OHLC and events · click a marker to open the filing</span>}
      </div>}
    </div>
  )
}
