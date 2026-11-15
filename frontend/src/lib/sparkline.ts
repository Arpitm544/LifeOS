// Pure geometry for the Insights metric-card sparklines (PRD 6: value, label, 14-day sparkline).

/**
 * SVG polyline points for a series. Missing days (null) are skipped, so a gap stays a gap.
 * The y axis runs from 0 to the series maximum, or to `max` when given (values above it are clamped);
 * x spreads the days evenly.
 */
export function sparklinePoints(values: (number | null)[], width: number, height: number, max?: number) {
  const present = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!present.length) return "";
  const highest = max ?? Math.max(...present);
  const top = highest > 0 ? highest : 1;
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  const pad = 1; // keep the stroke inside the box
  return values.flatMap((value, index) => {
    if (typeof value !== "number" || !Number.isFinite(value)) return [];
    const x = values.length > 1 ? index * step : width / 2;
    const y = pad + (height - 2 * pad) * (1 - Math.min(1, Math.max(0, value) / top));
    return [`${round(x)},${round(y)}`];
  }).join(" ");
}

const round = (value: number) => Math.round(value * 10) / 10;

/** Caption under the plan adherence metric. Only blocks that have already ended are counted. */
export function adherenceCaption(endedBlocks: number) {
  return endedBlocks
    ? `Of ${endedBlocks} planned ${endedBlocks === 1 ? "block" : "blocks"} that ended in the last 14 days`
    : "Shows once a planned block has ended";
}
