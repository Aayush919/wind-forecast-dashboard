import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useJson } from "../api";
import Coverage from "../components/Coverage";
import { Kpi, Status } from "../components/Kpi";
import {
  firmCover,
  formatDay,
  formatEnergy,
  formatMwh,
  formatMw,
  formatStamp,
  GATE_ASSUMPTION,
  januaryDates,
  shiftDate,
} from "../format";

const HOUR_TICKS = ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"];

function periodLabel(period) {
  const minutes = (period - 1) * 30;
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

function axisMw(value) {
  return Number(value).toLocaleString("en-GB");
}

function chartTop(dataMax) {
  const max = Number(dataMax) || 0;
  return Math.ceil(max * 1.32);
}

function GenerationTip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const energy = row.errorMw == null ? null : row.errorMw * 0.5;
  return (
    <div className="tip">
      <p className="tip-title">
        {row.timeLabel} · SP{row.settlementPeriod}
      </p>
      <p>Forecast {formatMw(row.forecastMw)}</p>
      <p>Actual {formatMw(row.actualMw)}</p>
      <p>Energy error {formatMwh(energy, true)}</p>
    </div>
  );
}

export default function Decision() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("date") || "2026-01-15";
  const date = januaryDates().includes(requested) ? requested : "2026-01-15";
  const dayState = useJson(`/api/days/${date}`);
  const listState = useJson("/api/days");

  const labels = useMemo(() => {
    const map = new Map();
    for (const day of listState.data?.days || []) {
      map.set(day.date, day.energyErrorMwh);
    }
    return map;
  }, [listState.data]);

  function choose(next) {
    setParams({ date: next });
  }

  const day = dayState.data;
  const rows = (day?.points || []).map((point) => ({
    ...point,
    timeLabel: periodLabel(point.settlementPeriod),
  }));

  return (
    <section>
      <header className="page-head">
        <div>
          <p className="crumb">One delivery day</p>
          <h2>{formatDay(date)}</h2>
          <p className="lede">Wind forecast available for the day-ahead buy, against metered wind.</p>
        </div>
        <div className="toolbar">
          <button type="button" onClick={() => choose(shiftDate(date, -1))} disabled={date <= "2026-01-01"}>
            Previous
          </button>
          <label>
            <span className="sr">Delivery day</span>
            <select value={date} onChange={(event) => choose(event.target.value)}>
              {januaryDates().map((iso) => {
                const error = labels.get(iso);
                const suffix = error == null ? "" : ` · ${formatEnergy(error, true)}`;
                return (
                  <option key={iso} value={iso}>
                    {formatDay(iso)}
                    {suffix}
                  </option>
                );
              })}
            </select>
          </label>
          <button type="button" onClick={() => choose(shiftDate(date, 1))} disabled={date >= "2026-01-31"}>
            Next
          </button>
        </div>
      </header>

      <Status loading={dayState.loading} error={dayState.error}>
        {day ? (
          <>
            <div className="kpi-grid">
              <Kpi label="Forecast used for the buy" value={formatEnergy(day.summary.forecastMwh)} note="Published before the auction" />
              <Kpi label="Metered wind" value={formatEnergy(day.summary.actualMwh)} note="What actually generated" />
              <Kpi label="Difference" value={formatEnergy(day.summary.energyErrorMwh, true)} note="Same number as the chart. High and low hours can offset" />
              <Kpi label="Size of the misses" value={formatEnergy(day.summary.absoluteEnergyErrorMwh)} note="Every half-hour miss, added up" />
            </div>
            <p className="note" aria-live="polite">{firmCover(day.summary.energyErrorMwh)}</p>
            <div className="review-grid">
              <article className="card chart-card">
                <div className="card-head">
                  <h3>Through the delivery day</h3>
                  <p>Blue line is the forecast used for the buy. Grey area is metered wind. The number on the chart is that gap, added up.</p>
                </div>
                <div className="chart chart-day">
                  {day.summary.energyErrorMwh != null ? (
                    <div className="gap-badge">
                      <span>This gap</span>
                      <strong>{formatEnergy(day.summary.energyErrorMwh, true)}</strong>
                    </div>
                  ) : null}
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={rows} key={date}>
                      <CartesianGrid stroke="#e6edf5" vertical={false} />
                      <XAxis dataKey="timeLabel" ticks={HOUR_TICKS} tick={{ fill: "#64748b", fontSize: 12 }} axisLine={false} tickLine={false} />
                      <YAxis domain={[0, chartTop]} tickFormatter={axisMw} tick={{ fill: "#64748b", fontSize: 12 }} axisLine={false} tickLine={false} width={64} />
                      <Tooltip content={<GenerationTip />} />
                      <Legend />
                      <Area type="monotone" dataKey="actualMw" name="Metered wind" stroke="#5b7c99" fill="#dbe7f5" connectNulls={false} />
                      <Line type="stepAfter" dataKey="forecastMw" name="Forecast used for the buy" stroke="#1d4ed8" strokeWidth={2.4} dot={false} connectNulls={false} />
                      <Brush dataKey="timeLabel" height={22} stroke="#1d4ed8" travellerWidth={8} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </article>

              <div className="side-stack">
                <article className="card">
                  <div className="card-head">
                    <h3>Records for this day</h3>
                    <p>A missing half-hour is left blank. It is not treated as zero wind.</p>
                  </div>
                  <Coverage summary={day.summary} />
                </article>
                <article className="card vintage">
                  <p className="kicker">When the buy was made</p>
                  <p className="vintage-time">{formatStamp(day.forecastPublishTime)}</p>
                  <p>Forecast published. Auction assumed at {formatStamp(day.gateTime)}.</p>
                  <p className="fine">{GATE_ASSUMPTION}</p>
                </article>
              </div>
            </div>

            <article className="card">
              <div className="card-head">
                <h3>Half-hours</h3>
                <p>Difference for each half-hour is (forecast MW − metered MW) × 0.5 hours.</p>
              </div>
              <div className="table-wrap">
                <table className="navy">
                  <thead>
                    <tr>
                      <th>Period</th>
                      <th>Time</th>
                      <th>Forecast</th>
                      <th>Metered</th>
                      <th>Difference</th>
                      <th>Published</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.startTime}>
                        <td>{row.settlementPeriod}</td>
                        <td>{row.timeLabel}</td>
                        <td>{formatMw(row.forecastMw)}</td>
                        <td>{formatMw(row.actualMw)}</td>
                        <td>{formatMwh(row.errorMw == null ? null : row.errorMw * 0.5, true)}</td>
                        <td>{row.publishTime ? formatStamp(row.publishTime) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </>
        ) : null}
      </Status>
    </section>
  );
}
