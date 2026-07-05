import { BatteryCharging, Home, PlugZap, Sun } from "lucide-react";
import type { LatestResponse } from "../api/types";
import { formatW } from "../utils/format";

interface EnergyFlowProps {
  latest: LatestResponse | undefined;
}

export default function EnergyFlow({ latest }: EnergyFlowProps) {
  const solarToHome = latest?.solar_self_consumption_w ?? 0;
  const solarToGrid = latest?.grid_export_w ?? 0;
  const gridToHome = latest?.grid_import_w ?? 0;

  return (
    <section className="panel p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold">Flujo energetico</h2>
        <span className="text-sm text-slate-500 dark:text-slate-400">
          {latest ? new Date(latest.timestamp).toLocaleTimeString("es-ES") : "Sin lectura"}
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <FlowNode icon={Sun} label="Solar" value={formatW(latest?.solar_w)} tone="bg-amber-500" />
        <FlowNode icon={Home} label="Consumo conjunto" value={formatW(latest?.house_consumption_w)} tone="bg-red-500" />
        <FlowNode icon={PlugZap} label="Red" value={`${formatW(gridToHome)} / ${formatW(solarToGrid)}`} tone="bg-blue-600" />
      </div>
      <div className="mt-5 grid gap-3">
        <FlowLine label="Solar -> Consumo conjunto" value={solarToHome} color="bg-amber-500" />
        <FlowLine label="Solar -> Red" value={solarToGrid} color="bg-emerald-500" />
        <FlowLine label="Red -> Consumo conjunto" value={gridToHome} color="bg-blue-600" />
      </div>
    </section>
  );
}

function FlowNode({
  icon: Icon,
  label,
  value,
  tone
}: {
  icon: typeof BatteryCharging;
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-white/10">
      <div className="flex items-center gap-3">
        <span className={`flex h-9 w-9 items-center justify-center rounded-md text-white ${tone}`}>
          <Icon className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
          <p className="break-words text-lg font-semibold">{value}</p>
        </div>
      </div>
    </div>
  );
}

function FlowLine({ label, value, color }: { label: string; value: number; color: string }) {
  const active = value > 1;
  const width = Math.max(4, Math.min(100, value / 50));
  return (
    <div className={`rounded-md border p-3 ${active ? "border-slate-200 dark:border-white/10" : "border-dashed border-slate-200 opacity-45 dark:border-white/10"}`}>
      <div className="flex items-center justify-between gap-3 text-sm">
        <span>{label}</span>
        <span className="font-medium">{formatW(value)}</span>
      </div>
      <div className="mt-2 h-2 rounded-full bg-slate-100 dark:bg-white/10">
        <div className={`h-2 rounded-full ${color}`} style={{ width: active ? `${width}%` : "0%" }} />
      </div>
    </div>
  );
}
