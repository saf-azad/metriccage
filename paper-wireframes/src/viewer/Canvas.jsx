/**
 * The review canvas. Reproduces the presentation chrome of the Claude Design export:
 * turns hold options, each option is a labelled card, and the id anchors (#1a, #2c)
 * still work so a specific wireframe can be linked to in review.
 */

export function Turn({ id, name, children, next }) {
  return (
    <section className="dv-turn" id={id}>
      <div className="dv-thd">
        <a className="dv-tid" href={`#${id}`}>
          {id.replace('t', '')}
        </a>
        <span className="dv-tname">{name}</span>
      </div>
      <div className="dv-opts">{children}</div>
      {next && <p className="dv-next">{next}</p>}
    </section>
  )
}

export function Option({ id, label, note, width, children }) {
  return (
    <div className="dv-opt" id={id}>
      <div className="dv-olabel">
        <a className="dv-oid" href={`#${id}`}>
          {id}
        </a>
        {label}
        {note && <span className="dv-note">{note}</span>}
      </div>
      <div className="dv-card" style={{ width }}>
        {children}
      </div>
    </div>
  )
}
