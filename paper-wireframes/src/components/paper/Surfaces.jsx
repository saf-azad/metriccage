/**
 * Surfaces. The whole recipe for a card in Paper: a 2px ink outline, a radius from the
 * ladder, no fill, no shadow, no header divider. Depth is expressed three ways only —
 * an outline, a fill change, or one surface overlapping another.
 */

const RADII = {
  sm: 'var(--radius-sm)',
  md: 'var(--radius-md)',
  lg: 'var(--radius-lg)',
  xl: 'var(--radius-xl)',
  '2xl': 'var(--radius-2xl)',
  '3xl': 'var(--radius-3xl)',
  pill: 'var(--radius-pill)',
}

export const radius = (r) => RADII[r] ?? r

export function Card({
  r = 'md',
  pad,
  gap,
  row = false,
  clip = false,
  border = 'var(--border)',
  fill,
  children,
  style,
  ...rest
}) {
  return (
    <div
      style={{
        border,
        borderRadius: radius(r),
        padding: pad,
        background: fill,
        overflow: clip ? 'hidden' : undefined,
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
 * Panel — the inverted container. Solid ink, the largest radius, white type. The only
 * place `--white` is allowed to appear.
 */
export function Panel({ r = '3xl', pad = '34px 30px', gap, children, style, ...rest }) {
  return (
    <div
      style={{
        background: 'var(--surface-panel)',
        borderRadius: radius(r),
        padding: pad,
        display: 'flex',
        flexDirection: 'column',
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
 * MediaBlock — a placeholder for imagery. Paper never shows a photograph; it shows
 * slate at 35% with a matching stroke, or opaque `--fill` for thumbnails and card
 * headers.
 */
export function MediaBlock({ h, r = 'lg', solid = false, bordered = true, style, ...rest }) {
  return (
    <div
      style={{
        height: h,
        borderRadius: radius(r),
        background: solid ? 'var(--surface-media-solid)' : 'var(--surface-media)',
        border: bordered ? 'var(--border-media)' : undefined,
        ...style,
      }}
      {...rest}
    />
  )
}

/** Tile — the faint empty cell, slate at 15%. */
export function Tile({ h, r = 'md', style, ...rest }) {
  return (
    <div
      style={{ height: h, borderRadius: radius(r), background: 'var(--surface-tile)', ...style }}
      {...rest}
    />
  )
}
