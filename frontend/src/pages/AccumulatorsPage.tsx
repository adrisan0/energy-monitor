import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import EChart from "../components/EChart";
import type { Device, Measurement } from "../api/types";
import { useDaikinLatest, useDaikinReadings, useDevices, useMeasurements, useSmartPlugReadings } from "../hooks/useEnergy";
import { adjustPowerSeries, detectAccumulatorCycles, type AccumulatorCycle, type AdjustedPowerSample } from "../analytics/accumulators";
import { formatKwh, formatW } from "../utils/format";

export default function AccumulatorsPage() {
  const range = useMemo(() => monthToNow(), []);
  const readings = useMeasurements("raw", range);
  const devices = useDevices();
  const daikinLatest = useDaikinLatest();
  const daikinHistory = useDaikinReadings(range);
  const sonoffs = (devices.data ?? []).filter((device) => device.active && device.measurement_capable && device.config?.adapter === "sonoff_s61s");
  const computerPlug = sonoffs.find((device) => /ordenador|computador|computer|pc/i.test(device.name)) ?? (sonoffs.length === 1 ? sonoffs[0] : null);
  const computerHistory = useSmartPlugReadings(computerPlug?.id ?? null, range);
  const rows = (readings.data?.data ?? []) as Measurement[];
  const computerRows = computerHistory.data?.data ?? [];
  const daikinRows = daikinHistory.data?.data ?? [];
  const correctedSeries = useMemo(() => adjustPowerSeries(rows, computerRows, daikinRows), [rows, computerRows, daikinRows]);
  const cycles = useMemo(() => detectAccumulatorCycles(rows, computerRows, daikinRows, computerPlug != null, daikinLatest.data?.configured ?? false), [rows, computerRows, daikinRows, computerPlug, daikinLatest.data?.configured]);
  const nights = useMemo(() => [...new Set(cycles.map((cycle) => cycle.startNight))].sort(), [cycles]);
  const [selectedNight, setSelectedNight] = useState("");
  const night = nights.includes(selectedNight) ? selectedNight : nights.at(-1) ?? "";
  const nightCycles = cycles.filter((cycle) => cycle.startNight === night);
  const smallCycles = nightCycles.filter((cycle) => cycle.category === "small");
  const largeCycles = nightCycles.filter((cycle) => cycle.category === "large");
  const points = night ? selectNightSamples(correctedSeries, night) : [];
  const chart = useMemo(() => buildNightChart(points, nightCycles), [points, nightCycles]);
  const smallKwh = smallCycles.reduce((sum, cycle) => sum + cycle.energyKwh, 0);
  const largeKwh = largeCycles.reduce((sum, cycle) => sum + cycle.energyKwh, 0);
  const partialRows = rows.filter((row) => row.data_quality === "partial").length;
  const invalidRows = rows.filter((row) => row.data_quality === "invalid").length;
  const computerSamples = computerRows.filter((row) => row.online && row.power_w != null).length;

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">Acumuladores</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Ciclos probables inferidos del consumo total de la vivienda</p>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          <span className="label">Noche</span>
          <select className="field min-w-56" value={night} onChange={(event) => setSelectedNight(event.target.value)} disabled={!nights.length}>
            {nights.length ? nights.map((item) => <option key={item} value={item}>{nightLabel(item)}</option>) : <option value="">Sin ciclos detectados</option>}
          </select>
        </label>
      </header>

      {readings.isError ? <section role="alert" className="panel p-4 text-sm text-rose-500">No se pudo leer el histórico del medidor: {readings.error.message}</section> : null}
      {readings.isPending ? <section className="panel p-4 text-sm text-slate-500">Cargando histórico del medidor…</section> : null}
      {!readings.isPending && !readings.isError && rows.length === 0 ? <section className="panel p-4 text-sm text-slate-500">No hay muestras de consumo en este periodo.</section> : null}
      {rows.length > 0 && (partialRows > 0 || invalidRows > 0) ? <section className="rounded-lg border border-slate-300 bg-slate-100 p-3 text-xs text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">Calidad del histórico: {rows.length.toLocaleString("es-ES")} muestras; {partialRows.toLocaleString("es-ES")} parciales y {invalidRows.toLocaleString("es-ES")} inválidas. Los ciclos se infieren solo de las lecturas que contienen potencia total de la vivienda.</section> : null}

      <section className="grid gap-3 lg:grid-cols-2">
        <div className={`rounded-lg border p-3 text-sm ${computerSamples ? "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-100" : "border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100"}`}>
          <strong>Ordenador:</strong> {computerPlug ? computerSamples ? `resto su potencia en ${computerSamples.toLocaleString("es-ES")} lecturas Sonoff; si no hay muestra cercana, baja la confianza del ciclo.` : `identifiqué ${computerPlug.name}, pero aún no hay histórico Sonoff; en estas noches no puedo separar las horas que te quedas trabajando.` : "no hay un único Sonoff de medida identificado para corregir el ordenador."}
        </div>
        <div className="rounded-lg border border-slate-300 bg-slate-100 p-3 text-sm text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
          <strong>Daikin:</strong> {daikinRows.length ? `cruzo ${daikinRows.length.toLocaleString("es-ES")} estados y variaciones de energía; si el aire está activo o cambia justo en el salto, marco el candidato como ambiguo.` : daikinLatest.data?.configured ? "aún no hay lecturas históricas Daikin en este rango." : "ONECTA no está configurado en este servidor."}
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Ciclos pequeños · noche" value={`${smallCycles.length}`} detail="salto habitual medido ~1,5 kW" />
        <Metric label="Energía pequeña · estimada" value={formatKwh(smallKwh)} detail="solo tramos emparejados" />
        <Metric label="Ciclos grandes · noche" value={`${largeCycles.length}`} detail="salto habitual medido ~2,5 kW" />
        <Metric label="Energía grande · estimada" value={formatKwh(largeKwh)} detail="solo tramos emparejados" />
      </section>

      <section className="panel p-4">
        <div className="mb-3">
          <h3 className="text-base font-semibold">Perfil de potencia · {night ? nightLabel(night) : "sin noche seleccionada"}</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">Línea azul: potencia de la vivienda. Línea discontinua: resto estimado tras descontar Sonoff y la potencia media inferida de Daikin cuando hay lecturas fiables. Las bandas marcan ciclos candidatos.</p>
        </div>
        {nightCycles.length && points.length ? <EChart option={chart} height={390} /> : <p className="py-10 text-center text-sm text-slate-500">Todavía no hay ciclos emparejados en esta noche.</p>}
      </section>

      <section className="panel overflow-hidden p-4">
        <div className="mb-3">
          <h3 className="text-base font-semibold">Arranques y apagados detectados</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">Se agrupan saltos de potencia aunque cambien de hora. El consumo se estima como salto corregido × duración; la recurrencia muestra en cuántas otras noches aparece un salto parecido.</p>
        </div>
        {nightCycles.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs uppercase text-slate-500"><tr><th className="py-2">Inicio</th><th className="py-2">Fin</th><th className="py-2">Candidato</th><th className="py-2">Salto corregido</th><th className="py-2">Duración</th><th className="py-2">Energía aprox.</th><th className="py-2">Contexto</th><th className="py-2">Repetición</th><th className="py-2">Coherencia</th></tr></thead>
              <tbody>{nightCycles.map((cycle) => <CycleRow key={`${cycle.startMs}-${cycle.endMs}`} cycle={cycle} />)}</tbody>
            </table>
          </div>
        ) : <p className="text-sm text-slate-500">No hay ciclos confirmables para esta noche.</p>}
      </section>

      <aside className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100">
        <strong>Cómo leerlo:</strong> el histórico principal viene del Wibeee. El ordenador se corrige con su potencia Sonoff medida; Daikin se contrasta con sus estados y los incrementos de energía ONECTA. Los ciclos siguen siendo candidatos —no mediciones individuales de los acumuladores— y se buscan entre las 18:00 y las 10:00, sin exigir una hora fija de arranque.
      </aside>
    </div>
  );
}

