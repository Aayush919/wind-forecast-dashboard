export function formatMw(value, signed = false) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const rounded = Math.round(Number(value));
  const body = Math.abs(rounded).toLocaleString("en-GB");
  if (!signed) return `${body} MW`;
  if (rounded > 0) return `+${body} MW`;
  if (rounded < 0) return `−${body} MW`;
  return "0 MW";
}

export function formatEnergy(mwh, signed = false) {
  if (mwh == null || Number.isNaN(Number(mwh))) return "—";
  const gwh = Math.round((Number(mwh) / 1000) * 10) / 10;
  const body = Math.abs(gwh).toLocaleString("en-GB", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  if (!signed) return `${body} GWh`;
  if (gwh > 0) return `+${body} GWh`;
  if (gwh < 0) return `−${body} GWh`;
  return "0.0 GWh";
}

export function formatDay(iso) {
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(`${iso}T12:00:00Z`));
}

export function formatStamp(iso) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZoneName: "short",
  }).format(new Date(iso));
}

export function formatMwh(mwh, signed = false) {
  if (mwh == null || Number.isNaN(Number(mwh))) return "—";
  const rounded = Math.round(Number(mwh));
  const body = Math.abs(rounded).toLocaleString("en-GB");
  if (!signed) return `${body} MWh`;
  if (rounded > 0) return `+${body} MWh`;
  if (rounded < 0) return `−${body} MWh`;
  return "0 MWh";
}

export function formatCount(value) {
  return Number(value).toLocaleString("en-GB");
}

export function januaryDates() {
  return Array.from({ length: 31 }, (_, index) => {
    const day = String(index + 1).padStart(2, "0");
    return `2026-01-${day}`;
  });
}

export function shiftDate(iso, days) {
  const next = new Date(`${iso}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + days);
  return next.toISOString().slice(0, 10);
}

export function firmCover(energyErrorMwh) {
  if (energyErrorMwh == null) {
    return "This delivery day has no matched forecast and outturn.";
  }
  const amount = formatEnergy(Math.abs(energyErrorMwh));
  if (energyErrorMwh > 0) {
    return `Wind was forecast ${amount} above outturn. Buying demand minus this forecast would have left the book short ${amount} of firm power.`;
  }
  if (energyErrorMwh < 0) {
    return `Wind was forecast ${amount} below outturn. Buying demand minus this forecast would have left the book long ${amount} of firm power.`;
  }
  return "Forecast energy and outturn energy matched on the half-hours scored here.";
}

export function errorColor(value) {
  if (value == null || value === 0) return "#c5ced8";
  return value > 0 ? "#c2410c" : "#1d4ed8";
}

export const GATE_ASSUMPTION =
  "Assumed decision time: 09:50 Europe/London on the morning before delivery. This is a business assumption for the day-ahead buy, not a timestamp from Elexon.";
