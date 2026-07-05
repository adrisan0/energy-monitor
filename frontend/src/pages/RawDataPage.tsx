import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useLatest, useSystemStatus } from "../hooks/useEnergy";
import { formatW } from "../utils/format";

export default function RawDataPage() {
  const raw = useQuery({ queryKey: ["raw-latest"], queryFn: api.rawLatest, refetchInterval: 30_000 });
  const latest = useLatest();
  const status = useSystemStatus();
  const events = useQuery({ queryKey: ["events-system"], queryFn: api.events, refetchInterval: 60_000 });

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-semibold tracking-normal">Datos brutos</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400">Payloads redactados y diagnostico tecnico</p>
      </div>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Tile label="Calidad" value={raw.data?.data_quality ?? "sin datos"} />
        <Tile label="Respuesta" value={raw.data?.poll_duration_ms == null ? "-- ms" : `${raw.data.poll_duration_ms} ms`} />
        <Tile label="Medidor" value={status.data?.meter_online ? "online" : "sin datos"} />
        <Tile label="Payload repetido" value={raw.data?.repeated_payload ? "si" : "no"} />
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <div className="panel p-4">
          <h3 className="mb-3 text-base font-semibold">XML redactado</h3>
          <pre className="max-h-[520px] overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100">{raw.data?.raw_payload_redacted ?? "Sin payload"}</pre>
        </div>
        <div className="panel p-4">
          <h3 className="mb-3 text-base font-semibold">Variables disponibles</h3>
          <div className="max-h-[520px] overflow-auto">
            <table className="w-full text-left text-sm">
              <tbody>
                {Object.entries(raw.data?.raw_variables ?? {}).map(([key, value]) => (
                  <tr key={key} className="border-t border-slate-200 dark:border-white/10">
                    <td className="py-2 pr-3 font-medium">{key}</td>
                    <td className="py-2 text-slate-600 dark:text-slate-300">{String(value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <div className="panel p-4">
          <h3 className="mb-3 text-base font-semibold">Valores calculados</h3>
          <div className="grid gap-2 text-sm sm:grid-cols-2">
            <Info label="Solar" value={formatW(latest.data?.solar_w)} />
            <Info label="Importacion" value={formatW(latest.data?.grid_import_w)} />
            <Info label="Exportacion" value={formatW(latest.data?.grid_export_w)} />
            <Info label="Consumo" value={formatW(latest.data?.house_consumption_w)} />
          </div>
          {raw.data?.error_message ? <p className="mt-3 text-sm text-red-500">{raw.data.error_message}</p> : null}
        </div>
        <div className="panel p-4">
          <h3 className="mb-3 text-base font-semibold">Historial de conectividad</h3>
          <div className="max-h-72 overflow-auto">
            {(events.data?.system ?? []).map((event) => (
              <div key={event.id} className="border-t border-slate-200 py-3 text-sm dark:border-white/10">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium">{event.event_type}</span>
                  <span className="text-xs text-slate-500">{new Date(event.timestamp_utc).toLocaleString("es-ES")}</span>
                </div>
                <p className="mt-1 text-slate-600 dark:text-slate-300">{event.message}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <p className="label">{label}</p>
      <p className="mt-2 text-xl font-semibold">{value}</p>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-100 p-3 dark:bg-white/5">
      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  );
}
