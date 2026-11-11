import type { DaikinReading, Measurement, SmartPlugReading } from "../api/types";

export type AccumulatorClass = "small" | "large" | "combined";
export type LoadTimeClass = "overnight" | "daytime";

export interface AccumulatorCycle {
  startMs: number;
  endMs: number;
  deltaW: number;
  rawDeltaW: number;
  computerDeltaW: number;
  daikinDeltaW: number;
  durationMinutes: number;
  energyKwh: number;
  category: AccumulatorClass;
  timeClass: LoadTimeClass;
  confidence: "alta" | "media" | "baja";
  startNight: string;
  computerCorrected: boolean;
  daikinActive: boolean;
  daikinStateKnown: boolean;
  daikinTransitionNear: boolean;
  recurrenceNights: number;
}

export interface AdjustedPowerSample {
  timestamp: number;
  watts: number;
  computerW: number | null;
  daikinW: number | null;
  daikinOn: boolean | null;
  adjustedW: number;
}

interface Step {
  timestamp: number;
  deltaW: number;
  rawDeltaW: number;
  computerDeltaW: number;
  daikinDeltaW: number;
  computerCovered: boolean;
  daikinCovered: boolean;
  daikinOn: boolean;
  daikinStateKnown: boolean;
  daikinTransitionNear: boolean;
  decomposed?: boolean;
}

interface DaikinPowerInterval {
  startMs: number;
  endMs: number;
  watts: number;
}

const MAX_SAMPLE_GAP_MS = 240_000;
const MAX_REFERENCE_AGE_MS = 180_000;
const DAYTIME_START_HOUR = 10;
const DAYTIME_END_HOUR = 18;

