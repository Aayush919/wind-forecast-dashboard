import { useNavigate } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useJson } from "../api";
import Coverage from "../components/Coverage";
import { Kpi, Status } from "../components/Kpi";
import {
  errorColor,
  firmCover,
  formatDay,
  formatEnergy,
  formatMw,
  GATE_ASSUMPTION,
} from "../format";

function axisMw(value) {
  return Number(value).toLocaleString("en-GB");
}

function DayTip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="tip">
      <p className="tip-title">{formatDay(row.date)}</p>
      <p>Energy error {formatEnergy(row.energyErrorMwh, true)}</p>
      <p>Absolute energy error {formatEnergy(row.absoluteEnergyErrorMwh)}</p>
      <p>Bias {formatMw(row.biasMw, true)}</p>
      <p>MAE {formatMw(row.maeMw)}</p>
    </div>
  );
}

function PeriodTip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="tip">
      <p className="tip-title">
        {row.label} · SP{row.settlementPeriod}
      </p>
      <p>Bias {formatMw(row.biasMw, true)}</p>
      <p>MAE {formatMw(row.maeMw)}</p>
      <p>Matched half-hours {row.paired}</p>
    </div>
  );
}

export default function Accuracy() {
  const navigate = useNavigate();
  const state = useJson("/api/accuracy");
  const accuracy = state.data;

  const worst = accuracy
    ? [...accuracy.byDay]
        .filter((day) => day.absoluteEnergyErrorMwh != null)
        .sort((a, b) => b.absoluteEnergyErrorMwh - a.absoluteEnergyErrorMwh)
        .slice(0, 8)
    : [];

  function openDay(date) {
    if (date) navigate(`/review?date=${date}`);
  }

  return (
    <section>
      <header className="page-head">
        <div>
          <p className="crumb">Whole month</p>
          <h2>January accuracy</h2>
          <p className="lede">How far the forecast used for each buy sat from metered wind.</p>
        </div>
      </header>

      <Status loading={state.loading} error={state.error}>
        {accuracy ? (
          <>
            <div className="kpi-grid five">
              <Kpi label="Average difference" value={formatMw(accuracy.biasMw, true)} note="Forecast minus metered, averaged" />
              <Kpi label="Typical miss" value={formatMw(accuracy.maeMw)} note="Average size of the half-hour error" />
              <Kpi label="RMSE" value={formatMw(accuracy.rmseMw)} note="Gives more weight to big misses" />
              <Kpi label="Difference" value={formatEnergy(accuracy.energyErrorMwh, true)} note="High and low hours can offset" />
              <Kpi label="Size of the misses" value={formatEnergy(accuracy.absoluteEnergyErrorMwh)} note="Every half-hour miss, added up" />
            </div>
            <p className="note">
              {firmCover(accuracy.energyErrorMwh)} The size of the misses is {formatEnergy(accuracy.absoluteEnergyErrorMwh)}, because a high hour does not cancel a low hour.
              Nine in ten half-hours had a signed error between {formatMw(accuracy.p10Mw, true)} and {formatMw(accuracy.p90Mw, true)}.
            </p>
            <div className="review-grid">
              <article className="card">
                <div className="card-head">
                  <h3>Records in January</h3>
                  <p>Only half-hours with both a forecast and a meter reading go into the scores.</p>
                </div>
                <Coverage summary={accuracy} />
              </article>
              <article className="card vintage">
                <p className="kicker">How to read a day</p>
                <p>Click a day to open its forecast, the one used for that buy.</p>
                <p className="fine">{GATE_ASSUMPTION}</p>
              </article>
            </div>

            <article className="card">
              <div className="card-head">
                <h3>Difference by delivery day</h3>
                <p>Click a bar to open that day. Orange: forecast above metered wind. Blue: forecast below it.</p>
              </div>
              <div className="chart">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={accuracy.byDay} onClick={(bar) => openDay(bar?.activePayload?.[0]?.payload?.date)}>
                    <CartesianGrid stroke="#e6edf5" vertical={false} />
                    <XAxis dataKey="date" tickFormatter={(value) => value.slice(8)} interval={0} tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tickFormatter={(value) => `${Math.round(value / 1000)}`} tick={{ fill: "#64748b", fontSize: 12 }} axisLine={false} tickLine={false} width={36} />
                    <Tooltip content={<DayTip />} />
                    <ReferenceLine y={0} stroke="#0e2a4a" />
                    <Bar dataKey="energyErrorMwh" cursor="pointer" radius={[2, 2, 0, 0]}>
                      {accuracy.byDay.map((day) => (
                        <Cell key={day.date} fill={errorColor(day.energyErrorMwh)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </article>

            <article className="card">
              <div className="card-head">
                <h3>Difference by time of day</h3>
                <p>Each bar is one half-hour, from 00:00 London. The height is the average difference across January.</p>
              </div>
              <div className="chart chart-short">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={accuracy.byPeriod}>
                    <CartesianGrid stroke="#e6edf5" vertical={false} />
                    <XAxis dataKey="label" ticks={["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"]} tick={{ fill: "#64748b", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis tickFormatter={axisMw} tick={{ fill: "#64748b", fontSize: 12 }} axisLine={false} tickLine={false} width={64} />
                    <Tooltip content={<PeriodTip />} />
                    <ReferenceLine y={0} stroke="#0e2a4a" />
                    <Bar dataKey="biasMw" radius={[2, 2, 0, 0]}>
                      {accuracy.byPeriod.map((period) => (
                        <Cell key={period.settlementPeriod} fill={errorColor(period.biasMw)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </article>

            <article className="card">
              <div className="card-head">
                <h3>Days with the largest misses</h3>
                <p>Sorted by the size of the misses, so a day that was high and low still shows the full miss.</p>
              </div>
              <div className="table-wrap">
                <table className="navy">
                  <thead>
                    <tr>
                      <th>Delivery day</th>
                      <th>Difference</th>
                      <th>Size of the misses</th>
                      <th>Average difference</th>
                      <th>Typical miss</th>
                      <th>Forecast missing</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {worst.map((day) => (
                      <tr key={day.date}>
                        <td>{formatDay(day.date)}</td>
                        <td>{formatEnergy(day.energyErrorMwh, true)}</td>
                        <td>{formatEnergy(day.absoluteEnergyErrorMwh)}</td>
                        <td>{formatMw(day.biasMw, true)}</td>
                        <td>{formatMw(day.maeMw)}</td>
                        <td>{day.missingForecastIntervals}</td>
                        <td>
                          <button type="button" onClick={() => openDay(day.date)}>Open day</button>
                        </td>
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
