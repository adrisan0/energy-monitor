import { Download, MousePointer2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { api } from "../api/client";
import type { Aggregate, DaikinReading, Device, Measurement, SmartPlugReading, Tariff } from "../api/types";
import EChart from "../components/EChart";
import { useDaikinReadings, useDevices, useMeasurements, useSmartPlugReadings } from "../hooks/useEnergy";
import { adjustPowerSeries, detectAccumulatorCycles, type AccumulatorCycle } from "../analytics/accumulators";
import { formatMoney, formatW, rangeQuery } from "../utils/format";

const ranges = [
  ["1h", "Última hora"], ["24h", "Últimas 24 h"], ["today", "Hoy"], ["yesterday", "Ayer"],
  ["week", "Semana"], ["month", "Mes"], ["year", "Año"]
];
type PeriodFilter = "all" | "day" | "night";
type GraphMode = "power" | "energy" | "cost";
interface SourcePoint {
  time: number;
  total: number;
  pc: number;
  daikin: number;
  small: number;
  large: number;
  combined: number;
  other: number;
  imported: number;
}
interface CostPoint extends SourcePoint {
  energyTotal: number | null;
  energyPc: number | null;
  energyDaikin: number | null;
  energySmall: number | null;
  energyLarge: number | null;
  energyCombined: number | null;
  energyOther: number | null;
  costTotal: number | null;
  costPc: number | null;
  costDaikin: number | null;
  costSmall: number | null;
  costLarge: number | null;
  costCombined: number | null;
  costOther: number | null;
}
type SelectedRange = { start: number; end: number } | null;

export default function GraphsPage() {
  const [range, setRange] = useState("24h");
  const [resolution, setResolution] = useState("raw");
  const [period, setPeriod] = useState<PeriodFilter>("all");
  const [mode, setMode] = useState<GraphMode>("power");
  const [selecting, setSelecting] = useState(false);
  const [selection, setSelection] = useState<SelectedRange>(null);
  const query = useMemo(() => rangeQuery(range), [range]);
  const measurements = useMeasurements(resolution, query);
  const devices = useDevices();
  const daikin = useDaikinReadings(query);
  const tariffQuery = useQuery({ queryKey: ["tariff"], queryFn: api.tariff, refetchInterval: 300_000 });
  const sonoff = useMemo(() => findComputerPlug(devices.data ?? []), [devices.data]);
  const computer = useSmartPlugReadings(sonoff?.id ?? null, query);
  const rows = (measurements.data?.data ?? []) as Measurement[] | Aggregate[];
  const rawRows = resolution === "raw" ? rows as Measurement[] : [];
  const periodRows = useMemo(() => {
    if (resolution === "raw") return rows.filter((row) => matchesPeriod(Date.parse((row as Measurement).timestamp_local || (row as Measurement).timestamp_utc), period)) as Measurement[];
    return rows.filter((row) => matchesPeriod(Date.parse((row as Aggregate).period_start_local), period)) as Aggregate[];
  }, [rows, resolution, period]);
  const daikinRows = daikin.data?.data ?? [];
  const computerRows = computer.data?.data ?? [];
  const tariff = tariffQuery.data;

  const cycles = useMemo(
    () => detectAccumulatorCycles(rawRows, computerRows, daikinRows, sonoff != null, daikinRows.length > 0),
    [rawRows, computerRows, daikinRows, sonoff]
  );
  const sourcePoints = useMemo(
    () => buildSourcePoints(rawRows, computerRows, daikinRows, cycles, period),
    [rawRows, computerRows, daikinRows, cycles, period]
  );
  const costPoints = useMemo(() => buildCostPoints(sourcePoints, tariff), [sourcePoints, tariff]);
  const aggregatePoints = useMemo(() => buildAggregatePoints(rows, resolution, period), [rows, resolution, period]);
  const selectedCost = useMemo(() => {
    if (!selection) return null;
    return costPoints.reduce((sum, point, index) => {
      const before = costPoints[index - 1];
      if (!before || before.time < selection.start || point.time > selection.end || point.costTotal == null) return sum;
      return sum + point.costTotal;
    }, 0);
  }, [selection, costPoints]);

  const line = useMemo<EChartsOption>(() => {
    if (resolution !== "raw") return aggregateOption(aggregatePoints, mode);
    return sourceOption(costPoints, mode, selecting);
  }, [aggregatePoints, costPoints, mode, period, resolution, selecting, tariff]);
  const brushEvents = useMemo(() => ({
    brushSelected: (event: unknown) => {
      const batches = (event as { batch?: Array<{ selected?: Array<{ dataIndex?: number[] }> }> }).batch ?? [];
      const indexes = batches.flatMap((batch) => batch.selected ?? []).flatMap((item) => item.dataIndex ?? []);
      if (!indexes.length) return;
      const ordered = [...new Set(indexes)].sort((a, b) => a - b);
      const first = costPoints[ordered[0]];
      const last = costPoints[ordered[ordered.length - 1]];
      if (first && last) setSelection({ start: first.time, end: last.time });
    }
  }), [costPoints]);
  const selectedLabel = selection ? `${new Date(selection.start).toLocaleString("es-ES")} – ${new Date(selection.end).toLocaleString("es-ES")}` : "";

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">Gráficas</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Consumo, coste y procedencia de las cargas conocidas e inferidas</p>
        </div>
        <a className="inline-flex h-10 items-center gap-2 rounded-md bg-slate-900 px-3 text-sm font-medium text-white dark:bg-white dark:text-slate-950" href={api.csvUrl(query)}>
          <Download className="h-4 w-4" aria-hidden /> CSV
        </a>
      </div>

      <div className="panel flex flex-col gap-3 p-3">
        <div className="flex flex-wrap gap-2">
          {ranges.map(([key, label]) => <button key={key} type="button" onClick={() => { setRange(key); setSelection(null); }} className={`rounded-md px-3 py-2 text-sm ${range === key ? "bg-slate-900 text-white dark:bg-white dark:text-slate-950" : "bg-slate-100 dark:bg-white/10"}`}>{label}</button>)}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Periodo horario">
            {([ ["all", "Todo el día"], ["day", "Diurno · 08–22"], ["night", "Nocturno · 22–08"] ] as Array<[PeriodFilter, string]>).map(([key, label]) => (
              <button key={key} type="button" aria-pressed={period === key} onClick={() => { setPeriod(key); setSelection(null); }} className={`rounded-md px-3 py-2 text-sm ${period === key ? "bg-sky-700 text-white" : "bg-slate-100 dark:bg-white/10"}`}>{label}</button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-md border p-1" role="group" aria-label="Magnitud de gráfica">
              <button type="button" aria-pressed={mode === "power"} onClick={() => setMode("power")} className={`rounded px-3 py-1.5 text-sm ${mode === "power" ? "bg-slate-900 text-white dark:bg-white dark:text-slate-950" : ""}`}>Potencia · W</button>
              <button type="button" aria-pressed={mode === "energy"} onClick={() => setMode("energy")} className={`rounded px-3 py-1.5 text-sm ${mode === "energy" ? "bg-slate-900 text-white dark:bg-white dark:text-slate-950" : ""}`}>Energía · kWh</button>
              <button type="button" aria-pressed={mode === "cost"} onClick={() => setMode("cost")} className={`rounded px-3 py-1.5 text-sm ${mode === "cost" ? "bg-slate-900 text-white dark:bg-white dark:text-slate-950" : ""}`}>Coste · €</button>
            </div>
            <select className="field" value={resolution} onChange={(event) => { setResolution(event.target.value); setSelection(null); }}>
              <option value="raw">Datos crudos</option><option value="minute">Minuto</option><option value="hour">Hora</option><option value="day">Día</option>
            </select>
          </div>
        </div>
      </div>

      <section className="panel p-4">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold">{mode === "power" ? "Potencia por procedencia" : mode === "energy" ? "Energía por procedencia" : "Coste por procedencia"}</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">{resolution === "raw" ? "Total Wibeee y cargas separadas: Sonoff medido, Daikin estimado y acumuladores inferidos." : "En resoluciones agregadas se muestra el total; la separación por aparato requiere lecturas crudas."}</p>
          </div>
          <div className="flex items-center gap-2">
            {resolution === "raw" && <button type="button" aria-pressed={selecting} onClick={() => { setSelecting((active) => !active); setSelection(null); }} className={`inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${selecting ? "border-sky-500 bg-sky-50 text-sky-900 dark:bg-sky-500/10 dark:text-sky-100" : ""}`}><MousePointer2 className="h-4 w-4" />{selecting ? "Arrastra en la gráfica" : "Seleccionar intervalo"}</button>}
            {selection && <button type="button" onClick={() => setSelection(null)} className="inline-flex items-center gap-1 rounded-md border px-2 py-2 text-sm"><X className="h-4 w-4" /> Limpiar</button>}
          </div>
        </div>
        {measurements.isPending ? <p className="text-sm text-slate-500">Cargando lecturas…</p> : null}
        {measurements.isError ? <p role="alert" className="text-sm text-rose-500">No se pudieron cargar las lecturas: {measurements.error.message}</p> : null}
        {!measurements.isPending && !measurements.isError && rows.length === 0 ? <p className="text-sm text-slate-500">No hay lecturas en este periodo.</p> : null}
        {rows.length > 0 ? <EChart option={line} height={430} onEvents={brushEvents} /> : null}
        {selecting && resolution === "raw" ? <p className="text-xs text-sky-700 dark:text-sky-300">Arrastra sobre la gráfica para seleccionar un tramo. El coste se integra con las lecturas y el precio horario configurado.</p> : null}
        {selection && selectedCost != null ? <div className="mt-3 rounded-lg border border-sky-300 bg-sky-50 p-3 dark:border-sky-500/30 dark:bg-sky-500/10"><div className="text-xs text-slate-600 dark:text-slate-300">Intervalo: {selectedLabel}</div><div className="mt-1 text-lg font-semibold">Coste energético estimado: {formatMoney(selectedCost)}</div><div className="text-xs text-slate-600 dark:text-slate-300">{tariffRateSummary(tariff)} Tramos con huecos de más de 3 minutos no se extrapolan. Es coste equivalente de consumo; no descuenta autoconsumo/compensación ni incluye impuestos o costes fijos.</div></div> : null}
        <div className="mt-3 grid gap-2 text-xs text-slate-600 dark:text-slate-300 sm:grid-cols-2 xl:grid-cols-3">
          <span><b className="text-sky-500">Total vivienda</b> · Wibeee (medición)</span>
          <span><b className="text-emerald-500">Ordenador</b> · Sonoff (medición directa){sonoff ? " · enchufe identificado" : " · sin Sonoff identificado"}</span>
          <span><b className="text-violet-500">Daikin</b> · estimación por variación de energía ONECTA</span>
          <span><b className="text-amber-500">Acumulador dormitorio</b> · inferido por ciclos</span>
          <span><b className="text-rose-500">Acumulador comedor</b> · inferido por ciclos</span>
          <span><b className="text-slate-500">Resto</b> · diferencia estimada, no atribuida</span>
          <span><b>Termo padres (TP-Link)</b> · solo estado; no mide vatios y no se le asigna consumo.</span>
        </div>
        {tariffQuery.isError ? <p className="mt-2 text-xs text-amber-700">No se pudo cargar la tarifa; no se calcula el coste.</p> : null}
        {!tariff ? <p className="mt-2 text-xs text-amber-700">Cargando precios configurados de la tarifa…</p> : <p className="mt-2 text-xs text-slate-500">Los importes se leen de Ajustes de tarifa; actualízalos allí cuando cambie tu contrato.</p>}
      </section>

    </div>
  );
}

function findComputerPlug(devices: Device[]): Device | null {
  const candidates = devices.filter((device) => device.active && device.measurement_capable && device.config?.adapter === "sonoff_s61s");
  return candidates.find((device) => /ordenador|computador|computer|\bpc\b/i.test(device.name)) ?? (candidates.length === 1 ? candidates[0] : null);
}

function buildSourcePoints(rows: Measurement[], computerRows: SmartPlugReading[], daikinRows: DaikinReading[], cycles: AccumulatorCycle[], period: PeriodFilter): SourcePoint[] {
  const adjusted = adjustPowerSeries(rows, computerRows, daikinRows);
  const rowByTime = new Map(rows.map((row) => [Date.parse(row.timestamp_local || row.timestamp_utc), row]));
  const cycleAt = (time: number, category: AccumulatorCycle["category"]) => cycles.filter((cycle) => cycle.category === category && time >= cycle.startMs && time < cycle.endMs).reduce((sum, cycle) => sum + cycle.deltaW, 0);
  return adjusted.filter((point) => matchesPeriod(point.timestamp, period)).map((point) => {
    const small = cycleAt(point.timestamp, "small");
    const large = cycleAt(point.timestamp, "large");
    const combined = cycleAt(point.timestamp, "combined");
    const pc = point.computerW ?? 0;
    const daikin = point.daikinW ?? 0;
    const known = pc + daikin + small + large + combined;
    const factor = known > point.watts && known > 0 ? point.watts / known : 1;
    const components = [pc, daikin, small, large, combined].map((value) => value * factor);
    return { time: point.timestamp, total: point.watts, pc: components[0], daikin: components[1], small: components[2], large: components[3], combined: components[4], other: Math.max(0, point.watts - components.reduce((sum, value) => sum + value, 0)), imported: rowByTime.get(point.timestamp)?.grid_import_w ?? 0 };
  });
}

function buildCostPoints(points: SourcePoint[], tariff?: Tariff): CostPoint[] {
  return points.map((point, index) => {
    const before = points[index - 1];
    const elapsed = before ? point.time - before.time : 0;
    const valid = Boolean(before && tariff && elapsed > 0 && elapsed <= 180_000);
    const hours = valid ? elapsed / 3_600_000 : 0;
    const rate = valid && tariff ? priceAt(tariff, (point.time + before!.time) / 2) : 0;
    const energy = (a: number, b: number) => valid ? ((a + b) / 2 / 1000) * hours : null;
    const cost = (a: number, b: number) => {
      const kwh = energy(a, b);
      return kwh == null ? null : kwh * rate;
    };
    return {
      ...point,
      energyTotal: energy(before?.total ?? point.total, point.total), energyPc: energy(before?.pc ?? point.pc, point.pc),
      energyDaikin: energy(before?.daikin ?? point.daikin, point.daikin), energySmall: energy(before?.small ?? point.small, point.small),
      energyLarge: energy(before?.large ?? point.large, point.large), energyCombined: energy(before?.combined ?? point.combined, point.combined),
      energyOther: energy(before?.other ?? point.other, point.other),
      costTotal: cost(before?.total ?? point.total, point.total), costPc: cost(before?.pc ?? point.pc, point.pc),
      costDaikin: cost(before?.daikin ?? point.daikin, point.daikin), costSmall: cost(before?.small ?? point.small, point.small),
      costLarge: cost(before?.large ?? point.large, point.large), costCombined: cost(before?.combined ?? point.combined, point.combined),
      costOther: cost(before?.other ?? point.other, point.other)
    };
  });
}

function buildAggregatePoints(rows: Array<Measurement | Aggregate>, resolution: string, period: PeriodFilter) {
  if (resolution === "raw") return [];
  return rows.map((row) => row as Aggregate).filter((row) => matchesPeriod(Date.parse(row.period_start_local), period)).map((row) => ({
    time: Date.parse(row.period_start_local), energy: row.house_consumption_kwh, maxPower: row.max_power_w,
    cost: row.estimated_cost_eur, label: row.period_start_local
  }));
}

function sourceOption(points: CostPoint[], mode: GraphMode, selecting: boolean): EChartsOption {
  const series = [
    ["Ordenador · Sonoff medido", "pc", "energyPc", "costPc"], ["Daikin · estimado", "daikin", "energyDaikin", "costDaikin"],
    ["Acumulador dormitorio · inferido", "small", "energySmall", "costSmall"], ["Acumulador comedor · inferido", "large", "energyLarge", "costLarge"],
    ["Acumuladores · combinado", "combined", "energyCombined", "costCombined"], ["Resto · sin atribuir", "other", "energyOther", "costOther"]
  ] as const;
  const color = ["#10b981", "#8b5cf6", "#f59e0b", "#ef4444", "#a855f7", "#64748b"];
  const valueKey = (field: (typeof series)[number]) => mode === "power" ? field[1] : mode === "energy" ? field[2] : field[3];
  const totalValue = (point: CostPoint) => mode === "power" ? point.total : mode === "energy" ? point.energyTotal : point.costTotal;
  const unit = mode === "power" ? "W" : mode === "energy" ? "kWh" : "€";
  const seriesOptions: NonNullable<EChartsOption["series"]> = series.map((field, index) => ({ name: field[0], type: "bar", stack: "loads", barMaxWidth: 24, data: points.map((point) => [point.time, point[valueKey(field)]]), itemStyle: { color: color[index] } }));
  seriesOptions.push({ name: "Consumo total · Wibeee", type: "line", showSymbol: false, connectNulls: false, lineStyle: { width: 2.5, type: "solid" }, data: points.map((point) => [point.time, totalValue(point)]), itemStyle: { color: "#38bdf8" } });
  return {
    color, tooltip: { trigger: "axis", valueFormatter: (value) => mode === "power" ? formatW(Number(value)) : mode === "energy" ? `${Number(value).toFixed(4)} kWh` : formatMoney(Number(value)) },
    legend: { top: 0, textStyle: { color: "#cbd5e1" } }, grid: { top: 52, left: 75, right: 20, bottom: 70 },
    toolbox: { feature: { dataZoom: {}, saveAsImage: {} } }, dataZoom: [{ type: "inside" }, { type: "slider", height: 24 }],
    brush: selecting ? { brushType: "lineX", xAxisIndex: 0, brushMode: "single", transformable: false } : { brushType: false },
    xAxis: { type: "time", axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#334155" } } },
    yAxis: { type: "value", name: mode === "cost" ? "Coste por intervalo · €" : mode === "energy" ? "Energía por intervalo · kWh" : `Potencia · ${unit}`, min: 0, axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#334155" } } },
    series: seriesOptions
  };
}

function aggregateOption(points: ReturnType<typeof buildAggregatePoints>, mode: GraphMode): EChartsOption {
  const isCost = mode === "cost";
  const isPower = mode === "power";
  const value = (point: ReturnType<typeof buildAggregatePoints>[number]) => isCost ? point.cost : isPower ? point.maxPower : point.energy;
  const name = isCost ? "Coste variable" : isPower ? "Potencia máxima" : "Consumo total";
  return {
    tooltip: { trigger: "axis", valueFormatter: (item) => isCost ? formatMoney(Number(item)) : isPower ? formatW(Number(item)) : `${Number(item).toFixed(3)} kWh` },
    legend: { top: 0 }, grid: { top: 48, left: 70, right: 20, bottom: 60 }, dataZoom: [{ type: "inside" }, { type: "slider", height: 22 }],
    xAxis: { type: "time", axisLabel: { color: "#94a3b8" } }, yAxis: { type: "value", name: isCost ? "Coste variable estimado · €" : isPower ? "Potencia máxima · W" : "Consumo · kWh", min: 0 },
    series: [{ name, type: "bar", barMaxWidth: 24, data: points.map((point) => [point.time, value(point)]) }]
  };
}

function matchesPeriod(timestamp: number, period: PeriodFilter): boolean {
  if (period === "all") return true;
  const hour = new Date(timestamp).getHours();
  return period === "day" ? hour >= 8 && hour < 22 : hour >= 22 || hour < 8;
}

function priceAt(tariff: Tariff, timestamp: number): number {
  const hour = new Date(timestamp).getHours();
  const day = new Date(timestamp).getDay();
  if (tariff.mode === "time_of_use" && day !== 0 && day !== 6) {
    if ((hour >= 10 && hour < 14) || (hour >= 18 && hour < 22)) return Number(tariff.peak_price_eur_per_kwh);
    if ((hour >= 8 && hour < 10) || (hour >= 14 && hour < 18) || (hour >= 22 && hour < 24)) return Number(tariff.shoulder_price_eur_per_kwh);
    return Number(tariff.valley_price_eur_per_kwh);
  }
  return Number(tariff.flat_price_eur_per_kwh);
}

function tariffRateSummary(tariff: Tariff | undefined): string {
  if (!tariff) return "No hay precios de tarifa disponibles.";
  const label = (value: string) => `${Number(value).toLocaleString("es-ES", { minimumFractionDigits: 3, maximumFractionDigits: 3 })} €/kWh`;
  if (tariff.mode !== "time_of_use") return `Usa el precio único guardado en la tarifa: ${label(tariff.flat_price_eur_per_kwh)}. `;
  return `Usa los precios guardados en la tarifa: valle ${label(tariff.valley_price_eur_per_kwh)} · llano ${label(tariff.shoulder_price_eur_per_kwh)} · punta ${label(tariff.peak_price_eur_per_kwh)}. `;
}
