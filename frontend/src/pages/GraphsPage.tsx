import { Download, MousePointer2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { api } from "../api/client";
import type { Aggregate, DaikinReading, Device, Measurement, SmartPlugReading, Tariff } from "../api/types";
import EChart from "../components/EChart";
import { useDaikinReadings, useDeviceState, useDevices, useMeasurements, useSmartPlugReadings } from "../hooks/useEnergy";
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
  daytimeSmall: number;
  daytimeLarge: number;
  daytimeCombined: number;
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
  energyDaytimeSmall: number | null;
  energyDaytimeLarge: number | null;
  energyDaytimeCombined: number | null;
  costTotal: number | null;
  costPc: number | null;
  costDaikin: number | null;
  costSmall: number | null;
  costLarge: number | null;
  costCombined: number | null;
  costOther: number | null;
  costDaytimeSmall: number | null;
  costDaytimeLarge: number | null;
  costDaytimeCombined: number | null;
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
  const parentsThermo = useMemo(() => findParentsThermoPlug(devices.data ?? []), [devices.data]);
  const computer = useSmartPlugReadings(sonoff?.id ?? null, query);
  const parentsThermoHistory = useSmartPlugReadings(parentsThermo?.id ?? null, query);
  const parentsThermoState = useDeviceState(parentsThermo?.id ?? null);
  const rows = (measurements.data?.data ?? []) as Measurement[] | Aggregate[];
  const rawRows = resolution === "raw" ? rows as Measurement[] : [];
  const periodRows = useMemo(() => {
    if (resolution === "raw") return rows.filter((row) => matchesPeriod(Date.parse((row as Measurement).timestamp_local || (row as Measurement).timestamp_utc), period)) as Measurement[];
    return rows.filter((row) => matchesPeriod(Date.parse((row as Aggregate).period_start_local), period)) as Aggregate[];
  }, [rows, resolution, period]);
  const daikinRows = daikin.data?.data ?? [];
  const computerRows = computer.data?.data ?? [];
  const parentsThermoRows = parentsThermoHistory.data?.data ?? [];
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
    if (resolution !== "raw") return aggregateOption(aggregatePoints, mode, range);
    return sourceOption(costPoints, mode, selecting, parentsThermoRows, range);
  }, [aggregatePoints, costPoints, mode, period, parentsThermoRows, range, resolution, selecting, tariff]);
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
            <p className="text-xs text-slate-500 dark:text-slate-400">{resolution === "raw" ? "Total Wibeee y cargas separadas: Sonoff medido, Daikin estimado y ciclos térmicos inferidos." : "En resoluciones agregadas se muestra el total; la separación por aparato requiere lecturas crudas."}</p>
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
        <p className="mt-2 text-xs text-slate-500">🌙 Fondo sombreado: noche de referencia, de 22:00 a 08:00. ☀️ El resto es día; estas horas no representan el amanecer y anochecer reales.</p>
        {sonoff && !computerRows.some((row) => row.online && row.power_w != null) ? <p className="mt-3 rounded-md bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-500/10 dark:text-amber-100">💻 El Sonoff del ordenador está identificado, pero no hay lecturas de potencia en este periodo. Su consumo queda incluido en «Otros».</p> : null}
        {parentsThermo ? <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100">
          <strong>Termo de tus padres · TP‑Link:</strong>{" "}
          {parentsThermoState.data?.online
            ? `ahora ${parentsThermoState.data.is_on ? "encendido" : "apagado"}. `
            : parentsThermoState.data ? "sin conexión con el enchufe. " : "consultando el estado actual. "}
          {parentsThermoRows.length
            ? `La gráfica muestra ${parentsThermoRows.length.toLocaleString("es-ES")} muestras históricas de estado. El TP‑Link no mide vatios; el estado por sí solo no confirma cuándo calienta el termo.`
            : "El servidor empieza a guardar el estado desde esta actualización; no hay histórico anterior del TP‑Link. No mide vatios, así que los picos de consumo se atribuyen por inferencia del Wibeee."}
        </div> : null}
        {selecting && resolution === "raw" ? <p className="text-xs text-sky-700 dark:text-sky-300">Arrastra sobre la gráfica para seleccionar un tramo. El coste se integra con las lecturas y el precio horario configurado.</p> : null}
        {selection && selectedCost != null ? <div className="mt-3 rounded-lg border border-sky-300 bg-sky-50 p-3 dark:border-sky-500/30 dark:bg-sky-500/10"><div className="text-xs text-slate-600 dark:text-slate-300">Intervalo: {selectedLabel}</div><div className="mt-1 text-lg font-semibold">Coste energético estimado: {formatMoney(selectedCost)}</div><div className="text-xs text-slate-600 dark:text-slate-300">{tariffRateSummary(tariff)} Tramos con huecos de más de 3 minutos no se extrapolan. Es coste equivalente de consumo; no descuenta autoconsumo/compensación ni incluye impuestos o costes fijos.</div></div> : null}
        <div className="mt-3 grid gap-2 text-xs text-slate-600 dark:text-slate-300 sm:grid-cols-2 xl:grid-cols-3">
          <span><b className="text-sky-500">Total vivienda</b> · Wibeee (medición)</span>
          <span><b className="text-emerald-500">Ordenador</b> · Sonoff (medición directa){sonoff ? " · enchufe identificado" : " · sin Sonoff identificado"}</span>
          <span><b className="text-red-500">♨️ Daikin</b> · estimación ONECTA</span>
          <span><b className="text-orange-600">🔥 Acumuladores</b> · dormitorio y comedor, inferidos por ciclos</span>
          <span><b className="text-blue-500">💧 Posibles termos</b> · picos inferidos; pueden ser otros aparatos.</span>
          <span><b className="text-slate-500">Resto</b> · diferencia estimada, no atribuida</span>
          <span><b>🔌 Termo padres (TP-Link)</b> · estado del enchufe, sin medición de potencia.</span>
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

