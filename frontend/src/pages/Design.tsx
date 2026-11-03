import { useState } from 'react'
import { EChart, base, axis, C } from '../components/EChart'
import { Spark } from '../components/Spark'
import { Bar, Chip, Delta, Empty, PageTitle, Panel, Seg, Stat, StatGrid, Tag, tokens } from '../ui'

const COLORS: [string, string][] = [
  ['--bg', 'page'], ['--bg-1', 'surface'], ['--bg-2', 'raised'], ['--bg-3', 'sunken / track'], ['--line', 'hairline'], ['--line-2', 'border'],
  ['--text', 'primary text'], ['--text-2', 'secondary'], ['--text-3', 'tertiary'], ['--gold', 'brand · focus · selection'],
  ['--up', 'positive'], ['--down', 'negative'], ['--blue', 'series 2'], ['--violet', 'series 3'], ['--cyan', 'series 4'], ['--orange', 'series 5'],
]

export default function Design() {
  const [seg, setSeg] = useState<'annual' | 'quarterly'>('annual')
  const [chip, setChip] = useState(true)
  const option = {
    ...base, grid: { left: 40, right: 10, top: 24, bottom: 22 }, legend: { top: 0, right: 0, textStyle: { color: C.text2, fontSize: 11 } },
    xAxis: { type: 'category', data: ['Q1', 'Q2', 'Q3', 'Q4', 'Q1', 'Q2'], ...axis }, yAxis: { type: 'value', ...axis },
    series: [{ name: 'Series 1', type: 'bar', data: [5, 7, 6, 9, 8, 11], color: C.gold, barMaxWidth: 16 },
      { name: 'Series 2', type: 'line', data: [3, 4, 6, 5, 7, 8], color: C.blue, symbol: 'none' }],
  }
  return (
    <div className="grid">
      <PageTitle title="Design system" sub="The tokens and primitives every page and workspace widget is built from · src/ui/index.tsx · styles.css :root" />
      <Panel title="Colour tokens">
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>
          {COLORS.map(([v, l]) => <div key={v}><div className="swatch" style={{ background: `var(${v})` }} /><div className="mono" style={{ fontSize: 11, marginTop: 4 }}>{v}</div><div className="dimmer" style={{ fontSize: 11 }}>{l}</div></div>)}
        </div>
      </Panel>
      <div className="grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
        <Panel title="Type">
          <div style={{ display: 'grid', gap: 8 }}>
            <div style={{ fontSize: 18, fontWeight: 650 }}>Page title · Inter 18/650</div>
            <div style={{ font: '600 11px var(--sans)', letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-2)' }}>Panel header · 11/600 caps</div>
            <div>Body · Inter 13/1.45 with tabular figures 1,234,567.89</div>
            <div className="mono">Numbers · JetBrains Mono 12 — 398.66 +1.23%</div>
            <div className="dimmer">Tertiary / captions</div>
          </div>
        </Panel>
        <Panel title="Link groups (workspace)">
          <div style={{ display: 'flex', gap: 10 }}>{Object.entries(tokens.link).map(([k, c]) => <div key={k} style={{ textAlign: 'center' }}><div className="swatch" style={{ background: c, width: 60 }} /><div className="mono" style={{ fontSize: 11 }}>{k}</div></div>)}</div>
          <div className="dimmer" style={{ fontSize: 12, marginTop: 10 }}>Panels in the same colour share a ticker; “none” panels keep their own. Colour shows on the panel's top border and its link badge.</div>
        </Panel>
      </div>
      <Panel title="Primitives">
        <div style={{ display: 'grid', gap: 14 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <code>&lt;Seg&gt;</code><Seg options={['annual', 'quarterly'] as const} value={seg} onChange={setSeg} />
            <code>&lt;Chip&gt;</code><Chip on={chip} onClick={() => setChip(!chip)} dot={C.gold} count={117}>Results</Chip><Chip>off</Chip>
            <code>&lt;Tag&gt;</code><Tag kind="k10">10-K</Tag><Tag kind="q10">10-Q</Tag><Tag kind="k8">8-K</Tag><Tag kind="f4">4</Tag><Tag kind="px">DEF 14A</Tag><Tag>other</Tag>
          </div>
          <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
            <code>&lt;Delta&gt;</code><Delta v={0.0523} /><Delta v={-0.031} /><Delta v={0} />
            <code>&lt;Bar&gt;</code><Bar v={0.08} /><Bar v={-0.12} />
            <code>&lt;Spark&gt;</code><Spark vals={[3, 4, 3.5, 5, 4.8, 6, 5.5, 7]} w={100} h={26} /><Spark vals={[7, 6, 6.5, 5, 4, 4.2, 3]} w={100} h={26} />
          </div>
          <StatGrid cols={4}><Stat label="Market cap" value="$1.58T" sub="3.95B sh" /><Stat label="Net income" value="$3.2B" tone="up" /><Stat label="Op. margin" value="-3.8%" tone="down" /><Stat label="P/E" value="488×" tone="gold" /></StatGrid>
          <Empty>&lt;Empty&gt; — what to run when there's no data</Empty>
        </div>
      </Panel>
      <Panel title="Charts — shared ECharts defaults (base, axis, C)"><EChart option={option} height={200} /></Panel>
      <Panel title="Rules">
        <ul className="dim" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
          <li>Dark only, dense, numbers in mono with tabular figures. Gold means “selected / brand”, never “good”.</li>
          <li>Green/red only for signed values (returns, P&amp;L, deltas). Everything else is neutral.</li>
          <li>Pages compose <code>Panel · Stat · Seg · Chip · Tag · Delta · Bar · Empty</code>; no one-off panel styles.</li>
          <li>Every empty state says which command fills it. Every number can be traced to a source (hover / double-click).</li>
          <li>Workspace widgets take only a ticker and fill their panel — so any page section can become a widget.</li>
        </ul>
      </Panel>
    </div>
  )
}
