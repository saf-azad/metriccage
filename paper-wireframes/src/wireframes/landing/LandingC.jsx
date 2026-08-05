/**
 * 1c — Editorial column: one narrow thread, numbers as headlines.
 *
 * The export is verbatim down to the second corrections row and then stops mid-element.
 * Everything below the marker is reconstructed: chat 2 records that the finished 1c had
 * a case-study strip and a contact footer, so those are rebuilt in this layout's own
 * idiom — a 400px measure inside a 520px card, so the strip is a stacked list rather
 * than the three-up grid 1a uses, and the footer stays centred like the hero.
 */

import {
  Bar,
  TextBlock,
  Col,
  Row,
  Eyebrow,
  Heading,
  Num,
  Card,
  Panel,
  MediaBlock,
  Pill,
  CalibrationChart,
  LedgerRow,
  Arrow,
} from '../../components/paper/index.js'

/** A number set as a headline, with its label and one line of gloss beside it. */
function FigureHead({ value, labelW, glossW }) {
  return (
    <Row gap={16} align="baseline">
      <Num size={44}>{value}</Num>
      <Col gap={7}>
        <Bar h={5} w={labelW} tone="label" />
        <Bar h={3} w={glossW} tone="prose" />
      </Col>
    </Row>
  )
}

/** Reconstructed: a case study as a full-measure row rather than a card in a grid. */
function CaseRow({ titleW }) {
  return (
    <Card r="lg" row gap={14} pad={14} style={{ alignItems: 'center' }}>
      <MediaBlock h={56} r="md" style={{ width: 56, flex: 'none' }} />
      <Col gap={8} style={{ flex: 1 }}>
        <Bar h={5} w={titleW} tone="label" />
        <Bar h={3} w="80%" tone="prose" />
      </Col>
      <Arrow />
    </Card>
  )
}

export default function LandingC() {
  return (
    <>
      {/* ── masthead ─────────────────────────────────────────────── */}
      <Row
        justify="space-between"
        align="center"
        style={{ padding: '18px 40px', borderBottom: 'var(--border)' }}
      >
        <div style={{ fontWeight: 700, fontSize: 13 }}>MetricCage</div>
        <Row gap={14}>
          <Bar h={4} w={40} tone="label" style={{ alignSelf: 'center' }} />
          <Bar h={4} w={48} tone="label" style={{ alignSelf: 'center' }} />
          <Bar h={4} w={36} tone="label" style={{ alignSelf: 'center' }} />
        </Row>
      </Row>

      {/* ── hero ─────────────────────────────────────────────────── */}
      <Col
        gap={20}
        style={{
          padding: '60px 60px 50px',
          alignItems: 'center',
          textAlign: 'center',
          borderBottom: 'var(--border)',
        }}
      >
        <Eyebrow>Safwat Al Azad</Eyebrow>
        <Heading size={34} leading="var(--leading-tight)">
          When it says 70%,
          <br />
          it wins 70.
        </Heading>
        <Col gap={8} style={{ alignItems: 'center' }}>
          <Bar h={3} w={285} tone="prose" />
          <Bar h={3} w={240} tone="prose" />
          <Bar h={3} w={210} tone="prose" />
        </Col>
        <Pill h={38} padX={22} style={{ marginTop: 6 }}>
          Read the evidence
        </Pill>
      </Col>

      {/* ── 0.202 — the Brier score, as a headline ───────────────── */}
      <Col gap={26} style={{ padding: '44px 60px', borderBottom: 'var(--border)' }}>
        <FigureHead value="0.202" labelW={90} glossW={130} />
        <TextBlock lines={[undefined, undefined, '70%']} />
        <CalibrationChart
          viewBox="0 0 400 120"
          diag={[10, 110, 390, 10]}
          strokeW={2.5}
          points="10,108 90,90 170,68 250,48 330,28 390,12"
          dots={[
            [90, 90],
            [250, 48],
            [330, 28],
          ]}
        />
        <Bar h={3} w={150} tone="prose" style={{ alignSelf: 'center' }} />
      </Col>

      {/* ── 4 — the findings the audit reversed ──────────────────── */}
      <Col gap={22} style={{ padding: '44px 60px', borderBottom: 'var(--border)' }}>
        <FigureHead value="4" labelW={120} glossW={100} />
        <Col gap={12}>
          <LedgerRow boxed={false} h={4} strikeW={100} correctedW={120} />
          <LedgerRow boxed={false} h={4} strikeW={80} correctedW={105} />
          {/* ↑ the export is truncated at this point; everything below is reconstructed */}
        </Col>
      </Col>

      {/* ── case studies (reconstructed) ─────────────────────────── */}
      <Col gap={20} style={{ padding: '44px 60px', borderBottom: 'var(--border)' }}>
        <Row justify="space-between" align="baseline">
          <Eyebrow>Case studies</Eyebrow>
          <Bar h={3} w={50} tone="prose" />
        </Row>
        <Col gap={12}>
          <CaseRow titleW={110} />
          <CaseRow titleW={95} />
          <CaseRow titleW={125} />
        </Col>
      </Col>

      {/* ── contact (reconstructed) ──────────────────────────────── */}
      <Panel
        gap={14}
        pad="40px 30px"
        style={{ margin: 20, alignItems: 'center', textAlign: 'center' }}
      >
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