function findParentsThermoPlug(devices: Device[]): Device | null {
  return devices.find((device) => device.active && device.config?.adapter === "kasa_hs100") ?? null;
}

function buildSourcePoints(rows: Measurement[], computerRows: SmartPlugReading[], daikinRows: DaikinReading[], cycles: AccumulatorCycle[], period: PeriodFilter): SourcePoint[] {
  const adjusted = adjustPowerSeries(rows, computerRows, daikinRows);
  const rowByTime = new Map(rows.map((row) => [Date.parse(row.timestamp_local || row.timestamp_utc), row]));
  const cycleAt = (time: number, category: AccumulatorCycle["category"], timeClass: AccumulatorCycle["timeClass"]) => cycles.filter((cycle) => cycle.timeClass === timeClass && cycle.category === category && time >= cycle.startMs && time < cycle.endMs).reduce((sum, cycle) => sum + cycle.deltaW, 0);
  return adjusted.filter((point) => matchesPeriod(point.timestamp, period)).map((point) => {
    const small = cycleAt(point.timestamp, "small", "overnight");
    const large = cycleAt(point.timestamp, "large", "overnight");
    const combined = cycleAt(point.timestamp, "combined", "overnight");
    const daytimeSmall = cycleAt(point.timestamp, "small", "daytime");
    const daytimeLarge = cycleAt(point.timestamp, "large", "daytime");
    const daytimeCombined = cycleAt(point.timestamp, "combined", "daytime");
    const pc = point.computerW ?? 0;
    const daikin = point.daikinW ?? 0;
    const measuredPc = Math.min(pc, Math.max(0, point.watts));
    const inferred = [daikin, small, large, combined, daytimeSmall, daytimeLarge, daytimeCombined];
    const inferredTotal = inferred.reduce((sum, value) => sum + value, 0);
    const remaining = Math.max(0, point.watts - measuredPc);
    const factor = inferredTotal > remaining && inferredTotal > 0 ? remaining / inferredTotal : 1;
    const components = [measuredPc, ...inferred.map((value) => value * factor)];
    return { time: point.timestamp, total: point.watts, pc: components[0], daikin: components[1], small: components[2], large: components[3], combined: components[4], daytimeSmall: components[5], daytimeLarge: components[6], daytimeCombined: components[7], other: Math.max(0, point.watts - components.reduce((sum, value) => sum + value, 0)), imported: rowByTime.get(point.timestamp)?.grid_import_w ?? 0 };
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
      energyDaytimeSmall: energy(before?.daytimeSmall ?? point.daytimeSmall, point.daytimeSmall),
      energyDaytimeLarge: energy(before?.daytimeLarge ?? point.daytimeLarge, point.daytimeLarge),
      energyDaytimeCombined: energy(before?.daytimeCombined ?? point.daytimeCombined, point.daytimeCombined),
      costTotal: cost(before?.total ?? point.total, point.total), costPc: cost(before?.pc ?? point.pc, point.pc),
      costDaikin: cost(before?.daikin ?? point.daikin, point.daikin), costSmall: cost(before?.small ?? point.small, point.small),
      costLarge: cost(before?.large ?? point.large, point.large), costCombined: cost(before?.combined ?? point.combined, point.combined),
      costOther: cost(before?.other ?? point.other, point.other),
      costDaytimeSmall: cost(before?.daytimeSmall ?? point.daytimeSmall, point.daytimeSmall),
      costDaytimeLarge: cost(before?.daytimeLarge ?? point.daytimeLarge, point.daytimeLarge),
      costDaytimeCombined: cost(before?.daytimeCombined ?? point.daytimeCombined, point.daytimeCombined)
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

function sourceOption(points: CostPoint[], mode: GraphMode, selecting: boolean, parentsThermoRows: SmartPlugReading[], range: string): EChartsOption {
  const series = [
    ["💻 Ordenador", "pc", "energyPc", "costPc"], ["♨️ Daikin · estimado", "daikin", "energyDaikin", "costDaikin"],
    ["🔥 Dormitorio · inferido", "small", "energySmall", "costSmall"], ["🔥 Comedor · inferido", "large", "energyLarge", "costLarge"],
    ["🔥 Combinado · inferido", "combined", "energyCombined", "costCombined"],
    ["💧 Posible termo ~1 kW", "daytimeSmall", "energyDaytimeSmall", "costDaytimeSmall"],
    ["💧 Posible termo ~2,5 kW", "daytimeLarge", "energyDaytimeLarge", "costDaytimeLarge"],
    ["💧 Posible carga combinada", "daytimeCombined", "energyDaytimeCombined", "costDaytimeCombined"],
    ["Otros · sin identificar", "other", "energyOther", "costOther"]
  ] as const;
  const color = ["#10b981", "#ef4444", "#ea580c", "#be123c", "#9f1239", "#3b82f6", "#1d4ed8", "#60a5fa", "#64748b"];
  const valueKey = (field: (typeof series)[number]) => mode === "power" ? field[1] : mode === "energy" ? field[2] : field[3];
  const totalValue = (point: CostPoint) => mode === "power" ? point.total : mode === "energy" ? point.energyTotal : point.costTotal;
  const unit = mode === "power" ? "W" : mode === "energy" ? "kWh" : "€";
  const seriesOptions: NonNullable<EChartsOption["series"]> = series.map((field, index) => ({ name: field[0], type: "bar", stack: "loads", barMaxWidth: 24, data: points.map((point) => [point.time, point[valueKey(field)]]), itemStyle: { color: color[index] } }));
  seriesOptions.push({ name: "Consumo total · Wibeee", type: "line", showSymbol: false, connectNulls: false, lineStyle: { width: 2.5, type: "solid" }, data: points.map((point) => [point.time, totalValue(point)]), itemStyle: { color: "#38bdf8" }, markArea: { silent: true, itemStyle: { color: "rgba(30, 41, 59, 0.12)" }, label: { show: true, position: "insideTopLeft", fontSize: 10, color: "#94a3b8", formatter: "🌙" }, data: nightBands(points) } });
  if (mode === "power") seriesOptions.push({ name: "Termo padres · TP‑Link (apagado/encendido)", type: "line", yAxisIndex: 1, step: "end", showSymbol: false, connectNulls: true, lineStyle: { width: 2, color: "#facc15" }, itemStyle: { color: "#facc15" }, data: [...parentsThermoRows].sort((a, b) => Date.parse(a.captured_at_utc) - Date.parse(b.captured_at_utc)).map((row) => [Date.parse(row.captured_at_utc), row.online && row.is_on != null ? Number(row.is_on) : null]) });
  return {
    color, tooltip: { trigger: "axis", valueFormatter: (value) => mode === "power" ? formatW(Number(value)) : mode === "energy" ? `${Number(value).toFixed(4)} kWh` : formatMoney(Number(value)) },
    legend: { type: "scroll", top: 0, textStyle: { color: "#cbd5e1" } }, grid: { top: 52, left: 75, right: mode === "power" ? 62 : 20, bottom: 70 },
    toolbox: { feature: { dataZoom: {}, saveAsImage: {} } }, dataZoom: [{ type: "inside" }, { type: "slider", height: 24 }],
    brush: selecting ? { brushType: "lineX", xAxisIndex: 0, brushMode: "single", transformable: false } : { brushType: false },
    xAxis: hourlyAxis(range),
    yAxis: mode === "power" ? [
      { type: "value", name: `Potencia · ${unit}`, min: 0, axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#334155" } } },
      { type: "value", name: "TP‑Link", min: 0, max: 1, interval: 1, position: "right", axisLabel: { color: "#facc15", formatter: (value: number) => value === 1 ? "ON" : "OFF" }, splitLine: { show: false } }
    ] : { type: "value", name: mode === "cost" ? "Coste por intervalo · €" : "Energía por intervalo · kWh", min: 0, axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#334155" } } },
    series: seriesOptions
  };
}

function aggregateOption(points: ReturnType<typeof buildAggregatePoints>, mode: GraphMode, range: string): EChartsOption {
  const isCost = mode === "cost";
  const isPower = mode === "power";
  const value = (point: ReturnType<typeof buildAggregatePoints>[number]) => isCost ? point.cost : isPower ? point.maxPower : point.energy;
  const name = isCost ? "Coste variable" : isPower ? "Potencia máxima" : "Consumo total";
  return {
    tooltip: { trigger: "axis", valueFormatter: (item) => isCost ? formatMoney(Number(item)) : isPower ? formatW(Number(item)) : `${Number(item).toFixed(3)} kWh` },
    legend: { top: 0 }, grid: { top: 48, left: 70, right: 20, bottom: 60 }, dataZoom: [{ type: "inside" }, { type: "slider", height: 22 }],
    xAxis: hourlyAxis(range), yAxis: { type: "value", name: isCost ? "Coste variable estimado · €" : isPower ? "Potencia máxima · W" : "Consumo · kWh", min: 0 },
    series: [{ name, type: "bar", barMaxWidth: 24, data: points.map((point) => [point.time, value(point)]), markArea: { silent: true, itemStyle: { color: "rgba(30, 41, 59, 0.12)" }, label: { show: true, position: "insideTopLeft", fontSize: 10, formatter: "🌙" }, data: nightBands(points) } }]
  };
}

function hourlyAxis(range: string): EChartsOption["xAxis"] {
  const interval = range === "1h" ? 5 * 60_000 : range === "week" ? 6 * 3_600_000 : range === "month" ? 24 * 3_600_000 : range === "year" ? 7 * 24 * 3_600_000 : 3_600_000;
  return { type: "time", minInterval: interval, maxInterval: interval, axisLabel: { color: "#94a3b8", hideOverlap: true }, splitLine: { show: true, lineStyle: { type: "dashed", color: "#64748b", opacity: 0.55 } } };
}

function nightBands(points: Array<{ time: number }>): Array<[{ xAxis: number }, { xAxis: number }]> {
  if (!points.length) return [];
  const first = points[0].time;
  const last = points[points.length - 1].time;
  if (last - first > 8 * 86_400_000) return [];
  const day = new Date(first);
  day.setHours(0, 0, 0, 0);
  day.setDate(day.getDate() - 1);
  const result: Array<[{ xAxis: number }, { xAxis: number }]> = [];
  while (day.getTime() <= last) {
    const start = new Date(day); start.setHours(22);
    const end = new Date(day); end.setDate(end.getDate() + 1); end.setHours(8);
    if (end.getTime() >= first) result.push([{ xAxis: Math.max(first, start.getTime()) }, { xAxis: Math.min(last, end.getTime()) }]);
    day.setDate(day.getDate() + 1);
  }
  return result;
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