/** Infer appliance-sized steps after correcting for measured or known household loads. */
export function detectAccumulatorCycles(
  rows: Measurement[],
  computerReadings: SmartPlugReading[] = [],
  daikinReadings: DaikinReading[] = [],
  computerMeteringConfigured = false,
  daikinConfigured = daikinReadings.length > 0
): AccumulatorCycle[] {
  const samples = adjustPowerSeries(rows, computerReadings, daikinReadings);
  const gaps = samples.flatMap((sample, index) => index > 0 && sample.timestamp - samples[index - 1].timestamp > MAX_SAMPLE_GAP_MS ? [sample.timestamp] : []);
  const daikin = [...daikinReadings].sort((a, b) => Date.parse(a.captured_at_utc) - Date.parse(b.captured_at_utc));
  const daikinTransitions = buildDaikinTransitions(daikin);

  const steps: Step[] = [];
  for (let i = 3; i < samples.length - 3; i += 1) {
    const window = samples.slice(i - 3, i + 4);
    if (window.some((sample, index) => index > 0 && sample.timestamp - window[index - 1].timestamp > MAX_SAMPLE_GAP_MS)) continue;

    const before = samples.slice(i - 3, i);
    const after = samples.slice(i + 1, i + 4);
    const rawDeltaW = median(after.map((sample) => sample.watts)) - median(before.map((sample) => sample.watts));
    const computerBefore = medianAvailable(before.map((sample) => sample.computerW));
    const computerAfter = medianAvailable(after.map((sample) => sample.computerW));
    const daikinBefore = medianAvailable(before.map((sample) => sample.daikinW));
    const daikinAfter = medianAvailable(after.map((sample) => sample.daikinW));
    const computerCovered = computerBefore != null && computerAfter != null;
    const daikinCovered = daikinBefore != null && daikinAfter != null;
    const computerDeltaW = computerCovered ? computerAfter - computerBefore : 0;
    const daikinDeltaW = daikinCovered ? daikinAfter - daikinBefore : 0;
    const deltaW = rawDeltaW - computerDeltaW - daikinDeltaW;
    if (Math.abs(deltaW) < 700 || Math.abs(deltaW) > 4500) continue;

    const previous = steps.at(-1);
    if (previous && Math.sign(previous.deltaW) === Math.sign(deltaW) && samples[i].timestamp - previous.timestamp < 180_000) {
      if (Math.abs(deltaW) > Math.abs(previous.deltaW)) {
        steps[steps.length - 1] = makeStep(samples[i].timestamp, deltaW, rawDeltaW, computerDeltaW, daikinDeltaW, computerCovered, daikinCovered, samples, i, daikinTransitions);
      }
      continue;
    }
    steps.push(makeStep(samples[i].timestamp, deltaW, rawDeltaW, computerDeltaW, daikinDeltaW, computerCovered, daikinCovered, samples, i, daikinTransitions));
  }

  // A simultaneous start can later end as two distinct steps. Only split it
  // when both complementary falls are observed without a telemetry gap.
  const expandedSteps = steps.flatMap((step, index) => {
    if (step.deltaW < 3150 || step.deltaW > 4500) return [step];
    const gapIndex = lowerBound(gaps, step.timestamp, (value) => value);
    const falls = steps.slice(index + 1).filter((end) => end.timestamp - step.timestamp <= 8 * 3_600_000 && end.deltaW < -700 && !(gaps[gapIndex] <= end.timestamp));
    const pairs = falls.flatMap((small) => falls
      .filter((large) => large !== small && -small.deltaW < 1950 && -large.deltaW >= 1950 && -large.deltaW < 3150)
      .map((large) => ({ small, large, error: Math.abs(step.deltaW + small.deltaW + large.deltaW) })));
    const pair = pairs.sort((a, b) => a.error - b.error)[0];
    if (!pair || pair.error > Math.max(350, step.deltaW * 0.18)) return [step];
    const { small, large } = pair;
    return [{ ...step, deltaW: -small.deltaW, decomposed: true }, { ...step, deltaW: -large.deltaW, decomposed: true }];
  });
  steps.splice(0, steps.length, ...expandedSteps);

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
      if (minutes > 480) break;
      if (minutes < 5) continue;
      // A matching edge after a telemetry outage cannot establish a continuous cycle.
      const gapIndex = lowerBound(gaps, start.timestamp, (value) => value);
      if (gaps[gapIndex] <= end.timestamp) continue;
      const difference = Math.abs(Math.abs(end.deltaW) - start.deltaW);
      if (difference > Math.max(350, start.deltaW * 0.23)) continue;
      const from = lowerBound(samples, start.timestamp);
      const to = lowerBound(samples, end.timestamp);
      const interval = samples.slice(from, to);
      // A paired fall hours later is not the same load if the intervening
      // measurements do not support a sustained plateau.
      if (!interval.length || interval.filter((sample) => sample.adjustedW < start.deltaW * 0.7).length / interval.length > 0.1) continue;
      matches.push({ index: j, error: difference + minutes * 0.4, minutes });
    }
    const match = matches.sort((a, b) => a.error - b.error)[0];
    if (!match) continue;
    const end = steps[match.index];
    used.add(i);
    used.add(match.index);
    const deltaW = (start.deltaW + Math.abs(end.deltaW)) / 2;
    const category: AccumulatorClass = deltaW < 1950 ? "small" : deltaW < 3150 ? "large" : "combined";
    const startHour = new Date(start.timestamp).getHours();
    const timeClass: LoadTimeClass = startHour >= DAYTIME_START_HOUR && startHour < DAYTIME_END_HOUR ? "daytime" : "overnight";
    const relativeError = Math.abs(start.deltaW - Math.abs(end.deltaW)) / deltaW;
    let confidence: AccumulatorCycle["confidence"] = match.minutes <= 60 && relativeError <= 0.18 ? "alta" : match.minutes <= 240 && relativeError <= 0.23 ? "media" : "baja";
    if (start.decomposed) confidence = "baja";
    if (start.daikinTransitionNear || end.daikinTransitionNear) confidence = "baja";
    else if (start.daikinOn || end.daikinOn) confidence = lowerConfidence(confidence, "media");
    if ((computerMeteringConfigured && (!start.computerCovered || !end.computerCovered)) ||
        (daikinConfigured && (!start.daikinCovered || !end.daikinCovered))) confidence = lowerConfidence(confidence, "media");
    if (!computerMeteringConfigured) confidence = lowerConfidence(confidence, "media");

    const startDate = new Date(start.timestamp);
    const startNight = timeClass === "daytime"
      ? localDateKey(startDate)
      : startDate.getHours() < 12 ? addDays(localDateKey(startDate), -1) : localDateKey(startDate);
    cycles.push({
      startMs: start.timestamp,
      endMs: end.timestamp,
      deltaW,
      rawDeltaW: (start.rawDeltaW + Math.abs(end.rawDeltaW)) / 2,
      computerDeltaW: (start.computerDeltaW + end.computerDeltaW) / 2,
      daikinDeltaW: (start.daikinDeltaW + end.daikinDeltaW) / 2,
      durationMinutes: match.minutes,
      energyKwh: deltaW * match.minutes / 60_000,
      category,
      timeClass,
      confidence,
      startNight,
      computerCorrected: start.computerCovered && end.computerCovered,
      daikinActive: start.daikinOn || end.daikinOn || daikinActiveDuring(daikin, start.timestamp, end.timestamp),
      daikinStateKnown: start.daikinStateKnown || end.daikinStateKnown,
      daikinTransitionNear: start.daikinTransitionNear || end.daikinTransitionNear,
      recurrenceNights: 0
    });
  }
  return addRecurrenceCounts(cycles);
}

