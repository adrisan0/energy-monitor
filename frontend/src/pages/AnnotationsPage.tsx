import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { Plus } from "lucide-react";
import { api } from "../api/client";
import type { Annotation, Measurement } from "../api/types";
import EChart from "../components/EChart";
import { useMeasurements } from "../hooks/useEnergy";
import { rangeQuery } from "../utils/format";

const applianceNames = ["lavadora", "termo padres", "termo usuario", "lavavajillas", "horno", "aire acondicionado", "ordenador potente"];

export default function AnnotationsPage() {
  const queryClient = useQueryClient();
  const annotations = useQuery({ queryKey: ["annotations"], queryFn: api.annotations });
  const events = useQuery({ queryKey: ["events-analysis"], queryFn: api.events, refetchInterval: 60_000 });
  const measurements = useMeasurements("raw", rangeQuery("24h"));
  const [form, setForm] = useState({
    appliance_name: "lavadora",
    home_area: "compartido",
    appliance_type: "electrodomestico",
    starts_at: toLocalInput(new Date()),
    ends_at: "",
    approx_power_w: "",
    comment: "",
    source: "manual",
    confidence: "confirmed_manual"
  });

  const create = useMutation({
    mutationFn: () =>
      api.createAnnotation({
        appliance_name: form.appliance_name,
        home_area: form.home_area || null,
        appliance_type: form.appliance_type || null,
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
        approx_power_w: form.approx_power_w || null,
        comment: form.comment || null,
        source: form.source,
        confidence: form.confidence
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["annotations"] })
  });

  const option = useMemo(
    () => annotationOption((measurements.data?.data ?? []) as Measurement[], annotations.data ?? []),
    [measurements.data, annotations.data]
  );

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-semibold tracking-normal">Anotaciones y analisis</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400">Confirmaciones manuales e hipotesis separadas</p>
      </div>

      <section className="panel p-4">
        <h3 className="text-base font-semibold">Anotar evento</h3>
        <div className="mt-4 flex flex-wrap gap-2">
          {applianceNames.map((name) => (
            <button key={name} type="button" onClick={() => setForm({ ...form, appliance_name: name, starts_at: toLocalInput(new Date()) })} className="rounded-md bg-slate-100 px-3 py-2 text-sm dark:bg-white/10">
              Ahora {name}
            </button>
          ))}
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Field label="Aparato" value={form.appliance_name} onChange={(value) => setForm({ ...form, appliance_name: value })} />
          <Field label="Vivienda o zona" value={form.home_area} onChange={(value) => setForm({ ...form, home_area: value })} />
          <Field label="Tipo" value={form.appliance_type} onChange={(value) => setForm({ ...form, appliance_type: value })} />
          <Field label="Potencia aproximada W" value={form.approx_power_w} onChange={(value) => setForm({ ...form, approx_power_w: value })} />
          <DateField label="Inicio" value={form.starts_at} onChange={(value) => setForm({ ...form, starts_at: value })} />
          <DateField label="Fin" value={form.ends_at} onChange={(value) => setForm({ ...form, ends_at: value })} />
          <Select label="Fuente" value={form.source} options={["manual", "smart_plug", "estimacion", "ia_futura"]} onChange={(value) => setForm({ ...form, source: value })} />
          <Select label="Confianza" value={form.confidence} options={["confirmed_manual", "low", "medium", "high", "smart_plug_measured"]} onChange={(value) => setForm({ ...form, confidence: value })} />
        </div>
        <textarea className="field mt-3 min-h-20 w-full py-2" value={form.comment} onChange={(event) => setForm({ ...form, comment: event.target.value })} placeholder="Comentario" />
        <button type="button" onClick={() => create.mutate()} className="mt-3 inline-flex h-10 items-center gap-2 rounded-md bg-slate-900 px-3 text-sm font-medium text-white dark:bg-white dark:text-slate-950">
          <Plus className="h-4 w-4" aria-hidden />
          Guardar anotacion
        </button>
      </section>

      <section className="panel p-4">
        <h3 className="mb-3 text-base font-semibold">Consumo con intervalos anotados</h3>
        <EChart option={option} height={360} />
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <div className="panel p-4">
          <h3 className="mb-3 text-base font-semibold">Anotaciones</h3>
          <div className="max-h-96 overflow-auto">
            {(annotations.data ?? []).map((annotation) => (
              <div key={annotation.id} className="border-t border-slate-200 py-3 text-sm dark:border-white/10">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium">{annotation.appliance_name}</span>
                  <span className="text-xs text-slate-500">{annotation.confidence}</span>
                </div>
                <p className="text-slate-600 dark:text-slate-300">
                  {new Date(annotation.starts_at).toLocaleString("es-ES")}
                  {annotation.ends_at ? ` - ${new Date(annotation.ends_at).toLocaleString("es-ES")}` : ""}
                </p>
                {annotation.comment ? <p className="mt-1">{annotation.comment}</p> : null}
              </div>
            ))}
          </div>
        </div>
        <div className="panel p-4">
          <h3 className="mb-3 text-base font-semibold">Hipotesis del analisis</h3>
          <div className="max-h-96 overflow-auto">
            {(events.data?.analysis ?? []).map((event) => (
              <div key={`${event.timestamp}-${event.event_type}`} className="border-t border-slate-200 py-3 text-sm dark:border-white/10">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium">{event.label}</span>
                  <span className="text-xs text-slate-500">{event.confidence}</span>
                </div>
                <p className="text-slate-600 dark:text-slate-300">{event.note}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function annotationOption(rows: Measurement[], annotations: Annotation[]): EChartsOption {
  const data = [...rows].reverse().map((row) => [row.timestamp_local, row.house_consumption_w ?? 0]);
  return {
    color: ["#ef4444"],
    tooltip: { trigger: "axis" },
    grid: { top: 30, left: 50, right: 20, bottom: 60 },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 24 }],
    xAxis: { type: "time" },
    yAxis: { type: "value", name: "W" },
    series: [
      {
        name: "Consumo",
        type: "line",
        symbol: "none",
        data,
        markArea: {
          itemStyle: { color: "rgba(245, 158, 11, 0.18)" },
          data: annotations
            .filter((item) => item.ends_at)
            .map((item) => [
              { name: item.appliance_name, xAxis: item.starts_at },
              { xAxis: item.ends_at as string }
            ])
        }
      }
    ]
  };
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label>
      <span className="label">{label}</span>
      <input className="field mt-1 w-full" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function DateField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label>
      <span className="label">{label}</span>
      <input className="field mt-1 w-full" type="datetime-local" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function Select({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <label>
      <span className="label">{label}</span>
      <select className="field mt-1 w-full" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function toLocalInput(date: Date): string {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 16);
}
