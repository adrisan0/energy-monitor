import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Device } from "../api/types";
import { useDeviceState, useDevices, useLatest } from "../hooks/useEnergy";

const DEFAULT_TOKEN = "change-me-local-admin-token";

type Feedback = { tone: "success" | "error"; text: string } | null;
type ThermoAutomation = {
  enabled: boolean;
  profile: "surplus_water_heater";
  surplus_on_w: number;
  surplus_off_w: number;
  on_hold_seconds: number;
  off_hold_seconds: number;
  min_daily_runtime_minutes: number;
  topup_window_start_hour: number;
  topup_window_end_hour: number;
  block_peak_hours: boolean;
};

const DEFAULT_THERMO_AUTOMATION: ThermoAutomation = {
  enabled: false,
  profile: "surplus_water_heater",
  surplus_on_w: 1200,
  surplus_off_w: 150,
  on_hold_seconds: 120,
  off_hold_seconds: 120,
  min_daily_runtime_minutes: 45,
  topup_window_start_hour: 14,
  topup_window_end_hour: 18,
  block_peak_hours: true
};

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Operacion fallida";
}

export default function PlugsPage() {
  const devices = useDevices();
  const plugs = (devices.data ?? []).filter(
    (device) =>
      device.type === "smart_plug" &&
      ["kasa_hs100", "sonoff_s61s"].includes(String(device.config?.adapter ?? ""))
  );

  const [token, setToken] = useState(DEFAULT_TOKEN);

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">Enchufes</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Control manual de enchufes TP-Link y Sonoff</p>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          <span className="label">Admin token</span>
          <input className="field min-w-72" value={token} onChange={(event) => setToken(event.target.value)} />
        </label>
      </div>

      {plugs.length === 0 ? <div className="panel p-4">No hay enchufes compatibles configurados.</div> : null}

      <div className="grid gap-5 xl:grid-cols-2">
        {plugs.map((plug) => (
          <PlugCard key={plug.id} plug={plug} token={token} />
        ))}
      </div>
    </div>
  );
}

