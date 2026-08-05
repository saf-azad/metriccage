/**
 * 1d — Bento grid: the whole argument above the fold.
 *
 * Option 1d is absent from the export — chat 2 records it as built, but the file was
 * truncated before it. This is a reconstruction from the description ("a bento-grid
 * layout that fits the whole argument above the fold") built strictly out of the Paper
 * vocabulary the other three options establish: 2px ink outlines, radius 19 tiles, one
 * ink panel, no shadows, no new colour.
 *
 * Six-column grid, four rows. The claim, the scoreboard, the calibration curve, the
 * ensemble, the ledger, the cases and the contact all land without a scroll. Card
 * width 720.
 */

import {
  Bar,
  Col,
  Row,
  Eyebrow,
  Heading,
  Num,
  Card,
  Panel,
  Pill,
  Chip,
  SegmentedBar,
  CalibrationChart,
  StatCard,
  LegendRow,
  LedgerRow,
  CaseCard,
} from '../../components/paper/index.js'

/** One cell of the bento. Radius 19 is the system's workhorse tile. */
function Cell({ span, pad = 16, gap = 10, children, style }) {
  return (
    <Card r="lg" pad={pad} gap={gap} style={{ gridColumn: `span ${span}`, ...style }}>
      {children}
    </Card>
  )
}

export default function LandingD() {
  return (
    <>
      {/* ── masthead ─────────────────────────────────────────────── */}
      <Row
        align="center"
        justify="space-between"
        style={{ padding: '18px 30px', borderBottom: 'var(--border)' }}
      >
        <div style={{ fontWeight: 700, fontSize: 15 }}>MetricCage</div>
        <Row gap={16} align="center">
          <Bar h={5} w={52} tone="label" />
          <Bar h={5} w={40} tone="label" />
          <Bar h={5} w={46} tone="label" />
          <Pill h={28} padX={14} fs={11}>
            Contact
          </Pill>
        </Row>
      </Row>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(6, 1fr)',
          gap: 12,
          padding: 20,
        }}
      >
        {/* ── the claim ──────────────────────────────────────────── */}
        <Cell span={4} pad={20} gap={14}>
          <Eyebrow>Fight analytics · calibrated ML</Eyebrow>
          <Heading size={34} tracking="var(--tracking-tight)" leading="var(--leading-tight)">
            MetricCage
          </Heading>
          <Col gap={8}>
            <Bar h={3} w={260} tone="prose" />
            <Bar h={3} w={210} tone="prose" />
          </Col>
          <Row gap={10} style={{ marginTop: 2 }}>
            <Pill h={34}>Discoveries</Pill>
            <Pill h={34} variant="outline">
              Scoreboard
            </Pill>
          </Row>
        </Cell>

        {/* ── the headline number ────────────────────────────────── */}
        <Cell span={2} pad={20} gap={10} style={{ justifyContent: 'center' }}>
          <Bar h={5} w={70} tone="label" />
          <Num size={44}>0.202</Num>
          <Bar h={3} w={90} tone="prose" />
        </Cell>

        {/* ── reliability diagram ────────────────────────────────── */}
        <Cell span={4}>
          <Row justify="space-between" align="center">
            <Bar h={5} w={120} tone="label" />
            <Row gap={6}>
              <Chip active />
              <Chip />
            </Row>
          </Row>
          <CalibrationChart
            viewBox="0 0 440 150"
            diag={[30, 132, 420, 18]}
            strokeW={2.5}
            points="30,130 95,110 160,90 225,72 290,54 355,36 420,20"
            dots={[
              [95, 110],
              [225, 72],
              [355, 36],
            ]}
            dotR={4.5}
            errorBars={[
              [95, 101, 119],
              [225, 63, 81],
              [355, 27, 45],
            ]}
          />
          <Bar h={3} w={180} tone="prose" />
        </Cell>

        {/* ── the rest of the scoreboard ─────────────────────────── */}
        <div style={{ gridColumn: 'span 2', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <StatCard barFirst value="0.049" barW={30} fs={19} pad={12} gap={6} />
          <StatCard barFirst value="695" barW={40} fs={19} pad={12} gap={6} />
          <StatCard barFirst value="102" barW={34} fs={19} pad={12} gap={6} />
        </div>

        {/* ── ensemble weighting ─────────────────────────────────── */}
        <Cell span={3} gap={12}>
          <Eyebrow>Ensemble</Eyebrow>
          <SegmentedBar
            h={20}
            segments={[
              { w: '38%', fill: 'var(--ink)' },
              { w: '27%', fill: 'var(--slate)' },
              { w: '20%', fill: 'var(--fill)' },
              { w: '15%', fill: 'var(--slate-a15)' },
            ]}
          />
          <Col gap={8}>
            <LegendRow fill="var(--ink)" barW={95} value="38%" />
            <LegendRow fill="var(--slate)" barW={80} value="27%" />
            <LegendRow fill="var(--fill)" soft barW={105} value="20%" />
            <LegendRow fill="var(--slate-a15)" soft barW={70} value="15%" />
          </Col>
        </Cell>

        {/* ── corrections ledger ─────────────────────────────────── */}
        <Cell span={3} gap={12}>
          <Row justify="space-between" align="baseline">
            <Eyebrow>Corrections ledger</Eyebrow>
            <div style={{ fontSize: 11, fontWeight: 700 }}>4 reversed</div>
          </Row>
          <Col gap={10}>
            <LedgerRow boxed={false} h={4} strikeW={95} correctedW={115} />
            <LedgerRow boxed={false} h={4} strikeW={75} correctedW={100} />
            <LedgerRow boxed={false} h={4} strikeW={88} correctedW={104} />
          </Col>
        </Cell>

        {/* ── case studies ───────────────────────────────────────── */}
        <Cell span={4} gap={12}>
          <Row justify="space-between" align="baseline">
            <Eyebrow>Case studies</Eyebrow>
            <Bar h={3} w={50} tone="prose" />
          </Row>
          <Row gap={10}>
            <CaseCard titleW={70} mediaH={52} />
            <CaseCard titleW={60} mediaH={52} />
            <CaseCard titleW={78} mediaH={52} />
          </Row>
        </Cell>

        {/* ── contact ────────────────────────────────────────────── */}
        <Panel r="xl" pad={20} gap={12} style={{ gridColumn: 'span 2' }}>
          <Heading size={17} style={{ color: 'var(--text-invert)' }}>
            Get in touch
          </Heading>
          <Bar h={3} w={110} tone="invert" />
          <Col gap={8} style={{ marginTop: 'auto' }}>
            <Pill variant="white" h={32} full>
              GitHub
            </Pill>
            <Pill variant="outlineWhite" h={32} full>
              CV
            </Pill>
          </Col>
        </Panel>
      </div>
    </>
  )
}
