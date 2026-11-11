import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import { Thermometer, Wind, Zap } from "lucide-react";
import EChart from "../components/EChart";
import StatusPill from "../components/StatusPill";
import { useDaikinLatest, useDaikinReadings, useLatest } from "../hooks/useEnergy";
import type { DaikinReading } from "../api/types";
import { formatW } from "../utils/format";

const ranges = [
  ["24h", "24 horas", 1],
  ["7d", "7 días", 7],
  ["30d", "30 días", 30]
] as const;

export default function ClimatePage() {
  const [days, setDays] = useState(1);
  const params = useMemo(() => {
    const end = new Date();
    const start = new Date(end.getTime() - days * 24 * 60 * 60 * 1000);
    return `start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`;
  }, [days]);
  const latest = useDaikinLatest();
  const readings = useDaikinReadings(params);
  const meter = useLatest();
  const devices = latest.data?.data ?? [];
  const rows = readings.data?.data ?? [];

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">Clima Daikin</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Estado, temperaturas y consumo comunicado por ONECTA</p>
        </div>
        <div className="flex items-center gap-2">
          {latest.data?.configured ? <StatusPill ok={devices.length > 0} label={devices.length ? `${devices.length} equipos conectados` : "Esperando primera lectura"} /> : <StatusPill ok={false} label="Integración sin configurar" />}
        </div>
      </header>

      {latest.isSuccess && !latest.data.configured ? (
        <section className="panel p-5 text-sm text-slate-600 dark:text-slate-300">
          Activa `FEATURE_DAIKIN` y configura las credenciales ONECTA en el servidor para empezar a guardar lecturas.
        </section>
      ) : null}
      {latest.isError ? <section role="alert" className="panel p-4 text-sm text-rose-500">No se pudo consultar el estado Daikin: {latest.error.message}</section> : null}
      {latest.data?.configured && latest.isPending ? <section className="panel p-4 text-sm text-slate-500">Cargando los aires acondicionados…</section> : null}
      {latest.data?.configured && !latest.isPending && devices.length === 0 ? <section className="panel p-4 text-sm text-slate-500">Aún no hay lecturas guardadas. Comprueba que el worker tenga acceso a ONECTA y espera unos minutos.</section> : null}

      <div className="grid gap-4 xl:grid-cols-2">
        {devices.map((device) => <DaikinCard key={device.device_id} reading={device} />)}
      </div>

      <section className="panel p-4">
        <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-base font-semibold">Temperatura interior y exterior</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">Actualización según el intervalo de consulta a ONECTA</p>
          </div>
          <div className="flex gap-2">
            {ranges.map(([key, label, value]) => <button key={key} type="button" onClick={() => setDays(value)} className={`rounded-md px-3 py-2 text-sm ${days === value ? "bg-slate-900 text-white dark:bg-white dark:text-slate-950" : "bg-slate-100 dark:bg-white/10"}`}>{label}</button>)}
          </div>
        </div>
        {readings.isError ? <p role="alert" className="text-sm text-rose-500">No se pudo cargar el histórico: {readings.error.message}</p> : null}
        {readings.isPending ? <p className="text-sm text-slate-500">Cargando histórico…</p> : null}
        {!readings.isPending && rows.length === 0 ? <p className="text-sm text-slate-500">Todavía no hay histórico Daikin para este rango.</p> : null}
        {rows.length > 0 ? <EChart option={temperatureHistoryOption(rows)} height={340} /> : null}
      </section>

      <section className="panel p-4">
        <h3 className="mb-2 text-base font-semibold">Energía Daikin por día</h3>
        <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">Cada punto diario toma la última lectura disponible de cada unidad en ese día.</p>
        {rows.length > 0 ? <EChart option={dailyEnergyHistoryOption(rows)} height={280} /> : <p className="text-sm text-slate-500">Sin lecturas para el periodo.</p>}
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        {devices.map((device) => <DaikinEnergyCard key={`energy-${device.device_id}`} reading={device} />)}
      </section>

      <section className="panel flex items-start gap-3 p-4 text-sm text-slate-600 dark:text-slate-300">
        <Zap className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" aria-hidden />
        <p>
          Potencia actual de la vivienda: <strong>{formatW(meter.data?.house_consumption_w)}</strong>, medida por el Wibeee. ONECTA informa el consumo del aire en kWh por periodos, pero no publica potencia instantánea en W; la app no la estima ni la presenta como medida.
        </p>
      </section>
    </div>
  );
}

