/**
 * 1a — Broadcast scroll: the current narrative, redrawn.
 *
 * A verbatim reconstruction of option 1a from the Claude Design export. Section order
 * follows the live site: hero → premise → pipeline → ensemble → results → corrections
 * → case studies → contact. Card width 640.
 */

import {
  Bar,
  TextBlock,
  Col,
  Row,
  Section,
  Eyebrow,
  Heading,
  Card,
  Panel,
  Pill,
  SegmentedBar,
  CalibrationChart,
  StatCard,
  PipelineStep,
  LegendRow,
  ResultsTable,
  LedgerRow,
  CaseCard,
} from '../../components/paper/index.js'

export default function LandingA() {
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

      {/* ── hero + scoreboard ────────────────────────────────────── */}
      <Section pad="50px 30px 40px" gap={18}>
        <Eyebrow>Fight analytics · calibrated ML</Eyebrow>
        <Heading
          size={42}
          tracking="var(--tracking-tight)"
          leading="var(--leading-tight)"
        >
          MetricCage
        </Heading>
        <Col gap={8}>
          <Bar h={3} w={285} tone="prose" />
          <Bar h={3} w={240} tone="prose" />
        </Col>
        <Row gap={10} style={{ marginTop: 6 }}>
          <Pill>Discoveries</Pill>
          <Pill variant="outline">Scoreboard</Pill>
        </Row>
        <Row gap={12} style={{ marginTop: 14 }}>
          <StatCard value="0.202" barW={44} />
          <StatCard value="0.049" barW={32} />
          <StatCard value="695" barW={52} />
          <StatCard value="102" barW={40} />
        </Row>
      </Section>

      {/* ── the premise ──────────────────────────────────────────── */}
      <Section row gap={30}>
        <Col gap={10} style={{ width: 180, flex: 'none' }}>
          <Eyebrow>The premise</Eyebrow>
          <Heading size={18} leading="var(--leading-snug)">
            Accuracy is the wrong target.
          </Heading>
        </Col>
        <Col gap={8} style={{ flex: 1 }}>
          <TextBlock lines={[undefined, undefined, '75%', null, undefined, '85%', '60%']} />
          <Card r="lg" pad={14} gap={8} style={{ marginTop: 12 }}>
            <Bar h={5} w={135} tone="label" />
            <Bar h={3} w="80%" tone="prose" />
          </Card>
        </Col>
      </Section>

      {/* ── pipeline ─────────────────────────────────────────────── */}
      <Section gap={20}>
        <Eyebrow>Pipeline</Eyebrow>
        <Row gap={12}>
          <PipelineStep n="01" barW={60} />
          <PipelineStep n="02" barW={70} />
          <PipelineStep n="03" barW={55} />
          <PipelineStep n="04" barW={64} />
        </Row>
      </Section>

      {/* ── ensemble weighting ───────────────────────────────────── */}
      <Section gap={16}>
        <Eyebrow>Ensemble — four models, one probability</Eyebrow>
        <SegmentedBar
          h={24}
          segments={[
            { w: '38%', fill: 'var(--ink)' },
            { w: '27%', fill: 'var(--slate)' },
            { w: '20%', fill: 'var(--fill)' },
            { w: '15%', fill: 'var(--slate-a15)' },
          ]}
        />
        <Col gap={10}>
          <LegendRow fill="var(--ink)" barW={105} value="38%" />
          <LegendRow fill="var(--slate)" barW={90} value="27%" />
          <LegendRow fill="var(--fill)" soft barW={120} value="20%" />
          <LegendRow fill="var(--slate-a15)" soft barW={80} value="15%" />
        </Col>
      </Section>

      {/* ── results + calibration ────────────────────────────────── */}
      <Section row gap={24}>
        <Col gap={14} style={{ flex: 1 }}>
          <Eyebrow>Results</Eyebrow>
          <ResultsTable
            rows={[
              [90, '0.598'],
              [70, '0.202'],
              [80, '64.7%'],
              [60, '0.049'],
            ]}
          />
        </Col>
        <Col gap={10} style={{ flex: 1 }}>
          <Bar h={5} w={105} tone="label" />
          <CalibrationChart
            framed
            viewBox="0 0 240 150"
            diag={[30, 130, 220, 20]}
            points="30,128 70,105 110,82 150,62 190,38 220,24"
            dots={[
              [30, 128],
              [110, 82],
              [190, 38],
            ]}
          />
          <Bar h={3} w={160} tone="prose" />
        </Col>
      </Section>

      {/* ── corrections ledger ───────────────────────────────────── */}
      <Section gap={14}>
        <Eyebrow>Corrections ledger</Eyebrow>
        <Col gap={12}>
          <LedgerRow strikeW={110} correctedW={130} mechanismW={70} />
          <LedgerRow strikeW={90} correctedW={110} mechanismW={60} />
        </Col>
      </Section>

      {/* ── case studies ─────────────────────────────────────────── */}
      <Section gap={16}>
        <Row justify="space-between" align="baseline">
          <Eyebrow>Case studies</Eyebrow>
          <Bar h={3} w={50} tone="prose" />
        </Row>
        <Row gap={12}>
          <CaseCard titleW={80} />
          <CaseCard titleW={70} />
          <CaseCard titleW={90} />
        </Row>
      </Section>

      {/* ── contact ──────────────────────────────────────────────── */}
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
    </>
  )
}
