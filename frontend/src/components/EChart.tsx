import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, CustomChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkLineComponent,
  MarkAreaComponent, TitleComponent, AxisPointerComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, LineChart, CustomChart, ScatterChart, GridComponent, TooltipComponent, LegendComponent,
  DataZoomComponent, MarkLineComponent, MarkAreaComponent, TitleComponent, AxisPointerComponent, CanvasRenderer])

export const C = {
  gold: '#d4af37', up: '#2fbf71', down: '#f0524f', blue: '#5aa9ff', violet: '#a68bff', cyan: '#3cc8d8',
  orange: '#ff9d4d', text: '#e6e9ef', text2: '#9aa3b2', text3: '#636c7c', line: '#222834', bg1: '#0d1015',
}

// Shared dark defaults so every chart reads as one system.
export const base = {
  backgroundColor: 'transparent',
  textStyle: { fontFamily: 'Inter Variable, system-ui', color: C.text2 },
  animationDuration: 400,
  grid: { left: 56, right: 18, top: 28, bottom: 28 },
  tooltip: {
    trigger: 'axis' as const,
    backgroundColor: '#12161d', borderColor: '#2d3542', textStyle: { color: C.text, fontSize: 12 },
    axisPointer: { type: 'line' as const, lineStyle: { color: '#3a4350' } },
  },
}

export const axis = {
  axisLine: { lineStyle: { color: C.line } },
  axisTick: { show: false },
  axisLabel: { color: C.text3, fontSize: 11, fontFamily: 'JetBrains Mono, monospace' },
  splitLine: { lineStyle: { color: '#161b23' } },
}

export function EChart({ option, height = 260, onClick }: {
  option: echarts.EChartsCoreOption; height?: number | string; onClick?: (p: unknown) => void
}) {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!el.current) return
    chart.current = echarts.init(el.current, undefined, { renderer: 'canvas' })
    const ro = new ResizeObserver(() => chart.current?.resize())
    ro.observe(el.current)
    return () => { ro.disconnect(); chart.current?.dispose(); chart.current = null }
  }, [])

  useEffect(() => { chart.current?.setOption(option, true) }, [option])

  useEffect(() => {
    const c = chart.current
    if (!c || !onClick) return
    c.on('click', onClick)
    return () => { c.off('click', onClick) }
  }, [onClick])

  return <div ref={el} style={{ width: '100%', height }} />
}