export function adjustPowerSeries(
  rows: Measurement[],
  computerReadings: SmartPlugReading[] = [],
  daikinReadings: DaikinReading[] = []
): AdjustedPowerSample[] {
  const computer = computerReadings
    .map((row) => ({ timestamp: Date.parse(row.captured_at_utc), watts: row.online ? (row.is_on === false ? 0 : row.power_w) : null }))
    .filter((row) => Number.isFinite(row.timestamp) && row.watts != null)
    .sort((a, b) => a.timestamp - b.timestamp) as Array<{ timestamp: number; watts: number }>;
  const daikin = [...daikinReadings].sort((a, b) => Date.parse(a.captured_at_utc) - Date.parse(b.captured_at_utc));
  const daikinPower = buildDaikinPowerIntervals(daikin);
  return rows
    .filter((row): row is Measurement & { house_consumption_w: number } => Number.isFinite(row.house_consumption_w))
    .map((row) => {
      const timestamp = Date.parse(row.timestamp_local || row.timestamp_utc);
      const computerW = nearestValue(computer, timestamp, MAX_REFERENCE_AGE_MS);
      const daikinW = intervalValue(daikinPower, timestamp, MAX_REFERENCE_AGE_MS);
      const daikinOn = daikinStateAt(daikin, timestamp);
      return {
        timestamp,
        watts: row.house_consumption_w,
        computerW,
        daikinW,
        daikinOn,
        adjustedW: Math.max(0, row.house_consumption_w - (computerW ?? 0) - (daikinW ?? 0))
      };
    })
    .filter((row) => Number.isFinite(row.timestamp))
    .sort((a, b) => a.timestamp - b.timestamp);
}

function makeStep(
  timestamp: number,
  deltaW: number,
  rawDeltaW: number,
  computerDeltaW: number,
  daikinDeltaW: number,
  computerCovered: boolean,
  daikinCovered: boolean,
  samples: AdjustedPowerSample[],
  index: number,
  daikinTransitions: Array<{ timestamp: number; deviceId: string }>
): Step {
  const before = samples.slice(index - 3, index);
  const after = samples.slice(index + 1, index + 4);
  const daikinOn = [...before, ...after].some((sample: AdjustedPowerSample) => sample.daikinOn === true);
  const daikinStateKnown = [...before, ...after].some((sample: AdjustedPowerSample) => sample.daikinOn != null);
  const daikinTransitionNear = daikinTransitions.some((event) => Math.abs(event.timestamp - timestamp) <= 10 * 60_000);
  return { timestamp, deltaW, rawDeltaW, computerDeltaW, daikinDeltaW, computerCovered, daikinCovered, daikinOn, daikinStateKnown, daikinTransitionNear };
}

function buildDaikinPowerIntervals(rows: DaikinReading[]): DaikinPowerInterval[] {
  const byDevice = new Map<string, DaikinReading[]>();
  for (const row of rows) byDevice.set(row.device_id, [...(byDevice.get(row.device_id) ?? []), row]);
  const intervals: DaikinPowerInterval[] = [];
  for (const deviceRows of byDevice.values()) {
    const ordered = deviceRows.sort((a, b) => Date.parse(a.captured_at_utc) - Date.parse(b.captured_at_utc));
    for (let i = 1; i < ordered.length; i += 1) {
      const before = ordered[i - 1];
      const after = ordered[i];
      const startMs = Date.parse(before.captured_at_utc);
      const endMs = Date.parse(after.captured_at_utc);
      const elapsedMs = endMs - startMs;
      if (localDateKey(new Date(startMs)) !== localDateKey(new Date(endMs)) || elapsedMs < 2 * 60_000 || elapsedMs > 20 * 60_000) continue;
      const previousKwh = sumNullable(before.heating_today_kwh, before.cooling_today_kwh);
      const currentKwh = sumNullable(after.heating_today_kwh, after.cooling_today_kwh);
      if (previousKwh == null || currentKwh == null) continue;
      const deltaKwh = currentKwh - previousKwh;
      if (deltaKwh < 0) continue;
      const watts = deltaKwh * 3_600_000 / elapsedMs;
      if (watts <= 5000) intervals.push({ startMs, endMs, watts });
    }
  }
  return intervals.sort((a, b) => a.startMs - b.startMs);
}

