/**
 * 1b — Dashboard: sidebar nav, evidence as a control room.
 *
 * A verbatim reconstruction of option 1b from the Claude Design export. The argument
 * is laid out as instrumentation rather than as a scroll — the scoreboard, the
 * calibration curve with its Wilson intervals, permutation importance, and the ledger
 * all visible at once. Card width 680.
 */

import {
  Bar,
  Col,
  Row,
  Spacer,
  Eyebrow,
  Heading,
  Card,
  MediaBlock,
  Pill,
  Chip,
  CalibrationChart,
  StatCard,
  ProgressRow,
  LedgerRow,
  NavItem,
} from '../../components/paper/index.js'

export default function LandingB() {
  return (
    <div style={{ display: 'flex', minHeight: 640 }}>
      {/* ── sidebar ──────────────────────────────────────────────── */}
      <Col
        gap={24}
        style={{
          width: 150,
          flex: 'none',
          borderRight: 'var(--border)',
          padding: '24px 18px',
        }}
      >
        <div style={{ fontWeight: 700, fontSize: 14 }}>MetricCage</div>
        <Col gap={16}>
          <NavItem barW={56} selected />
          <NavItem barW={64} />
          <NavItem barW={48} />
          <NavItem barW={70} />
          <NavItem barW={52} />
        </Col>
        <Spacer />
        <Pill full h={34} fs={11}>
          Contact
        </Pill>
      </Col>

      {/* ── main ─────────────────────────────────────────────────── */}
      <Col gap={18} style={{ flex: 1, padding: 24 }}>
        <Col gap={10}>
          <Eyebrow>Calibrated UFC prediction</Eyebrow>
          <Heading size={26}>The scoreboard first.</Heading>
          <Bar h={3} w={260} tone="prose" />
        </Col>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10 }}>
          <StatCard barFirst value="0.598" barW={36} fs={19} pad={12} gap={6} />
          <StatCard barFirst value="0.202" barW={30} fs={19} pad={12} gap={6} />
          <StatCard barFirst value="64.7%" barW={40} fs={19} pad={12} gap={6} />
          <StatCard barFirst value="0.049" barW={26} fs={19} pad={12} gap={6} />
        </div>

        {/* reliability diagram — the headline chart of the whole project */}
        <Card r="lg" pad={16} gap={10}>
          <Row justify="space-between" align="center">
            <Bar h={5} w={120} tone="label" />
            <Row gap={6}>
              <Chip active />
              <Chip />
            </Row>
          </Row>
          <CalibrationChart
            viewBox="0 0 560 180"
            diag={[40, 160, 530, 20]}
            dash="5 5"
            strokeW={2.5}
            points="40,158 120,132 200,108 280,88 360,64 440,44 530,22"
            dots={[
              [120, 132],
              [280, 88],
              [440, 44],
            ]}
            dotR={5}
            errorBars={[
              [120, 122, 144],
              [280, 76, 100],
              [440, 32, 56],
            ]}
          />
          <Bar h={3} w={180} tone="prose" />
        </Card>

        <Row gap={10}>
          <Card r="lg" pad={14} gap={10} style={{ flex: 1 }}>
            <Bar h={5} w={90} tone="label" />
            <Col gap={7}>
              <ProgressRow pct={82} />
              <ProgressRow pct={64} />
              <ProgressRow pct={47} />
              <ProgressRow pct={31} />
            </Col>
          </Card>
          <Card r="lg" pad={14} gap={10} style={{ flex: 1 }}>
            <Bar h={5} w={110} tone="label" />
            <MediaBlock style={{ flex: 1, minHeight: 90 }} r="md" />
          </Card>
        </Row>

        {/* ── corrections ledger ─────────────────────────────────── */}
        <Card r="lg" clip>
          <Row
            justify="space-between"
            style={{
              padding: '10px 14px',
              background: 'var(--slate-a15)',
              borderBottom: 'var(--border)',
            }}
          >
            <Eyebrow>Corrections ledger</Eyebrow>
            <div style={{ fontSize: 11, fontWeight: 700 }}>4 reversed</div>
          </Row>
          <LedgerRow
            boxed={false}
            arrow={false}
            h={4}
            strikeW={90}
            correctedW={110}
            style={{ padding: '10px 14px', borderBottom: 'var(--border-soft)' }}
          />
          <LedgerRow
            boxed={false}
            arrow={false}
            h={4}
            strikeW={70}
            correctedW={95}
            style={{ padding: '10px 14px' }}
          />
        </Card>
      </Col>
    </div>
  )
}
