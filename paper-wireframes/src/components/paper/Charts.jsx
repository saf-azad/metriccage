/**
 * Charts. Hand-written SVG, no charting library — the same decision the live site
 * makes, and the only one compatible with Paper's stroke rules. A chart here is three
 * marks: a dashed slate reference line (perfect calibration), a solid ink series, and
 * ink dots on the sampled bins.
 */

export function CalibrationChart({
  viewBox,
  /** [x1, y1, x2, y2] — the diagonal a perfectly calibrated model would trace */
  diag,
  dash = '4 4',
  points,
  strokeW = 2,
  dots = [],
  dotR = 4,
  /** [x, y1, y2] triples — the Wilson intervals on each sampled bin */
  errorBars = [],
  framed = false,
  style,
}) {
  return (
    <svg
      viewBox={viewBox}
      style={{
        width: '100%',
        border: framed ? 'var(--border-media)' : undefined,
        borderRadius: framed ? 'var(--radius-lg)' : undefined,
        background: framed ? 'var(--slate-a15)' : undefined,
        ...style,
      }}
    >
      <line
        x1={diag[0]}
        y1={diag[1]}
        x2={diag[2]}
        y2={diag[3]}
        stroke="var(--slate)"
        strokeWidth="2"
        strokeDasharray={dash}
      />
      <polyline points={points} fill="none" stroke="var(--ink)" strokeWidth={strokeW} />
      {dots.map(([cx, cy], i) => (
        <circle key={i} cx={cx} cy={cy} r={dotR} fill="var(--ink)" />
      ))}
      {errorBars.map(([x, y1, y2], i) => (
        <line key={i} x1={x} y1={y1} x2={x} y2={y2} stroke="var(--slate)" strokeWidth="2" />
      ))}
    </svg>
  )
}

/**
 * ColumnChart — an ink-outlined histogram. Used for the forecast distribution and the
 * evidence-coverage bands, where a line would imply continuity the data does not have.
 */
export function ColumnChart({ viewBox = '0 0 400 120', bars, baseline = 110, style }) {
  return (
    <svg viewBox={viewBox} style={{ width: '100%', ...style }}>
      <line x1="0" y1={baseline} x2="400" y2={baseline} stroke="var(--ink)" strokeWidth="2" />
      {bars.map(([x, w, h], i) => (
        <rect
          key={i}
          x={x}
          y={baseline - h}
          width={w}
          height={h}
          fill="var(--fill)"
          stroke="var(--ink)"
          strokeWidth="2"
        />
      ))}
    </svg>
  )
}

/**
 * SeriesChart — a plain ink line over a slate-filled tile, for the era trends on the
 * discoveries page. An optional second series is drawn dashed rather than tinted,
 * because the kit has no second colour to spend.
 */
export function SeriesChart({ viewBox = '0 0 400 130', points, secondary, framed = true, style }) {
  return (
    <svg
      viewBox={viewBox}
      style={{
        width: '100%',
        border: framed ? 'var(--border-media)' : undefined,
        borderRadius: framed ? 'var(--radius-lg)' : undefined,
        background: framed ? 'var(--slate-a15)' : undefined,
        ...style,
      }}
    >
      {secondary && (
        <polyline
          points={secondary}
          fill="none"
          stroke="var(--slate)"
          strokeWidth="2"
          strokeDasharray="5 5"
        />
      )}
      <polyline points={points} fill="none" stroke="var(--ink)" strokeWidth="2.5" />
    </svg>
  )
}

/**
 * BeeswarmBlock — the SHAP beeswarm stands in as a scatter of slate dots around a
 * centre rule, which is all a wireframe should commit to at this stage.
 */
export function BeeswarmBlock({ viewBox = '0 0 400 110', rows, style }) {
  return (
    <svg viewBox={viewBox} style={{ width: '100%', ...style }}>
      <line x1="200" y1="6" x2="200" y2="104" stroke="var(--ink)" strokeWidth="2" />
      {rows.map((row, r) =>
        row.map((cx, i) => (
          <circle key={`${r}-${i}`} cx={cx} cy={18 + r * 24} r="3.5" fill="var(--slate)" />
        )),
      )}
    </svg>
  )
}