function buildDaikinTransitions(rows: DaikinReading[]): Array<{ timestamp: number; deviceId: string }> {
  const byDevice = new Map<string, DaikinReading[]>();
  for (const row of rows) byDevice.set(row.device_id, [...(byDevice.get(row.device_id) ?? []), row]);
  const transitions: Array<{ timestamp: number; deviceId: string }> = [];
  for (const [deviceId, deviceRows] of byDevice) {
    const ordered = deviceRows.sort((a, b) => Date.parse(a.captured_at_utc) - Date.parse(b.captured_at_utc));
    for (let i = 1; i < ordered.length; i += 1) {
      if (ordered[i - 1].is_on != null && ordered[i].is_on != null && ordered[i - 1].is_on !== ordered[i].is_on) {
        transitions.push({ timestamp: Date.parse(ordered[i].captured_at_utc), deviceId });
      }
    }
  }
  return transitions;
}

function daikinStateAt(rows: DaikinReading[], timestamp: number): boolean | null {
  const states = rows
    .map((row) => ({ timestamp: Date.parse(row.captured_at_utc), on: row.is_on }))
    .filter((row) => row.on != null && row.timestamp <= timestamp && timestamp - row.timestamp <= 10 * 60_000)
    .sort((a, b) => b.timestamp - a.timestamp);
  return states[0]?.on ?? null;
}

function daikinActiveDuring(rows: DaikinReading[], start: number, end: number): boolean {
  return rows.some((row) => {
    const timestamp = Date.parse(row.captured_at_utc);
    return row.is_on === true && timestamp >= start - 10 * 60_000 && timestamp <= end + 10 * 60_000;
  });
}

function nearestValue(rows: Array<{ timestamp: number; watts: number }>, timestamp: number, maxAgeMs: number): number | null {
  const index = lowerBound(rows, timestamp);
  const candidates = [rows[index - 1], rows[index]].filter((row): row is { timestamp: number; watts: number } => row != null);
  const nearest = candidates.sort((a, b) => Math.abs(a.timestamp - timestamp) - Math.abs(b.timestamp - timestamp))[0];
  return nearest && Math.abs(nearest.timestamp - timestamp) <= maxAgeMs ? nearest.watts : null;
}

function intervalValue(rows: DaikinPowerInterval[], timestamp: number, edgeAllowanceMs: number): number | null {
  const index = lowerBound(rows, timestamp, (row) => row.startMs);
  const candidates = [rows[index - 1], rows[index]].filter((row): row is DaikinPowerInterval => row != null);
  const interval = candidates.find((row) => timestamp >= row.startMs - edgeAllowanceMs && timestamp <= row.endMs + edgeAllowanceMs);
  return interval?.watts ?? null;
}

function lowerBound<T>(rows: T[], value: number, key: (row: T) => number = (row) => (row as { timestamp: number }).timestamp): number {
  let low = 0;
  let high = rows.length;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (key(rows[mid]) < value) low = mid + 1;
    else high = mid;
  }
  return low;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function medianAvailable(values: Array<number | null>): number | null {
  const available = values.filter((value): value is number => value != null && Number.isFinite(value));
  return available.length >= 2 ? median(available) : null;
}

function sumNullable(first: number | null, second: number | null): number | null {
  return first == null && second == null ? null : (first ?? 0) + (second ?? 0);
}

function lowerConfidence(current: AccumulatorCycle["confidence"], cap: "media" | "baja"): AccumulatorCycle["confidence"] {
  if (cap === "baja" || current === "baja") return "baja";
  return "media";
}

function addRecurrenceCounts(cycles: AccumulatorCycle[]): AccumulatorCycle[] {
  return cycles.map((cycle) => {
    const minuteOfDay = new Date(cycle.startMs).getHours() * 60 + new Date(cycle.startMs).getMinutes();
    const matchingNights = new Set(cycles.filter((other) => {
      if (other === cycle || other.category !== cycle.category || other.timeClass !== cycle.timeClass || other.startNight === cycle.startNight) return false;
      if (Math.abs(other.deltaW - cycle.deltaW) > Math.max(400, cycle.deltaW * 0.2)) return false;
      const otherMinute = new Date(other.startMs).getHours() * 60 + new Date(other.startMs).getMinutes();
      const gap = Math.abs(otherMinute - minuteOfDay);
      return Math.min(gap, 1440 - gap) <= 360;
    }).map((other) => other.startNight));
    return { ...cycle, recurrenceNights: matchingNights.size };
  });
}

function localDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function addDays(dateKey: string, amount: number): string {
  const [year, month, day] = dateKey.split("-").map(Number);
  const date = new Date(year, month - 1, day + amount);
  return localDateKey(date);
}
