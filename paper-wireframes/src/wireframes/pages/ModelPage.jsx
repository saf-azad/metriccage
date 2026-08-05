/**
 * 2a — Model evidence, wireframed.
 *
 * Derived, not exported: the design file only covers the landing page, so this rebuilds
 * model.html's six numbered sections in the vocabulary option 1a establishes. Section
 * eyebrows and headings are the live page's own; everything else is drawn.
 *
 * Only figures that already appear in the approved mocks are set as type — 0.202,
 * 0.049, 695, 102. Paper's rule against numbering things for effect means no new
 * numerals were invented to fill the layout.
 */

import {
  Bar,
  TextBlock,
  Col,
  Row,
  Spacer,
  Section,
  Eyebrow,
  Card,
  Swatch,
  Chip,
  Track,
  SegmentedBar,
  ColumnChart,
  SeriesChart,
  BeeswarmBlock,
  ProgressRow,
  Num,
} from '../../components/paper/index.js'
import { Masthead, PageHero, ContactFooter, SplitSection } from './PageChrome.jsx'

/** A legend row whose value is drawn rather than set — used where no figure is given. */
function KeyRow({ fill, soft, barW, valueW }) {
  return (
    <Row gap={12} align="center">
      <Swatch size={14} fill={fill} style={soft ? { border: 'var(--border-soft)' } : undefined} />
      <Bar h={5} w={barW} tone="label" />
      <Spacer />
      <Bar h={3} w={valueW} tone="prose" />
    </Row>
  )
}

/** One rung of the baseline ladder. The ensemble rung carries the only real figure. */
function LadderRow({ barW, pct, value }) {
  return (
    <Row gap={10} align="center">
      <Bar h={3} w={barW} tone="prose" />
      <Track pct={pct} />
      {value ? <Num size={13}>{value}</Num> : <Bar h={3} w={30} tone="prose" />}
    </Row>
  )
}

export default function ModelPage() {
  return (
    <>
      <Masthead active={1} />
      <PageHero eyebrow="Model evidence" title="Show the working." lines={[285, 240, 190]} />

      {/* ── 01 · Murphy decomposition ────────────────────────────── */}
      <SplitSection
        eyebrow="01 · the central claim, as arithmetic"
        title="Calibration and discrimination are two terms of one equation."
      >
        <TextBlock lines={[undefined, undefined, '80%']} />
        {/* uncertainty − resolution + reliability, drawn as one bar */}
        <SegmentedBar
          h={22}
          segments={[
            { w: '58%', fill: 'var(--ink)' },
            { w: '30%', fill: 'var(--slate)' },
            { w: '12%', fill: 'var(--fill)' },
          ]}
        />
        <Col gap={10}>
          <KeyRow fill="var(--ink)" barW={100} valueW={38} />
          <KeyRow fill="var(--slate)" barW={85} valueW={34} />
          <KeyRow fill="var(--fill)" soft barW={110} valueW={30} />
        </Col>
      </SplitSection>

      {/* ── 02 · the baseline ladder ─────────────────────────────── */}
      <SplitSection
        eyebrow="02 · value added"
        title="A four-model ensemble is worth exactly what it beats."
      >
        <Card r="lg" pad={16} gap={12}>
          <Bar h={5} w={120} tone="label" />
          <Col gap={9}>
            <LadderRow barW={58} pct={34} />
            <LadderRow barW={70} pct={52} />
            <LadderRow barW={46} pct={68} />
            <LadderRow barW={64} pct={81} />
            <LadderRow barW={52} pct={94} value="0.202" />
          </Col>
        </Card>
        <Bar h={3} w={170} tone="prose" />
      </SplitSection>

      {/* ── 03 · two rankings that disagree ──────────────────────── */}
      <Section gap={16}>
        <Eyebrow>03 · what actually drives it</Eyebrow>
        <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 'var(--leading-snug)' }}>
          Two ways to rank a feature. They disagree completely.
        </div>
        <Row gap={12}>
          <Card r="lg" pad={14} gap={10} style={{ flex: 1 }}>
            <Bar h={5} w={110} tone="label" />
            <Col gap={7}>
              <ProgressRow pct={88} />
              <ProgressRow pct={71} />
              <ProgressRow pct={54} />
              <ProgressRow pct={38} />
            </Col>
          </Card>
          <Card r="lg" pad={14} gap={10} style={{ flex: 1 }}>
            <Bar h={5} w={92} tone="label" />
            <Col gap={7}>
              <ProgressRow pct={45} />
              <ProgressRow pct={83} />
              <ProgressRow pct={29} />
              <ProgressRow pct={66} />
            </Col>
          </Card>
        </Row>
        {/* SHAP across all 695 test fights */}
        <Card r="lg" pad={14} gap={10}>
          <Row justify="space-between" align="center">
            <Bar h={5} w={130} tone="label" />
            <Num size={13}>695</Num>
          </Row>
          <BeeswarmBlock
            rows={[
              [120, 150, 168, 182, 196, 205, 214, 228, 244, 270, 300],
              [140, 162, 176, 188, 198, 208, 219, 232, 250, 282],
              [96, 134, 158, 174, 190, 202, 212, 226, 248, 276, 318],
              [150, 170, 184, 194, 203, 211, 222, 238, 258],
            ]}
          />
          <Bar h={3} w={200} tone="prose" />
        </Card>
      </Section>

      {/* ── 04 · the blind spot, measured ────────────────────────── */}
      <SplitSection
        eyebrow="04 · the limitation, measured"
        title="A fighter’s record begins the day they enter the UFC."
      >
        <TextBlock lines={[undefined, '85%']} />
        <Card r="lg" pad={14} gap={10}>
          <Bar h={5} w={105} tone="label" />
          <ColumnChart
            bars={[
              [14, 26, 22],
              [50, 26, 34],
              [86, 26, 48],
              [122, 26, 41],
              [158, 26, 63],
              [194, 26, 72],
              [230, 26, 58],
              [266, 26, 84],
              [302, 26, 76],
              [338, 26, 92],
            ]}
          />
          <Bar h={3} w={185} tone="prose" />
        </Card>
      </SplitSection>

      {/* ── 05 · stability across years ──────────────────────────── */}
      <SplitSection eyebrow="05 · stability" title="In-sample years, marked as in-sample.">
        <Card r="lg" pad={14} gap={10}>
          <Row justify="space-between" align="center">
            <Bar h={5} w={118} tone="label" />
            {/* train / validation / test */}
            <Row gap={6}>
              <Chip w={34} active />
              <Chip w={34} />
              <Chip w={34} />
            </Row>
          </Row>
          <SeriesChart
            points="14,86 60,74 106,80 152,66 198,72 244,58 290,64 336,54 382,60"
            secondary="14,96 60,92 106,95 152,88 198,91 244,86 290,89 336,84 382,87"
          />
          <Bar h={3} w={160} tone="prose" />
        </Card>
      </SplitSection>

      {/* ── 06 · named, not hidden ───────────────────────────────── */}
      <Section gap={16} divider={false}>
        <Eyebrow>06 · named, not hidden</Eyebrow>
        <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 'var(--leading-snug)' }}>
          What this page still cannot show you.
        </div>
        <Col gap={10}>
          {[
            [140, '92%'],
            [118, '86%'],
            [156, '90%'],
          ].map(([titleW, proseW], i) => (
            <Card key={i} r="md" pad="12px 14px" gap={8}>
              <Bar h={5} w={titleW} tone="label" />
              <Bar h={3} w={proseW} tone="prose" />
            </Card>
          ))}
        </Col>
      </Section>

      <ContactFooter />
    </>
  )
}