function PlugCard({ plug, token }: { plug: Device; token: string }) {
  const queryClient = useQueryClient();
  const plugState = useDeviceState(plug.id);
  const latest = useLatest();
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [draft, setDraft] = useState<ThermoAutomation>(DEFAULT_THERMO_AUTOMATION);

  useEffect(() => {
    const raw = (plug.config?.thermo_automation ?? {}) as Partial<ThermoAutomation>;
    setDraft({ ...DEFAULT_THERMO_AUTOMATION, ...raw });
  }, [plug]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["devices"] }),
      queryClient.invalidateQueries({ queryKey: ["device-state", plug.id] })
    ]);
  };

  const onMutation = useMutation({
    mutationFn: async () => api.deviceTurnOn(plug.id, token),
    onSuccess: async (result) => {
      setFeedback({ tone: "success", text: result.message });
      await refresh();
    },
    onError: (error) => setFeedback({ tone: "error", text: errorText(error) })
  });

  const offMutation = useMutation({
    mutationFn: async () => api.deviceTurnOff(plug.id, token),
    onSuccess: async (result) => {
      setFeedback({ tone: "success", text: result.message });
      await refresh();
    },
    onError: (error) => setFeedback({ tone: "error", text: errorText(error) })
  });

  const saveAutomationMutation = useMutation({
    mutationFn: async () =>
      api.updateDevice(
        plug.id,
        {
          config: {
            ...(plug.config ?? {}),
            thermo_automation: draft
          }
        },
        token
      ),
    onSuccess: async () => {
      setFeedback({ tone: "success", text: "Configuracion del termo guardada." });
      await refresh();
    },
    onError: (error) => setFeedback({ tone: "error", text: errorText(error) })
  });

  const enableAutoMutation = useMutation({
    mutationFn: async () => {
      await api.updateDevice(
        plug.id,
        {
          control_mode: "automatic",
          config: {
            ...(plug.config ?? {}),
            thermo_automation: { ...draft, enabled: true }
          }
        },
        token
      );
      return api.deviceApplyAutomation(plug.id, token);
    },
    onSuccess: async (result) => {
      setFeedback({ tone: "success", text: result.message });
      await refresh();
    },
    onError: (error) => setFeedback({ tone: "error", text: errorText(error) })
  });

  const disableAutoMutation = useMutation({
    mutationFn: async () =>
      api.updateDevice(
        plug.id,
        {
          control_mode: "manual",
          config: {
            ...(plug.config ?? {}),
            thermo_automation: { ...draft, enabled: false }
          }
        },
        token
      ),
    onSuccess: async () => {
      setFeedback({ tone: "success", text: "Modo termo desactivado; enchufe en manual." });
      await refresh();
    },
    onError: (error) => setFeedback({ tone: "error", text: errorText(error) })
  });

  const applyAutomationMutation = useMutation({
    mutationFn: async () => {
      await api.updateDevice(
        plug.id,
        {
          config: {
            ...(plug.config ?? {}),
            thermo_automation: draft
          }
        },
        token
      );
      return api.deviceApplyAutomation(plug.id, token);
    },
    onSuccess: async (result) => {
      setFeedback({ tone: "success", text: result.message });
      await refresh();
    },
    onError: (error) => setFeedback({ tone: "error", text: errorText(error) })
  });

  const busy =
    onMutation.isPending ||
    offMutation.isPending ||
    saveAutomationMutation.isPending ||
    enableAutoMutation.isPending ||
    disableAutoMutation.isPending ||
    applyAutomationMutation.isPending;
  const raw = (plugState.data?.raw ?? {}) as Record<string, unknown>;
  const adapter = String(plug.config?.adapter ?? "");
  const thermoState = (plug.config?.thermo_automation_state ?? {}) as Record<string, unknown>;
  const thermoEnabled = Boolean(draft.enabled);
  const latestExport = latest.data?.grid_export_w ?? 0;
  const latestImport = latest.data?.grid_import_w ?? 0;

  return (
    <section className="panel p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">{plug.name}</h3>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {adapter === "sonoff_s61s" ? "Sonoff/eWeLink original" : "TP-Link Kasa"}
          </p>
        </div>
        <span className="rounded-full border px-3 py-1 text-xs">
          {plugState.data?.is_on ? "encendido" : "apagado"}
        </span>
      </div>

      {feedback ? (
        <div
          className={`mt-4 rounded-md border px-4 py-3 text-sm ${
            feedback.tone === "success"
              ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200"
              : "border-red-300 bg-red-50 text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200"
          }`}
        >
          {feedback.text}
        </div>
      ) : null}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Tile label="Online" value={plugState.data?.online ? "si" : "no"} />
        <Tile label="IP" value={plug.ip_address ?? "-"} />
        <Tile label="Alias" value={String(raw.alias ?? raw.deviceid ?? "-")} />
        <Tile label="Modelo" value={String(raw.model ?? plug.model ?? "-")} />
        <Tile label="Potencia" value={plugState.data?.power_w == null ? "no disponible" : `${plugState.data.power_w} W`} />
        <Tile label="Tipo" value={adapter} />
        <Tile label="Modo" value={plug.control_mode} />
        <Tile label="Auto termo" value={thermoEnabled ? "si" : "no"} />
        <Tile label="Runtime hoy" value={`${Math.round(Number(thermoState.runtime_today_seconds ?? 0) / 60)} min`} />
        <Tile label="Ultimo motivo" value={String(thermoState.last_reason ?? "-")} />
      </div>

      {adapter === "sonoff_s61s" ? (
        <div className="mt-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100">
          Si falla el Sonoff, suele faltar `device_id` o `api_key`, o el enchufe no anuncia LAN mode en la red local.
        </div>
      ) : null}

      {adapter === "kasa_hs100" ? (
        <div className="mt-4 space-y-4 rounded-xl border border-slate-200 p-4 dark:border-white/10">
          <div>
            <h4 className="text-sm font-semibold">Modo termo</h4>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Enciende con excedente sostenido, se apaga al perder excedente, evita hora punta y asegura un minimo diario fuera de punta.
            </p>
          </div>

          <label className="flex items-center gap-3 text-sm">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(event) => setDraft((current) => ({ ...current, enabled: event.target.checked }))}
            />
            <span>Automatizacion del termo activada</span>
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            <NumberField label="Excedente para encender (W)" value={draft.surplus_on_w} onChange={(value) => setDraft((current) => ({ ...current, surplus_on_w: value }))} />
            <NumberField label="Excedente para apagar (W)" value={draft.surplus_off_w} onChange={(value) => setDraft((current) => ({ ...current, surplus_off_w: value }))} />
            <NumberField label="Excedente estable encendido (s)" value={draft.on_hold_seconds} onChange={(value) => setDraft((current) => ({ ...current, on_hold_seconds: value }))} />
            <NumberField label="Sin excedente para apagar (s)" value={draft.off_hold_seconds} onChange={(value) => setDraft((current) => ({ ...current, off_hold_seconds: value }))} />
            <NumberField label="Minimo diario (min)" value={draft.min_daily_runtime_minutes} onChange={(value) => setDraft((current) => ({ ...current, min_daily_runtime_minutes: value }))} />
            <NumberField label="Apoyo desde hora" value={draft.topup_window_start_hour} onChange={(value) => setDraft((current) => ({ ...current, topup_window_start_hour: value }))} />
            <NumberField label="Apoyo hasta hora" value={draft.topup_window_end_hour} onChange={(value) => setDraft((current) => ({ ...current, topup_window_end_hour: value }))} />
          </div>

          <label className="flex items-center gap-3 text-sm">
            <input
              type="checkbox"
              checked={draft.block_peak_hours}
              onChange={(event) => setDraft((current) => ({ ...current, block_peak_hours: event.target.checked }))}
            />
            <span>No encender en hora punta</span>
          </label>

          <div className="rounded-md border border-sky-300 bg-sky-50 px-3 py-2 text-xs text-sky-900 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-100">
            Ahora mismo: exportacion {latestExport} W, importacion {latestImport} W. Si activas automatico, el worker reevaluara el termo en cada lectura del medidor.
          </div>

          <div className="flex flex-wrap gap-2">
            <ActionButton disabled={busy} pending={saveAutomationMutation.isPending} onClick={() => saveAutomationMutation.mutate()} primary>
              Guardar configuracion
            </ActionButton>
            <ActionButton disabled={busy} pending={enableAutoMutation.isPending} onClick={() => enableAutoMutation.mutate()}>
              Activar modo termo
            </ActionButton>
            <ActionButton disabled={busy} pending={disableAutoMutation.isPending} onClick={() => disableAutoMutation.mutate()}>
              Volver a manual
            </ActionButton>
            <ActionButton disabled={busy} pending={applyAutomationMutation.isPending} onClick={() => applyAutomationMutation.mutate()}>
              Probar ahora
            </ActionButton>
          </div>
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <ActionButton disabled={busy} pending={onMutation.isPending} onClick={() => onMutation.mutate()} primary>
          Encender
        </ActionButton>
        <ActionButton disabled={busy} pending={offMutation.isPending} onClick={() => offMutation.mutate()}>
          Apagar
        </ActionButton>
        <ActionButton disabled={busy} pending={false} onClick={() => void refresh()}>
          Refrescar estado
        </ActionButton>
      </div>
    </section>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="label">{label}</span>
      <input className="field" type="number" value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function ActionButton({
  children,
  disabled,
  onClick,
  pending,
  primary = false
}: {
  children: string;
  disabled: boolean;
  onClick: () => void;
  pending: boolean;
  primary?: boolean;
}) {
  return (
    <button
      className={`rounded-md px-4 py-2 text-sm ${
        primary ? "bg-slate-900 text-white dark:bg-white dark:text-slate-950" : "border"
      } disabled:cursor-not-allowed disabled:opacity-60`}
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      {pending ? "Aplicando..." : children}
    </button>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <p className="label">{label}</p>
      <p className="mt-2 break-all text-base font-semibold">{value}</p>
    </div>
  );
}
