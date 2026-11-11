import type { Measurement } from "../api/types";

export type AccumulatorClass = "small" | "large" | "combined";

export interface AccumulatorCycle {
  startMs: number;
  endMs: number;
  deltaW: number;
  offDeltaW: number;
  durationMinutes: number;
  energyKwh: number;
  category: AccumulatorClass;
  confidence: "alta" | "media" | "baja";
  startNight: string;
}

interface Step {
  timestamp: number;
  deltaW: number;
  beforeW: number;
  afterW: number;
}

const MAX_SAMPLE_GAP_MS = 150_000;

/** Infer appliance-sized step changes from whole-home power; this is an estimate, not a direct device reading. */
export function detectAccumulatorCycles(rows: Measurement[]): AccumulatorCycle[] {
  const samples = rows
    .filter((row): row is Measurement & { house_consumption_w: number } => Number.isFinite(row.house_consumption_w))
    .map((row) => ({ timestamp: Date.parse(row.timestamp_local || row.timestamp_utc), watts: row.house_consumption_w }))
    .filter((row) => Number.isFinite(row.timestamp))
    .sort((a, b) => a.timestamp - b.timestamp);

  const steps: Step[] = [];
  for (let i = 3; i < samples.length - 3; i += 1) {
    const hour = new Date(samples[i].timestamp).getHours();
    if (hour >= 9 && hour < 23) continue;
    const window = samples.slice(i - 3, i + 4);
    if (window.some((sample, index) => index > 0 && sample.timestamp - window[index - 1].timestamp > MAX_SAMPLE_GAP_MS)) continue;
    const beforeW = median(samples.slice(i - 3, i).map((sample) => sample.watts));
    const afterW = median(samples.slice(i + 1, i + 4).map((sample) => sample.watts));
    const deltaW = afterW - beforeW;
    if (Math.abs(deltaW) < 700 || Math.abs(deltaW) > 4500) continue;

    const previous = steps.at(-1);
    if (previous && Math.sign(previous.deltaW) === Math.sign(deltaW) && samples[i].timestamp - previous.timestamp < 180_000) {
      if (Math.abs(deltaW) > Math.abs(previous.deltaW)) steps[steps.length - 1] = { timestamp: samples[i].timestamp, deltaW, beforeW, afterW };
      continue;
    }
    steps.push({ timestamp: samples[i].timestamp, deltaW, beforeW, afterW });
  }

  const used = new Set<number>();
  const cycles: AccumulatorCycle[] = [];
  for (let i = 0; i < steps.length; i += 1) {
    const start = steps[i];
    if (start.deltaW <= 0 || used.has(i)) continue;
    const matches: Array<{ index: number; error: number; minutes: number }> = [];
    for (let j = i + 1; j < steps.length; j += 1) {
      const end = steps[j];
      if (end.deltaW >= 0 || used.has(j)) continue;
      const minutes = (end.timestamp - start.timestamp) / 60_000;
      if (minutes < 5 || minutes > 480) continue;
      const difference = Math.abs(Math.abs(end.deltaW) - start.deltaW);
      if (difference <= Math.max(350, start.deltaW * 0.23)) matches.push({ index: j, error: difference + minutes * 0.4, minutes });
    }
    const match = matches.sort((a, b) => a.error - b.error)[0];
    if (!match) continue;
    const end = steps[match.index];
    used.add(i);
    used.add(match.index);
    const deltaW = (start.deltaW + Math.abs(end.deltaW)) / 2;
    const category: AccumulatorClass = deltaW < 1950 ? "small" : deltaW < 3100 ? "large" : "combined";
    const relativeError = Math.abs(start.deltaW - Math.abs(end.deltaW)) / deltaW;
    const confidence = match.minutes <= 60 && relativeError <= 0.18 ? "alta" : match.minutes <= 240 && relativeError <= 0.23 ? "media" : "baja";
    const startDate = new Date(start.timestamp);
    const startNight = startDate.getHours() < 9 ? addDays(localDateKey(startDate), -1) : localDateKey(startDate);
    cycles.push({
      startMs: start.timestamp,
      endMs: end.timestamp,
      deltaW,
      offDeltaW: Math.abs(end.deltaW),
      durationMinutes: match.minutes,
      energyKwh: deltaW * match.minutes / 60_000,
      category,
      confidence,
      startNight
    });
  }
  return cycles.sort((a, b) => a.startMs - b.startMs);
}

export function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function localDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function addDays(dateKey: string, amount: number): string {
  const [year, month, day] = dateKey.split("-").map(Number);
  const date = new Date(year, month - 1, day + amount);
  return localDateKey(date);
}
