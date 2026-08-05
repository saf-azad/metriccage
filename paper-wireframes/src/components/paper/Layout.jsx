/**
 * Layout atoms. Paper has no grid framework — every screen in the source is flexbox on
 * a 5px coordinate grid — so these are deliberately thin wrappers that keep the
 * wireframes readable without inventing layout behaviour.
 */

export function Col({ gap, children, style, ...rest }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap, ...style }} {...rest}>
      {children}
    </div>
  )
}

export function Row({ gap, align, justify, children, style, ...rest }) {
  return (
    <div
      style={{ display: 'flex', gap, alignItems: align, justifyContent: justify, ...style }}
      {...rest}
    >
      {children}
    </div>
  )
}

/** Pushes whatever follows it to the far end of a row. */
export const Spacer = () => <div style={{ flex: 1 }} />

/**
 * Section — a horizontal band of the page. Vertical rhythm in Paper comes from pitch
 * rather than rules, but the landing-page wireframes do separate their bands with the
 * standard 2px ink border, so it is opt-out rather than opt-in here.
 */
export function Section({
  pad = '36px 30px',
  divider = true,
  gap,
  row = false,
  children,
  style,
  ...rest
}) {
  return (
    <div
      style={{
        padding: pad,
        borderBottom: divider ? 'var(--border)' : undefined,
        display: 'flex',
        flexDirection: row ? 'row' : 'column',
        gap,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  )
}

/**
 * Eyebrow — the small tracked-out label that opens most bands.
 *
 * Note: the Paper readme states the source SVGs contain no all-caps setting. The
 * wireframes do use one for section eyebrows, and since these are literal
 * reproductions of the approved mocks, the mock wins. Flagged rather than silently
 * "corrected".
 */
export function Eyebrow({ children, style }) {
  return (
    <div
      style={{
        fontSize: 11,
        fontWeight: 500,
        letterSpacing: 'var(--tracking-wide)',
        textTransform: 'uppercase',
        color: 'var(--ink-a50)',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

/** Real type. The system sets numerals and almost nothing else. */
export function Num({ children, size = 22, weight = 700, style }) {
  return <div style={{ fontSize: size, fontWeight: weight, ...style }}>{children}</div>
}

export function Heading({ children, size = 18, weight = 700, leading, tracking, style }) {
  return (
    <div
      style={{
        fontSize: size,
        fontWeight: weight,
        lineHeight: leading,
        letterSpacing: tracking,
        ...style,
      }}
    >
      {children}
    </div>
  )
}
