/**
 * Composite blocks — the repeating shapes of the MetricCage argument, expressed once.
 * Each of these appears in at least two of the seven wireframes.
 */

import Bar, { StrikeBar } from './Bar.jsx'
import { Row, Col, Spacer, Num } from './Layout.jsx'
import { Card, MediaBlock } from './Surfaces.jsx'
import { Swatch, Track } from './Controls.jsx'

/** The arrow between a retracted claim and its correction. */
export const Arrow = () => <div style={{ fontSize: 12 }}>→</div>

/**
 * StatCard — a headline figure over the bar that would label it. The scoreboard
 * numbers (Brier 0.202, ECE 0.049, 695 test fights, 102 features) are the only real
 * type on most of these screens.
 */
export function StatCard({ value, barW, fs = 22, pad = 14, gap = 8, barFirst = false, style }) {
  const label = <Bar h={3} w={barW} tone="prose" />
  const figure = <Num size={fs}>{value}</Num>
  return (
    <Card r="md" pad={pad} gap={gap} style={{ flex: 1, ...style }}>
      {barFirst ? label : figure}
      {barFirst ? figure : label}
    </Card>
  )
}

/** PipelineStep — a numbered stage of the scrape → features → validate → ship chain. */
export function PipelineStep({ n, barW, style }) {
  return (
    <Card r="md" pad={12} gap={8} style={{ flex: 1, ...style }}>
      <Num size={13}>{n}</Num>
      <Bar h={5} w={barW} tone="label" />
      <Bar h={3} w="80%" tone="prose" />
    </Card>
  )
}

/**
 * LegendRow — keys one model in the ensemble to its weight. `soft` adds the hairline
 * outline the two pale swatches need to stay visible against paper.
 */
export function LegendRow({ fill, soft = false, barW, value }) {
  return (
    <Row gap={12} align="center">
      <Swatch size={14} fill={fill} style={soft ? { border: 'var(--border-soft)' } : undefined} />
      <Bar h={5} w={barW} tone="label" />
      <Spacer />
      <Num size={13}>{value}</Num>
    </Row>
  )
}

/** ResultRow — one line of the honest scoreboard: metric label, measured value. */
export function ResultRow({ barW, value, last = false }) {
  return (
    <Row
      justify="space-between"
      style={{ padding: '10px 14px', borderBottom: last ? undefined : 'var(--border-soft)' }}
    >
      <Bar h={5} w={barW} tone="label" style={{ alignSelf: 'center' }} />
      <Num size={13}>{value}</Num>
    </Row>
  )
}

export function ResultsTable({ rows, r = 'md', style }) {
  return (
    <Card r={r} clip style={{ gap: 0, ...style }}>
      {rows.map(([barW, value], i) => (
        <ResultRow key={i} barW={barW} value={value} last={i === rows.length - 1} />
      ))}
    </Card>
  )
}

/**
 * LedgerRow — the corrections ledger. Nothing was deleted when the August audit
 * reversed four findings, so the original claim is struck through and the corrected
 * claim sits beside it with the mechanism named at the end of the row.
 */
export function LedgerRow({
  strikeW,
  correctedW,
  mechanismW,
  h = 5,
  boxed = true,
  /** the dashboard layout drops the glyph and lets the pairing carry the relation */
  arrow = true,
  style,
}) {
  const body = (
    <>
      <StrikeBar w={strikeW} h={h} top={h === 5 ? 2 : 1.5} overhang={h === 5 ? 4 : 3} />
      {arrow && <Arrow />}
      <Bar h={h} w={correctedW} tone="strong" />
      {mechanismW && (
        <>
          <Spacer />
          <Bar h={3} w={mechanismW} tone="prose" />
        </>
      )}
    </>
  )
  return boxed ? (
    <Card r="md" row gap={14} pad="12px 14px" style={{ alignItems: 'center', ...style }}>
      {body}
    </Card>
  ) : (
    <Row gap={12} align="center" style={style}>
      {body}
    </Row>
  )
}

/** ProgressRow — a ranked feature and the share of the model it explains. */
export function ProgressRow({ barW = 52, pct }) {
  return (
    <Row gap={8} align="center">
      <Bar h={3} w={barW} tone="prose" />
      <Track pct={pct} />
    </Row>
  )
}

/** CaseCard — a fight-card breakdown: media header, title bar, one line of standfirst. */
export function CaseCard({ titleW, mediaH = 70, style }) {
  return (
    <Card r="lg" clip style={{ flex: 1, ...style }}>
      <MediaBlock
        h={mediaH}
        r={0}
        style={{ border: 'none', borderBottom: 'var(--border-media)', borderRadius: 0 }}
      />
      <Col gap={8} style={{ padding: 12 }}>
        <Bar h={5} w={titleW} tone="label" />
        <Bar h={3} w="90%" tone="prose" />
      </Col>
    </Card>
  )
}

/** NavItem — a sidebar entry. Selected means a solid ink marker, nothing else. */
export function NavItem({ barW, selected = false }) {
  return (
    <Row gap={10} align="center">
      <Swatch size={12} r={3} selected={selected} />
      <Bar h={5} w={barW} tone={selected ? 'strong' : 'label'} />
    </Row>
  )
}
