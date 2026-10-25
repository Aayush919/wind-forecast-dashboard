import { formatCount } from "../format";

export default function Coverage({ summary }) {
  const intervals = summary?.intervals || 0;
  const matched = summary?.paired || 0;
  const pct = intervals ? Math.round((matched / intervals) * 100) : 0;

  return (
    <div className="coverage">
      <div
        className="ring"
        style={{ background: `conic-gradient(#1d4ed8 ${pct}%, #e6edf5 0)` }}
        role="img"
        aria-label={`${pct}% of half-hours matched`}
      >
        <span>{pct}%</span>
      </div>
      <ul>
        <li>
          <span>Half-hours</span>
          <strong>{formatCount(intervals)}</strong>
        </li>
        <li>
          <span>Matched</span>
          <strong>{formatCount(matched)}</strong>
        </li>
        <li>
          <span>Forecast missing</span>
          <strong>{formatCount(summary?.missingForecastIntervals || 0)}</strong>
        </li>
        <li>
          <span>Actual missing</span>
          <strong>{formatCount(summary?.missingActualIntervals || 0)}</strong>
        </li>
      </ul>
    </div>
  );
}
