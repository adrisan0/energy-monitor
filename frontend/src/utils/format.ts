export function formatW(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-- W";
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(2)} kW`;
  return `${Math.round(value)} W`;
}

export function formatKwh(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-- kWh";
  return `${value.toFixed(3)} kWh`;
}

export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-- EUR";
  return `${value.toFixed(2)} EUR`;
}

export function rangeQuery(range: string): string {
  const now = new Date();
  const start = new Date(now);
  if (range === "1h") start.setHours(now.getHours() - 1);
  if (range === "24h") start.setDate(now.getDate() - 1);
  if (range === "today") start.setHours(0, 0, 0, 0);
  if (range === "yesterday") {
    start.setDate(now.getDate() - 1);
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(start.getDate() + 1);
    return `start=${start.toISOString()}&end=${end.toISOString()}`;
  }
  if (range === "week") start.setDate(now.getDate() - 7);
  if (range === "month") start.setMonth(now.getMonth() - 1);
  if (range === "year") start.setFullYear(now.getFullYear() - 1);
  return `start=${start.toISOString()}&end=${now.toISOString()}`;
}