function DaikinCard({ reading }: { reading: DaikinReading }) {
  const energy = reading.energy_profiles?.day;
  return (
    <article className="panel space-y-4 p-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">{reading.device_name}</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">{reading.model ?? "Aire acondicionado"} · leído {new Date(reading.captured_at_utc).toLocaleTimeString("es-ES")}</p>
        </div>
        <StatusPill ok={reading.is_on === true && !reading.in_error_state} label={reading.in_error_state ? "Error" : reading.is_on ? "Encendido" : "Apagado"} />
      </header>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <ClimateMetric icon={Thermometer} label="Dentro" value={formatTemperature(reading.room_temperature_c)} detail="temperatura ambiente" />
        <ClimateMetric icon={Thermometer} label="Fuera" value={formatTemperature(reading.outdoor_temperature_c)} detail="temperatura exterior" />
        <ClimateMetric icon={Thermometer} label="Objetivo" value={formatTemperature(reading.target_temperature_c)} detail={modeLabel(reading.operating_mode)} />
        <ClimateMetric icon={Wind} label="Modo" value={modeLabel(reading.operating_mode)} detail={reading.fan_mode ? `Ventilador ${reading.fan_mode}` : "Velocidad no disponible"} />
        <ClimateMetric icon={Zap} label="Calefacción hoy" value={formatKwh(reading.heating_today_kwh)} detail="consumo comunicado por Daikin" />
        <ClimateMetric icon={Zap} label="Refrigeración hoy" value={formatKwh(reading.cooling_today_kwh)} detail="consumo comunicado por Daikin" />
      </div>
      {energy ? <div className="border-t border-slate-200 pt-3 dark:border-white/10"><p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Consumo por hora · hoy</p><EChart option={dailyEnergyOption(energy.heating_kwh, energy.cooling_kwh)} height={210} /></div> : null}
    </article>
  );
}

function DaikinEnergyCard({ reading }: { reading: DaikinReading }) {
  const profiles = reading.energy_profiles;
  const totals = [
    { label: "Hoy", profile: profiles?.day },
    { label: "Últimos 14 días", profile: profiles?.week },
    { label: "Últimos 24 meses", profile: profiles?.month }
  ];
  return (
    <section className="panel p-4">
      <h3 className="mb-3 text-base font-semibold">Energía Daikin · {reading.device_name}</h3>
      <div className="grid grid-cols-3 gap-2">
        {totals.map(({ label, profile }) => <div key={label} className="rounded-md bg-slate-100 p-3 dark:bg-white/5"><p className="text-xs text-slate-500 dark:text-slate-400">{label}</p><p className="mt-1 text-sm font-medium">🔥 {formatKwh(profile?.heating_total_kwh)}<br />❄️ {formatKwh(profile?.cooling_total_kwh)}</p></div>)}
      </div>
      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">Valores de energía acumulada kWh informados por el equipo; los periodos amplios reflejan el histórico disponible en ONECTA.</p>
    </section>
  );
}

function ClimateMetric({ icon: Icon, label, value, detail }: { icon: typeof Thermometer; label: string; value: string; detail: string }) {
  return <div className="rounded-md bg-slate-100 p-3 dark:bg-white/5"><div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400"><Icon className="h-4 w-4" aria-hidden />{label}</div><p className="mt-2 text-xl font-semibold">{value}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{detail}</p></div>;
}

