export function Kpi({ label, value, note }) {
  return (
    <article className="kpi">
      <p className="kpi-label">{label}</p>
      <p className="kpi-value">{value}</p>
      {note ? <p className="kpi-note">{note}</p> : null}
    </article>
  );
}

export function Status({ loading, error, children }) {
  if (loading) return <p className="status">Loading the January desk…</p>;
  if (error) {
    return (
      <p className="status error" role="alert">
        The desk API did not respond. Start the Python service, then refresh.
      </p>
    );
  }
  return children;
}
