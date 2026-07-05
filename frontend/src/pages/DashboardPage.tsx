import { BatteryCharging, Clock, Gauge, PlugZap, ShieldCheck, Sun, TrendingDown, Zap } from "lucide-react";
import EnergyFlow from "../components/EnergyFlow";
import MetricTile from "../components/MetricTile";
import StatusPill from "../components/StatusPill";
import { useLatest, useSystemStatus } from "../hooks/useEnergy";
import { formatW } from "../utils/format";

export default function DashboardPage() {
  const latest = useLatest();
  const status = useSystemStatus();
  const data = latest.data;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">Inicio</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Lecturas en tiempo casi real</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill ok={Boolean(data?.meter_online)} label={data?.meter_online ? "Medidor online" : "Medidor sin datos"} />
          <StatusPill ok={data?.data_quality === "valid"} label={`Calidad: ${data?.data_quality ?? "sin datos"}`} />
          {status.data?.simulation_mode ? <StatusPill ok label="Modo simulado" /> : null}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricTile label="Produccion solar" value={formatW(data?.solar_w)} icon={Sun} tone="solar" />
        <MetricTile label="Consumo total" value={formatW(data?.house_consumption_w)} icon={Zap} tone="load" />
        <MetricTile label="Importacion red" value={formatW(data?.grid_import_w)} icon={PlugZap} tone="grid" />
        <MetricTile label="Exportacion red" value={formatW(data?.grid_export_w)} icon={TrendingDown} tone="export" />
        <MetricTile label="Autoconsumo solar" value={formatW(data?.solar_self_consumption_w)} icon={BatteryCharging} tone="solar" />
        <MetricTile
          label="Autosuficiencia actual"
          value={data?.solar_self_consumption_percent == null ? "-- %" : `${data.solar_self_consumption_percent.toFixed(1)} %`}
          icon={Gauge}
          tone="neutral"
        />
        <MetricTile
          label="Ultima actualizacion"
          value={data ? new Date(data.timestamp).toLocaleTimeString("es-ES") : "--"}
          detail={data ? `${Math.round(data.seconds_since_last_reading)} s desde la lectura` : undefined}
          icon={Clock}
          tone="neutral"
        />
        <MetricTile label="Estado sistema" value={status.data?.database === "ok" ? "Operativo" : "Revisar"} icon={ShieldCheck} tone="neutral" />
      </div>

      <EnergyFlow latest={data} />

      <section className="grid gap-3 lg:grid-cols-3">
        <div className="panel p-4 lg:col-span-2">
          <h3 className="text-base font-semibold">Lectura interpretada</h3>
          <div className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
            <Info label="Solar" value={formatW(data?.solar_w)} />
            <Info label="Consumo conjunto" value={formatW(data?.house_consumption_w)} />
            <Info label="Red -> Consumo" value={formatW(data?.grid_import_w)} />
            <Info label="Solar -> Red" value={formatW(data?.grid_export_w)} />
          </div>
        </div>
        <div className="panel p-4">
          <h3 className="text-base font-semibold">Flags</h3>
          <div className="mt-4 space-y-2 text-sm">
            {Object.entries(status.data?.feature_flags ?? {}).map(([key, value]) => (
              <div key={key} className="flex items-center justify-between gap-3">
                <span>{key}</span>
                <span className={value ? "text-emerald-500" : "text-slate-500"}>{value ? "activo" : "inactivo"}</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-100 px-3 py-2 dark:bg-white/5">
      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  );
}
