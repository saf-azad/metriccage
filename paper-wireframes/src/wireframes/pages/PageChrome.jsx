/**
 * Shared chrome for the three inner pages. The export only specifies the landing page,
 * so these are derived: the masthead, page hero and contact panel are lifted straight
 * out of option 1a so the whole site reads as one system.
 */

import { Bar, Col, Row, Eyebrow, Heading, Panel, Pill } from '../../components/paper/index.js'

/** The 1a masthead, with the current page marked by an ink-weight nav bar. */
export function Masthead({ active = 0 }) {
  const widths = [52, 40, 46]
  return (
    <Row
      align="center"
      justify="space-between"
      style={{ padding: '18px 30px', borderBottom: 'var(--border)' }}
    >
      <div style={{ fontWeight: 700, fontSize: 15 }}>MetricCage</div>
      <Row gap={16} align="center">
        {widths.map((w, i) => (
          <Bar key={i} h={5} w={w} tone={i === active ? 'strong' : 'label'} />
        ))}
        <Pill h={28} padX={14} fs={11}>
          Contact
        </Pill>
      </Row>
    </Row>
  )
}

export function PageHero({ eyebrow, title, lines = [285, 240] }) {
  return (
    <Col gap={16} style={{ padding: '46px 30px 36px', borderBottom: 'var(--border)' }}>
      <Eyebrow>{eyebrow}</Eyebrow>
      <Heading size={34} tracking="var(--tracking-tight)" leading="var(--leading-tight)">
        {title}
      </Heading>
      <Col gap={8}>
        {lines.map((w, i) => (
          <Bar key={i} h={3} w={w} tone="prose" />
        ))}
      </Col>
    </Col>
  )
}

export function ContactFooter() {
  return (
    <Panel gap={14} style={{ margin: 20 }}>
      <Heading size={20} style={{ color: 'var(--text-invert)' }}>
        Get in touch
      </Heading>
      <Bar h={3} w={200} tone="invert" />
      <Row gap={10} style={{ marginTop: 8 }}>
        <Pill variant="white">GitHub</Pill>
        <Pill variant="outlineWhite">CV</Pill>
      </Row>
    </Panel>
  )
}

/**
 * SplitSection — the 1a "premise" band: a 180px stack of eyebrow + heading against a
 * flexible column of drawn prose or a chart.
 */
export function SplitSection({ eyebrow, title, children, gap = 30, divider = true }) {
  return (
    <Row
      gap={gap}
      style={{ padding: '36px 30px', borderBottom: divider ? 'var(--border)' : undefined }}
    >
      <Col gap={10} style={{ width: 180, flex: 'none' }}>
        <Eyebrow>{eyebrow}</Eyebrow>
        {title && (
          <Heading size={18} leading="var(--leading-snug)">
            {title}
          </Heading>
        )}
      </Col>
      <Col gap={12} style={{ flex: 1 }}>
        {children}
      </Col>
    </Row>
  )
}