function selectNightSamples(rows: AdjustedPowerSample[], night: string): AdjustedPowerSample[] {
  const start = new Date(`${night}T18:00:00`).getTime();
  const end = start + 16 * 60 * 60 * 1000;
  return rows.filter((row) => row.timestamp >= start && row.timestamp <= end);
}

function buildNightChart(points: AdjustedPowerSample[], cycles: AccumulatorCycle[]): EChartsOption {
  const colors: Record<AccumulatorCycle["category"], string> = { small: "rgba(245, 158, 11, 0.16)", large: "rgba(239, 68, 68, 0.15)", combined: "rgba(139, 92, 246, 0.16)" };
  const bands: Array<[{ name: string; xAxis: number; itemStyle: { color: string } }, { xAxis: number }]> = cycles.map((cycle) => [
    { name: cycleLabel(cycle.category), xAxis: cycle.startMs, itemStyle: { color: colors[cycle.category] } },
    { xAxis: cycle.endMs }
  ]);
  return {
    color: ["#38bdf8"],
    tooltip: { trigger: "axis", valueFormatter: (value) => `${formatW(Number(value))}` },
    legend: { top: 0 },
    grid: { top: 38, left: 65, right: 20, bottom: 55 },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 20 }],
    xAxis: { type: "time", min: points[0]?.timestamp, axisLabel: { color: "#94a3b8" } },
    yAxis: { type: "value", name: "Potencia total · W", min: 0, axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#334155" } } },
    series: [
      { name: "Consumo total", type: "line", showSymbol: false, connectNulls: false, lineStyle: { width: 1.2, type: "dashed" }, data: points.map((row) => [row.timestamp, row.watts]) },
      { name: "Resto estimado", type: "line", showSymbol: false, connectNulls: false, lineStyle: { width: 1.8 }, data: points.map((row) => [row.timestamp, row.adjustedW]) },
      { name: "Ciclos inferidos", type: "line", data: [], markArea: { silent: true, label: { show: true, position: "insideTop", fontSize: 10 }, data: bands } }
    ]
  };
}

