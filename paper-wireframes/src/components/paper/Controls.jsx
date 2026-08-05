/**
 * Controls. Paper buttons are pills and, in the source, unlabelled. The landing-page
 * wireframes do label theirs, so `Pill` takes children — kept to one or two words,
 * sentence case, no punctuation, per the system's copy rules.
 */

const VARIANTS = {
  /** filled ink pill — the primary action */
  solid: { background: 'var(--action-solid)', color: 'var(--action-solid-text)' },
  /** 2px ink outline, paper showing through */
  outline: { border: 'var(--border)', color: 'var(--action-outline-text)' },
  /** the lift inside an ink panel */
  white: { background: 'var(--white)', color: 'var(--ink)' },
  /** outline drawn in white, also panel-only */
  outlineWhite: { border: 'var(--stroke) solid var(--white)', color: 'var(--text-invert)' },
}

export function Pill({ variant = 'solid', h = 36, padX = 18, fs = 12, full = false, children, style }) {
  return (
    <div
      style={{
        height: h,
        padding: full ? 0 : `0 ${padX}px`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: full ? 'center' : undefined,
        borderRadius: 'var(--radius-pill)',
        fontSize: fs,
        fontWeight: 500,
        flex: 'none',
        ...VARIANTS[variant],
        ...style,
      }}
    >
      {children}
    </div>
  )
}

/**
 * Swatch — the small square that keys a legend row, or the selected/unselected marker
 * in a sidebar. Selection in Paper is a solid ink fill and nothing else: never a
 * colour, never a heavier border, never a fill *and* a checkmark.
 */
export function Swatch({ size = 14, r = 4, fill, selected, style }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: r,
        background: selected ? 'var(--ink)' : fill,
        border: !selected && !fill ? 'var(--border)' : undefined,
        flex: 'none',
        ...style,
      }}
    />
  )
}

/** Chip — the segmented-control pill pair used above a chart in the dashboard layout. */
export function Chip({ w = 40, h = 16, active = false, style }) {
  return (
    <div
      style={{
        width: w,
        height: h,
        borderRadius: 'var(--radius-pill)',
        background: active ? 'var(--fill)' : undefined,
        border: active ? undefined : 'var(--border-soft)',
        flex: 'none',
        ...style,
      }}
    />
  )
}

/**
 * Track — a horizontal meter. The empty track is slate at 15%, the filled portion is
 * solid ink. No gradient: the system uses exactly two, both elsewhere.
 */
export function Track({ pct, h = 10, style }) {
  return (
    <div
      style={{
        flex: 1,
        height: h,
        borderRadius: 'var(--radius-pill)',
        background: 'var(--slate-a15)',
        ...style,
      }}
    >
      <div
        style={{
          width: `${pct}%`,
          height: '100%',
          borderRadius: 'var(--radius-pill)',
          background: 'var(--ink)',
        }}
      />
    </div>
  )
}

/**
 * SegmentedBar — the ensemble weighting: one pill, four segments, 2px outline, clipped.
 */
export function SegmentedBar({ h = 24, segments, style }) {
  return (
    <div
      style={{
        display: 'flex',
        height: h,
        borderRadius: 'var(--radius-pill)',
        overflow: 'hidden',
        border: 'var(--border)',
        ...style,
      }}
    >
      {segments.map((s, i) => (
        <div key={i} style={{ width: s.w, background: s.fill }} />
      ))}
    </div>
  )
}
