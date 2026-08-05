/**
 * Bar — the load-bearing primitive of the Paper system.
 *
 * Paper draws prose rather than setting it. A 5px bar is a heading, a 3px bar is a line
 * of body copy, and the width carries the meaning. Two tones exist and they are not
 * interchangeable: a black-at-opacity bar is *interface* text (titles, labels, row
 * headings), a slate bar is *content* text (article bodies, descriptions). Never mix
 * them inside one block.
 */

const TONES = {
  /** interface text — the standard bar */
  label: 'var(--ink-a50)',
  /** interface text, one step heavier — the corrected half of a ledger row */
  strong: 'var(--ink-a60)',
  /** content text — prose the user wrote */
  prose: 'var(--slate-a60)',
  /** inside an ink panel */
  invert: 'rgba(255,255,255,.5)',
}

export default function Bar({ h = 3, w, tone = 'prose', style, ...rest }) {
  return (
    <div
      style={{
        width: w,
        height: h,
        borderRadius: 99,
        background: TONES[tone] ?? tone,
        flex: 'none',
        ...style,
      }}
      {...rest}
    />
  )
}

/**
 * StrikeBar — a bar with a 1px ink rule drawn across it, overhanging both ends.
 * This is how the corrections ledger shows a retracted claim. The hairline is the one
 * place the system uses a stroke weight other than 2px.
 */
export function StrikeBar({ w, h = 5, top = 2, overhang = 4, tone = 'prose', style }) {
  return (
    <div style={{ position: 'relative', width: w, flex: 'none', ...style }}>
      <Bar h={h} tone={tone} style={{ width: '100%' }} />
      <div
        style={{
          position: 'absolute',
          top,
          left: -overhang,
          right: -overhang,
          height: 1,
          background: 'var(--ink)',
        }}
      />
    </div>
  )
}

/**
 * TextBlock — a ragged paragraph. The source repeats individual 3px bars; this
 * generates the pattern so callers do not place each line by hand. `lines` holds a
 * width per line (a number for px, a string for %, `undefined` to fill the column) and
 * `null` inserts a paragraph break.
 */
export function TextBlock({ lines, gap = 8, h = 3, tone = 'prose', breakH = 12, style }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap, ...style }}>
      {lines.map((w, i) =>
        w === null ? (
          <div key={i} style={{ height: breakH }} />
        ) : (
          // no width given → the bar stretches to fill the column, which is how the
          // source draws a full-measure line of body copy
          <Bar key={i} h={h} w={w} tone={tone} />
        ),
      )}
    </div>
  )
}
