/**
 * 2b — Discoveries, wireframed.
 *
 * Derived from discoveries.html. The page's own structure is preserved: the three
 * framing discoveries (00 the denominator correction, 00b evidence coverage, 00c the
 * calf-kick null) get full bands, discoveries 01–08 become a card grid, and the methods
 * and queue sections close it out.
 *
 * Discovery headings that the live page computes at runtime are left as bars — the
 * system's rule is to draw copy you were not given rather than invent it.
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
  MediaBlock,
  Pill,
  Chip,
  SeriesChart,
  ColumnChart,
  LedgerRow,
  Num,
} from '../../components/paper/index.js'
import { Masthead, PageHero, ContactFooter, SplitSection } from './PageChrome.jsx'

/** A discovery in the grid: its eyebrow is real, its finding is not yet written. */
function DiscoveryCard({ label, titleW, chart }) {
  return (
    <Card r="lg" pad={14} gap={10} style={{ flex: 1 }}>
      <Eyebrow style={{ fontSize: 10 }}>{label}</Eyebrow>
      <Bar h={5} w={titleW} tone="label" />
      {chart ?? <MediaBlock h={54} r="md" />}
      <Bar h={3} w="85%" tone="prose" />
    </Card>
  )
}

export default function DiscoveriesPage() {
  return (
    <>
      <Masthead active={0} />
      <PageHero
        eyebrow="Eleven computed findings"
        title="What the data actually says."
        lines={[285, 240, 205]}
      />

      {/* ── 00 · the correction that reframes the rest ───────────── */}
      <SplitSection
        eyebrow="Discovery 00 · the correction that reframes the rest"
        title="A share of a tripling total is not a trend."
      >
        <TextBlock lines={[undefined, undefined, '75%']} />
        <Row gap={12}>
          {/* the discredited framing, then the same data per elapsed minute */}
          <Card r="lg" pad={12} gap={8} style={{ flex: 1 }}>
            <Bar h={5} w={86} tone="label" />
            <SeriesChart
              viewBox="0 0 200 100"
              points="10,84 45,70 80,58 115,44 150,30 190,18"
              framed={false}
            />
          </Card>
          <Card r="lg" pad={12} gap={8} style={{ flex: 1 }}>
            <Bar h={5} w={102} tone="label" />
            <SeriesChart
              viewBox="0 0 200 100"
              points="10,56 45,52 80,58 115,50 150,55 190,51"
              framed={false}
            />
          </Card>
        </Row>
        {/* four published findings reversed — nothing deleted */}
        <Col gap={10}>
          <LedgerRow boxed={false} h={4} strikeW={104} correctedW={124} mechanismW={64} />
          <LedgerRow boxed={false} h={4} strikeW={88} correctedW={110} mechanismW={58} />
        </Col>
      </SplitSection>

      {/* ── 00b · evidence coverage ──────────────────────────────── */}
      <SplitSection
        eyebrow="Discovery 00b · the chart almost nobody publishes"
        title="How thin is the evidence, year by year?"
      >
        <Card r="lg" pad={14} gap={10}>
          <Row justify="space-between" align="center">
            <Bar h={5} w={124} tone="label" />
            <Num size={13}>8,793</Num>
          </Row>
          <ColumnChart
            bars={[
              [12, 24, 16],
              [46, 24, 24],
              [80, 24, 31],
              [114, 24, 44],
              [148, 24, 58],
              [182, 24, 66],
              [216, 24, 79],
              [250, 24, 88],
              [284, 24, 84],
              [318, 24, 71],
              [352, 24, 39],
            ]}
          />
          <Bar h={3} w={190} tone="prose" />
        </Card>
      </SplitSection>

      {/* ── 00c · a null result, kept ────────────────────────────── */}
      <SplitSection
        eyebrow="Discovery 00c · a null worth more than most findings"
        title="The calf-kick era does not exist in the data."
      >
        <Card r="lg" pad={14} gap={10}>
          <Bar h={5} w={96} tone="label" />
          <SeriesChart points="14,64 60,61 106,66 152,62 198,65 244,60 290,64 336,63 382,61" />
          <Bar h={3} w={175} tone="prose" />
        </Card>
      </SplitSection>

      {/* ── 01–08 · the discovery grid ───────────────────────────── */}
      <Section gap={16}>
        <Row justify="space-between" align="baseline">
          <Eyebrow>Discoveries 01 — 08</Eyebrow>
          <Bar h={3} w={50} tone="prose" />
        </Row>
        <Col gap={12}>
          <Row gap={12}>
            <DiscoveryCard label="01 · fight sequences" titleW={96} />
            <DiscoveryCard label="02 · inside one fight" titleW={84} />
            <DiscoveryCard label="03 · prove it yourself" titleW={104} />
          </Row>
          <Row gap={12}>
            <DiscoveryCard label="04 · evolution of the sport" titleW={110} />
            <DiscoveryCard label="05 · behaviour conservation" titleW={88} />
            <DiscoveryCard label="06 · what advantages are worth" titleW={100} />
          </Row>
          <Row gap={12}>
            <DiscoveryCard label="06b · the forest plot, rebuilt" titleW={118} />
            <DiscoveryCard label="07 · the pre-finish fingerprint" titleW={92} />
            <DiscoveryCard label="08 · careers have climate" titleW={106} />
          </Row>
        </Col>
      </Section>

      {/* ── data & methods ───────────────────────────────────────── */}
      <SplitSection eyebrow="Data & methods" title="How these numbers were made.">
        <Card r="lg" clip>
          {[
            [110, 'UFCStats'],
            [92, '8,793'],
            [128, '2 Aug 2026'],
            [86, '4'],
          ].map(([w, v], i, a) => (
            <Row
              key={i}
              justify="space-between"
              style={{
                padding: '10px 14px',
                borderBottom: i === a.length - 1 ? undefined : 'var(--border-soft)',
              }}
            >
              <Bar h={5} w={w} tone="label" style={{ alignSelf: 'center' }} />
              <Num size={13}>{v}</Num>
            </Row>
          ))}
        </Card>
        <Row gap={8}>
          <Chip w={54} active />
          <Chip w={54} />
          <Chip w={54} />
        </Row>
      </SplitSection>

      {/* ── the queue ────────────────────────────────────────────── */}
      <Section gap={14} divider={false}>
        <Eyebrow>The queue</Eyebrow>
        <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 'var(--leading-snug)' }}>
          Same engine, next discoveries.
        </div>
        <Col gap={10}>
          {[128, 104, 146].map((w, i) => (
            <Row key={i} gap={12} align="center">
              <Bar h={5} w={w} tone="label" />
              <Spacer />
              <Bar h={3} w={56} tone="prose" />
            </Row>
          ))}
        </Col>
        <Row gap={10} style={{ marginTop: 4 }}>
          <Pill>Read the methods</Pill>
          <Pill variant="outline">Model evidence</Pill>
        </Row>
      </Section>

      <ContactFooter />
    </>
  )
}
