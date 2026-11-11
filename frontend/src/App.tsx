import { Suspense, lazy, useState } from "react";
import { Activity, BarChart3, BatteryCharging, Coins, Database, Home, Lightbulb, Moon, Plug, Sun, Tags, Thermometer } from "lucide-react";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const GraphsPage = lazy(() => import("./pages/GraphsPage"));
const MoneyPage = lazy(() => import("./pages/MoneyPage"));
const RawDataPage = lazy(() => import("./pages/RawDataPage"));
const AnnotationsPage = lazy(() => import("./pages/AnnotationsPage"));
const LightsPage = lazy(() => import("./pages/LightsPage"));
const PlugsPage = lazy(() => import("./pages/PlugsPage"));
const ClimatePage = lazy(() => import("./pages/ClimatePage"));
const AccumulatorsPage = lazy(() => import("./pages/AccumulatorsPage"));

type PageKey = "home" | "graphs" | "money" | "raw" | "annotations" | "lights" | "plugs" | "climate" | "accumulators";

const pages = [
  { key: "home" as const, label: "Inicio", icon: Home },
  { key: "graphs" as const, label: "Graficas", icon: BarChart3 },
  { key: "money" as const, label: "Energia y dinero", icon: Coins },
  { key: "lights" as const, label: "Luces", icon: Lightbulb },
  { key: "plugs" as const, label: "Enchufes", icon: Plug },
  { key: "climate" as const, label: "Clima Daikin", icon: Thermometer },
  { key: "accumulators" as const, label: "Acumuladores", icon: BatteryCharging },
  { key: "raw" as const, label: "Datos brutos", icon: Database },
  { key: "annotations" as const, label: "Analisis", icon: Tags }
];

export default function App() {
  const [page, setPage] = useState<PageKey>("home");
  const [dark, setDark] = useState(true);
  const ActivePage = {
    home: DashboardPage,
    graphs: GraphsPage,
    money: MoneyPage,
    lights: LightsPage,
    plugs: PlugsPage,
    climate: ClimatePage,
    accumulators: AccumulatorsPage,
    raw: RawDataPage,
    annotations: AnnotationsPage
  }[page];

  return (
    <div className={dark ? "dark" : ""}>
      <div className="min-h-screen bg-slate-50 text-slate-950 dark:bg-neutral-950 dark:text-slate-100">
        <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/90 backdrop-blur dark:border-white/10 dark:bg-neutral-950/90">
          <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-md bg-amber-500 text-white">
                <Activity className="h-5 w-5" aria-hidden />
              </div>
              <div>
                <h1 className="text-lg font-semibold tracking-normal">Energy Home Monitor</h1>
                <p className="text-xs text-slate-500 dark:text-slate-400">Solar compartida local</p>
              </div>
            </div>
            <nav className="flex gap-1 overflow-x-auto">
              {pages.map((item) => {
                const Icon = item.icon;
                const active = page === item.key;
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setPage(item.key)}
                    className={`flex min-h-10 items-center gap-2 rounded-md px-3 text-sm font-medium transition ${
                      active
                        ? "bg-slate-900 text-white dark:bg-white dark:text-slate-950"
                        : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/10"
                    }`}
                  >
                    <Icon className="h-4 w-4" aria-hidden />
                    <span className="whitespace-nowrap">{item.label}</span>
                  </button>
                );
              })}
              <button
                type="button"
                onClick={() => setDark((value) => !value)}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/10"
                title={dark ? "Modo claro" : "Modo oscuro"}
              >
                {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-5 sm:px-6">
          <Suspense fallback={<PageSkeleton label={pages.find((item) => item.key === page)?.label ?? "Cargando"} />}>
            <ActivePage />
          </Suspense>
        </main>
      </div>
    </div>
  );
}

function PageSkeleton({ label }: { label: string }) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-semibold tracking-normal">{label}</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400">Cargando pantalla...</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, index) => (
          <div key={index} className="metric animate-pulse">
            <div className="h-3 w-24 rounded bg-slate-200 dark:bg-white/10" />
            <div className="mt-3 h-7 w-28 rounded bg-slate-200 dark:bg-white/10" />
          </div>
        ))}
      </div>
    </div>
  );
}
