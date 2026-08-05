/**
 * 2c — Case studies, wireframed.
 *
 * Derived from case-studies.html. The page has one complete write-up (Macau) and four
 * queued stubs, and the live site is explicit that stubs render as a short
 * "write-up pending" list rather than as fabricated results — so the wireframe draws
 * that distinction structurally: one featured block, then a plain queue.
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
  CaseCard,
  ResultsTable,
} from '../../components/paper/index.js'
import { Masthead, PageHero, ContactFooter, SplitSection } from './PageChrome.jsx'

/** A queued case: titled, dated, and honestly empty. */
function QueuedCase({ titleW }) {
  return (
    <Card r="md" row pad="12px 14px" gap={12} style={{ alignItems: 'center' }}>
      <Bar h={5} w={titleW} tone="label" />
      <Spacer />
      <Bar h={3} w={62} tone="prose" />
    </Card>
  )
}

export default function CaseStudiesPage() {
  return (
    <>
      <Masthead active={2} />
      <PageHero eyebrow="2026 card breakdowns" title="Where it met the sport." lines={[285, 235]} />

      {/* ── how these were scored ────────────────────────────────── */}
      <SplitSection eyebrow="Method" title="How these were scored.">
        <TextBlock lines={[undefined, undefined, '70%']} />
      </SplitSection>

      {/* ── the one complete write-up ────────────────────────────── */}
      <Section gap={16}>
        <Row justify="space-between" align="baseline">
          <Eyebrow>Featured</Eyebrow>
          <Bar h={3} w={50} tone="prose" />
        </Row>
        <Card r="lg" clip>
          <MediaBlock
            h={132}
            style={{ border: 'none', borderBottom: 'var(--border-media)', borderRadius: 0 }}
          />
          <Col gap={14} style={{ padding: 18 }}>
            <Bar h={5} w={160} tone="label" />
            <TextBlock lines={[undefined, undefined, '82%']} />
            {/* record · called · landed */}
            <ResultsTable
              rows={[
                [86, '9'],
                [72, '64.7%'],
                [98, '0.202'],
              ]}
            />
            {/* the lesson — the part of a case study that is worth writing */}
            <Card r="md" pad={14} gap={8} style={{ background: 'var(--slate-a15)' }}>
              <Bar h={5} w={104} tone="label" />
              <Bar h={3} w="88%" tone="prose" />
            </Card>
          </Col>
        </Card>
      </Section>

      {/* ── the queue, not dressed up as results ─────────────────── */}
      <Section gap={14}>
        <Row justify="space-between" align="baseline">
          <Eyebrow>Write-up pending</Eyebrow>
          <Bar h={3} w={44} tone="prose" />
        </Row>
        <Col gap={10}>
          <QueuedCase titleW={118} />
          <QueuedCase titleW={104} />
          <QueuedCase titleW={92} />
          <QueuedCase titleW={136} />
        </Col>
      </Section>

      {/* ── keep reading ─────────────────────────────────────────── */}
      <Section gap={16}>
        <Eyebrow>Keep reading</Eyebrow>
        <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 'var(--leading-snug)' }}>
          The full write-up.
        </div>
        <Row gap={12}>
          <CaseCard titleW={84} />
          <CaseCard titleW={72} />
        </Row>
      </Section>

      {/* ── elsewhere ────────────────────────────────────────────── */}
      <Section gap={14} divider={false}>
        <Eyebrow>Elsewhere</Eyebrow>
        <Row gap={10}>
          <Pill variant="outline">Discoveries</Pill>
          <Pill variant="outline">Model evidence</Pill>
          <Pill variant="outline">Scoreboard</Pill>
        </Row>
      </Section>

      <ContactFooter />
    </>
  )
}