function CycleRow({ cycle }: { cycle: AccumulatorCycle }) {
  const daikinContext = cycle.daikinTransitionNear ? "cambio Daikin cercano" : cycle.daikinActive ? "Daikin activo" : cycle.daikinStateKnown ? "Daikin apagado" : "Daikin sin dato";
  return <tr className="border-t border-slate-200 dark:border-white/10">
    <td className="py-2 pr-3">{new Date(cycle.startMs).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}</td>
    <td className="py-2 pr-3">{new Date(cycle.endMs).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}</td>
    <td className="py-2 pr-3">{cycleLabel(cycle.category)}</td>
    <td className="py-2 pr-3">{formatW(cycle.deltaW)}</td>
    <td className="py-2 pr-3">{Math.round(cycle.durationMinutes)} min</td>
    <td className="py-2 pr-3">{formatKwh(cycle.energyKwh)}</td>
    <td className="py-2 pr-3">{cycle.computerCorrected ? "PC descontado" : "PC sin dato"}; {daikinContext}</td>
    <td className="py-2 pr-3">{cycle.recurrenceNights} noches</td>
    <td className="py-2">{cycle.confidence}</td>
  </tr>;
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="metric"><p className="label">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{detail}</p></div>;
}

function cycleLabel(category: AccumulatorCycle["category"]): string {
  if (category === "small") return "Pequeño dormitorio · ~1 kW";
  if (category === "large") return "Grande comedor · ~2,5 kW";
  return "Combinado · revisar";
}

function nightLabel(date: string): string {
  const [year, month, day] = date.split("-").map(Number);
  return `Noche del ${new Date(year, month - 1, day).toLocaleDateString("es-ES", { day: "numeric", month: "long" })}`;
}

function monthToNow(): string {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  return `start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(now.toISOString())}`;
}
