import { Download } from "lucide-react";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Aggregate, Measurement } from "../api/types";
import EChart from "../components/EChart";
import { flowAreaOption, heatmapOption, hourlyBarOption, powerLineOption } from "../charts/options";
import { rangeQuery } from "../utils/format";
import { useMeasurements } from "../hooks/useEnergy";

const ranges = [
  ["1h", "Ultima hora"],
  ["24h", "Ultimas 24 h"],
  ["today", "Hoy"],
  ["yesterday", "Ayer"],
  ["week", "Semana"],
  ["month", "Mes"],
  ["year", "Ano"]
];

export default function GraphsPage() {
  const [range, setRange] = useState("24h");
  const [resolution, setResolution] = useState("raw");
  const query = rangeQuery(range);
  const measurements = useMeasurements(resolution, query);
  const events = useQuery({ queryKey: ["events"], queryFn: api.events, refetchInterval: 60_000 });
  const rows = (measurements.data?.data ?? []) as Measurement[] | Aggregate[];

  const line = useMemo(() => powerLineOption(rows, resolution), [rows, resolution]);
  const area = useMemo(() => flowAreaOption(rows, resolution), [rows, resolution]);
  const bars = useMemo(() => hourlyBarOption(rows, resolution), [rows, resolution]);
  const heatmap = useMemo(() => heatmapOption(rows, resolution), [rows, resolution]);

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">Graficas</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Datos reales y agregados</p>
        </div>
        <a className="inline-flex h-10 items-center gap-2 rounded-md bg-slate-900 px-3 text-sm font-medium text-white dark:bg-white dark:text-slate-950" href={api.csvUrl(query)}>
          <Download className="h-4 w-4" aria-hidden />
          CSV
        </a>
      </div>

      <div className="panel flex flex-col gap-3 p-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2">
          {ranges.map(([key, label]) => (
            <button key={key} type="button" onClick={() => setRange(key)} className={`rounded-md px-3 py-2 text-sm ${range === key ? "bg-slate-900 text-white dark:bg-white dark:text-slate-950" : "bg-slate-100 dark:bg-white/10"}`}>
              {label}
            </button>
          ))}
        </div>
        <select className="field" value={resolution} onChange={(event) => setResolution(event.target.value)}>
          <option value="raw">Datos crudos</option>
          <option value="minute">Minuto</option>
          <option value="hour">Hora</option>
          <option value="day">Dia</option>
        </select>
      </div>

      <section className="panel p-4">
        <h3 className="mb-3 text-base font-semibold">Potencias y energia</h3>
        {measurements.isPending ? <p className="text-sm text-slate-500">Cargando lecturas…</p> : null}
        {measurements.isError ? <p role="alert" className="text-sm text-rose-500">No se pudieron cargar las lecturas: {measurements.error.message}</p> : null}
        {!measurements.isPending && !measurements.isError && rows.length === 0 ? <p className="text-sm text-slate-500">No hay lecturas en este periodo.</p> : null}
        {rows.length > 0 ? <EChart option={line} height={390} /> : null}
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <div className="panel p-4">
          <h3 className="mb-3 text-base font-semibold">Area temporal de flujos</h3>
          {rows.length > 0 ? <EChart option={area} /> : <p className="text-sm text-slate-500">Sin datos para dibujar.</p>}
        </div>
        <div className="panel p-4">
          <h3 className="mb-3 text-base font-semibold">Barras por hora</h3>
          {rows.length > 0 ? <EChart option={bars} /> : <p className="text-sm text-slate-500">Sin datos para dibujar.</p>}
        </div>
        <div className="panel p-4">
          <h3 className="mb-3 text-base font-semibold">Heatmap hora y dia</h3>
          {rows.length > 0 ? <EChart option={heatmap} /> : <p className="text-sm text-slate-500">Sin datos para dibujar.</p>}
        </div>
        <div className="panel p-4">
          <h3 className="mb-3 text-base font-semibold">Eventos y anomalias</h3>
          <div className="max-h-80 overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2">Hora</th>
                  <th className="py-2">Evento</th>
                  <th className="py-2">Confianza</th>
                </tr>
              </thead>
              <tbody>
                {(events.data?.analysis ?? []).map((event) => (
                  <tr key={`${event.timestamp}-${event.event_type}`} className="border-t border-slate-200 dark:border-white/10">
                    <td className="py-2">{new Date(event.timestamp).toLocaleString("es-ES")}</td>
                    <td className="py-2">{event.label}</td>
                    <td className="py-2">{event.confidence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