function temperatureHistoryOption(rows: DaikinReading[]): EChartsOption {
  const devices = [...new Set(rows.map((row) => row.device_name))];
  const colors = ["#f97316", "#38bdf8", "#ec4899", "#34d399"];
  const series = devices.flatMap((name, index) => {
    const samples = rows.filter((row) => row.device_name === name).reverse();
    return [
      { name: `${name} · dentro`, type: "line" as const, showSymbol: false, connectNulls: false, data: samples.filter((row) => row.room_temperature_c != null).map((row) => [Date.parse(row.captured_at_utc), row.room_temperature_c]) },
      { name: `${name} · fuera`, type: "line" as const, showSymbol: false, connectNulls: false, lineStyle: { type: "dashed" as const }, data: samples.filter((row) => row.outdoor_temperature_c != null).map((row) => [Date.parse(row.captured_at_utc), row.outdoor_temperature_c]) }
    ].map((item, lineIndex) => ({ ...item, color: colors[(index * 2 + lineIndex) % colors.length] }));
  });
  return {
    color: colors,
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { top: 50, left: 55, right: 20, bottom: 60 },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 22 }],
    xAxis: { type: "time", axisLabel: { color: "#94a3b8" } },
    yAxis: { type: "value", name: "°C", axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#334155" } } },
    series
  };
}

function dailyEnergyOption(heating: number[], cooling: number[]): EChartsOption {
  const hours = Array.from({ length: Math.max(heating.length, cooling.length, 24) }, (_, index) => `${String(index).padStart(2, "0")}:00`);
  return {
    color: ["#f97316", "#38bdf8"],
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { top: 40, left: 50, right: 12, bottom: 35 },
    xAxis: { type: "category", data: hours, axisLabel: { color: "#94a3b8", interval: 3 } },
    yAxis: { type: "value", name: "kWh", axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#334155" } } },
    series: [
      { name: "Calefacción", type: "bar", stack: "energy", data: hours.map((_, index) => heating[index] ?? 0) },
      { name: "Refrigeración", type: "bar", stack: "energy", data: hours.map((_, index) => cooling[index] ?? 0) }
    ]
  };
}

function dailyEnergyHistoryOption(rows: DaikinReading[]): EChartsOption {
  const days = new Map<string, Map<string, { heating: number; cooling: number }>>();
  for (const row of [...rows].reverse()) {
    const key = new Date(row.captured_at_utc).toLocaleDateString("sv-SE");
    const perDevice = days.get(key) ?? new Map<string, { heating: number; cooling: number }>();
    perDevice.set(row.device_id, { heating: row.heating_today_kwh ?? 0, cooling: row.cooling_today_kwh ?? 0 });
    days.set(key, perDevice);
  }
  const labels = [...days.keys()].sort();
  const totalFor = (day: string, key: "heating" | "cooling") => [...(days.get(day)?.values() ?? [])].reduce((sum, item) => sum + item[key], 0);
  return {
    color: ["#f97316", "#38bdf8"],
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { top: 40, left: 55, right: 15, bottom: 40 },
    xAxis: { type: "category", data: labels, axisLabel: { color: "#94a3b8" } },
    yAxis: { type: "value", name: "kWh", axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#334155" } } },
    series: [
      { name: "Calefacción", type: "bar", stack: "daily-energy", data: labels.map((day) => totalFor(day, "heating")) },
      { name: "Refrigeración", type: "bar", stack: "daily-energy", data: labels.map((day) => totalFor(day, "cooling")) }
    ]
  };
}

function formatTemperature(value: number | null): string {
  return value == null ? "—" : `${value.toFixed(1)} °C`;
}

function formatKwh(value: number | null | undefined): string {
  return value == null ? "— kWh" : `${value.toFixed(2)} kWh`;
}

function modeLabel(value: string | null): string {
  const labels: Record<string, string> = { heating: "Calor", cooling: "Frío", auto: "Automático", fanOnly: "Solo ventilador", dry: "Deshumidificar", off: "Apagado" };
  return value ? labels[value] ?? value : "—";
}
