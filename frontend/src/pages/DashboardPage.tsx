import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowDownToLine, Zap } from "lucide-react";
import { api } from "../api/client";
import { useLatest } from "../hooks/useEnergy";
import { formatKwh, formatW } from "../utils/format";

const STALE_AFTER_SECONDS = 180;
const POWER_BAR_MAX_W = 5000;

export default function DashboardPage() {
  const latest = useLatest();
  const today = useQuery({ queryKey: ["summary", "day"], queryFn: () => api.summary("day"), refetchInterval: 60_000 });
  const data = latest.data;
  const summary = today.data;
  const totalToday = summary?.house_consumption_kwh ?? 0;
  const importedToday = summary?.grid_import_kwh ?? 0;
  const solarToday = summary?.solar_self_consumption_kwh ?? 0;
  const dayEnergyTotal = importedToday + solarToday;
  const gridTodayPercent = dayEnergyTotal > 0 ? importedToday / dayEnergyTotal * 100 : 0;
  const solarTodayPercent = dayEnergyTotal > 0 ? solarToday / dayEnergyTotal * 100 : 0;
  const stale = !data || !data.meter_online || data.seconds_since_last_reading > STALE_AFTER_SECONDS;
  const currentConsumption = data?.house_consumption_w ?? 0;
  const currentImport = data?.grid_import_w ?? 0;

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">Inicio</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Consumo de hoy y potencia en este momento</p>
        </div>
      </header>

      {stale ? (
        <div role="alert" className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
          <div><strong>El medidor no está actualizando.</strong> {data ? `Última lectura hace ${Math.max(0, Math.round(data.seconds_since_last_reading / 60))} min.` : latest.isError ? "No se pudo obtener una lectura reciente." : "Todavía no hay una lectura reciente."}</div>
        </div>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-3">
        <article className="panel p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400"><Zap className="h-4 w-4 text-amber-500" aria-hidden /> Consumo acumulado hoy</div>
          <div className="mt-3 text-3xl font-semibold tabular-nums">{summary ? formatKwh(totalToday) : "— kWh"}</div>
          <div className="mt-5 h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10" role="img" aria-label={`Consumo de hoy: ${gridTodayPercent.toFixed(0)} por ciento de red y ${solarTodayPercent.toFixed(0)} por ciento solar`}>
            <div className="flex h-full w-full">
              <div className="h-full bg-rose-500 transition-all" style={{ width: `${gridTodayPercent}%` }} />
              <div className="h-full bg-emerald-500 transition-all" style={{ width: `${solarTodayPercent}%` }} />
            </div>
          </div>
          <div className="mt-3 flex flex-wrap justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
            <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-rose-500" />Red {formatKwh(importedToday)}</span>
            <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-500" />Solar {formatKwh(solarToday)}</span>
          </div>
          {today.isError ? <p role="alert" className="mt-3 text-xs text-rose-500">No se pudo cargar el resumen de hoy.</p> : null}
        </article>

        <article className="panel p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400"><Zap className="h-4 w-4 text-amber-500" aria-hidden /> Consumo ahora</div>
          <div className="mt-3 text-3xl font-semibold tabular-nums">{formatW(data?.house_consumption_w)}</div>
          <div className="mt-5 h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10" role="meter" aria-label="Potencia consumida ahora" aria-valuemin={0} aria-valuemax={POWER_BAR_MAX_W} aria-valuenow={currentConsumption}>
            <div className="h-full rounded-full bg-amber-500 transition-all" style={{ width: `${barPercent(currentConsumption)}%` }} />
          </div>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">Potencia total de la vivienda · Wibeee</p>
        </article>

        <article className="panel p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400"><ArrowDownToLine className="h-4 w-4 text-rose-500" aria-hidden /> Importación de red ahora</div>
          <div className="mt-3 text-3xl font-semibold tabular-nums">{formatW(data?.grid_import_w)}</div>
          <div className="mt-5 h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10" role="meter" aria-label="Potencia importada de la red ahora" aria-valuemin={0} aria-valuemax={POWER_BAR_MAX_W} aria-valuenow={currentImport}>
            <div className="h-full rounded-full bg-rose-500 transition-all" style={{ width: `${barPercent(currentImport)}%` }} />
          </div>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">Parte del consumo cubierta por la red eléctrica</p>
        </article>
      </section>
    </div>
  );
}

function barPercent(value: number): number {
  return Math.min(100, Math.max(0, value / POWER_BAR_MAX_W * 100));
}
