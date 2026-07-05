import type { LucideIcon } from "lucide-react";

interface MetricTileProps {
  label: string;
  value: string;
  detail?: string;
  icon: LucideIcon;
  tone: "solar" | "grid" | "export" | "load" | "neutral";
}

const tones = {
  solar: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  grid: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
  export: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  load: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300",
  neutral: "bg-slate-100 text-slate-700 dark:bg-white/10 dark:text-slate-200"
};

export default function MetricTile({ label, value, detail, icon: Icon, tone }: MetricTileProps) {
  return (
    <div className="metric min-h-32">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label">{label}</p>
          <p className="mt-2 break-words text-3xl font-semibold tracking-normal">{value}</p>
        </div>
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md ${tones[tone]}`}>
          <Icon className="h-5 w-5" aria-hidden />
        </div>
      </div>
      {detail ? <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">{detail}</p> : null}
    </div>
  );
}
