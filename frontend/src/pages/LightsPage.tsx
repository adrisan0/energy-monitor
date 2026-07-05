import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Device, DeviceUpdate } from "../api/types";
import { useDeviceState, useDevices, useLatest } from "../hooks/useEnergy";
import { formatW } from "../utils/format";

const DEFAULT_TOKEN = "change-me-local-admin-token";

type AutomationProfile = "consumption_gradient" | "grid_import_alert" | "tariff_price";
type Tier = "low" | "medium" | "high" | "surplus";
type Feedback = { tone: "success" | "error" | "info"; text: string } | null;

const PROFILE_PRESETS: Record<
  AutomationProfile,
  {
    metric: string;
    surplusOverride: boolean;
    blinkOnSolarGridImport: boolean;
    thresholds: { low_max_w: number; medium_max_w: number };
    colors: Record<Tier, string>;
    brightness: Record<Tier, number>;
    prices: Record<Tier, number>;
    description: string;
  }
> = {
  consumption_gradient: {
    metric: "house_consumption_w",
    surplusOverride: true,
    blinkOnSolarGridImport: true,
    thresholds: { low_max_w: 350, medium_max_w: 1650 },
    colors: { low: "#22C55E", medium: "#F59E0B", high: "#EF4444", surplus: "#3B82F6" },
    brightness: { low: 96, medium: 160, high: 255, surplus: 180 },
    prices: { low: 0.12, medium: 0.17, high: 0.24, surplus: 0.24 },
    description: "Degradado por consumo de la vivienda, con prioridad opcional para excedente."
  },
  grid_import_alert: {
    metric: "grid_import_w",
    surplusOverride: false,
    blinkOnSolarGridImport: false,
    thresholds: { low_max_w: 350, medium_max_w: 1650 },
    colors: { low: "#22C55E", medium: "#F59E0B", high: "#EF4444", surplus: "#A855F7" },
    brightness: { low: 96, medium: 144, high: 208, surplus: 255 },
    prices: { low: 0.12, medium: 0.17, high: 0.24, surplus: 0.24 },
    description: "Verde si no importas nada; amarillo, rojo y morado cuanto mas tiras de la red."
  },
  tariff_price: {
    metric: "house_consumption_w",
    surplusOverride: false,
    blinkOnSolarGridImport: false,
    thresholds: { low_max_w: 350, medium_max_w: 1650 },
    colors: { low: "#22C55E", medium: "#F59E0B", high: "#EF4444", surplus: "#A855F7" },
    brightness: { low: 96, medium: 160, high: 255, surplus: 255 },
    prices: { low: 0.12, medium: 0.17, high: 0.24, surplus: 0.24 },
    description: "Color segun tramo 2.0TD simplificado: valle, llano y punta. Fines de semana se consideran valle."
  }
};

function hexToRgbTuple(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  return [
    Number.parseInt(clean.slice(0, 2), 16),
    Number.parseInt(clean.slice(2, 4), 16),
    Number.parseInt(clean.slice(4, 6), 16)
  ];
}

function rgbArrayToHex(rgb: unknown): string {
  if (!Array.isArray(rgb) || rgb.length !== 3) return "#ffffff";
  const parts = rgb.map((value) => Number(value).toString(16).padStart(2, "0"));
  return `#${parts.join("")}`;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Operacion fallida";
}

function buildAutomationDraft(config: Record<string, unknown>, profile: AutomationProfile): NonNullable<DeviceUpdate["config"]> {
  const preset = PROFILE_PRESETS[profile];
  const automation = typeof config.automation === "object" && config.automation ? (config.automation as Record<string, unknown>) : {};
  const thresholds = (automation.thresholds as Record<string, unknown> | undefined) ?? {};
  const colors = (automation.colors as Record<string, unknown> | undefined) ?? {};
  const brightness = (automation.brightness as Record<string, unknown> | undefined) ?? {};
  const prices = (automation.prices as Record<string, unknown> | undefined) ?? {};

  return {
    adapter: "flux_led",
    ip_address: typeof config.ip_address === "string" ? config.ip_address : null,
    automation: {
      enabled: automation.enabled ?? false,
      profile,
      metric: automation.metric ?? preset.metric,
      surplus_override: automation.surplus_override ?? preset.surplusOverride,
      blink_on_solar_grid_import: automation.blink_on_solar_grid_import ?? preset.blinkOnSolarGridImport,
      thresholds: {
        low_max_w: thresholds.low_max_w ?? preset.thresholds.low_max_w,
        medium_max_w: thresholds.medium_max_w ?? preset.thresholds.medium_max_w
      },
      colors: {
        low: colors.low ?? preset.colors.low,
        medium: colors.medium ?? preset.colors.medium,
        high: colors.high ?? preset.colors.high,
        surplus: colors.surplus ?? preset.colors.surplus
      },
      brightness: {
        low: brightness.low ?? preset.brightness.low,
        medium: brightness.medium ?? preset.brightness.medium,
        high: brightness.high ?? preset.brightness.high,
        surplus: brightness.surplus ?? preset.brightness.surplus
      },
      prices: {
        low: prices.low ?? preset.prices.low,
        medium: prices.medium ?? preset.prices.medium,
        high: prices.high ?? preset.prices.high,
        surplus: prices.surplus ?? preset.prices.surplus
      }
    }
  };
}

function tierLabel(profile: AutomationProfile, tier: Tier): string {
  if (profile === "tariff_price") {
    return {
      low: "Valle",
      medium: "Llano",
      high: "Punta",
      surplus: "Punta alta"
    }[tier];
  }
  if (profile === "grid_import_alert") {
    return {
      low: "Sin importacion",
      medium: "Importacion baja",
      high: "Importacion media",
      surplus: "Importacion alta"
    }[tier];
  }
  return {
    low: "Consumo bajo",
    medium: "Consumo medio",
    high: "Consumo alto",
    surplus: "Excedente"
  }[tier];
}

function currentTier(
  profile: AutomationProfile,
  latest:
    | { timestamp?: string; house_consumption_w: number | null; grid_import_w: number | null; grid_export_w: number | null }
    | undefined,
  automation: Record<string, any>
): Tier {
  if (profile === "tariff_price") {
    return tariffTierForTimestamp(latest?.timestamp);
  }

  const lowMax = Number(automation.thresholds?.low_max_w ?? PROFILE_PRESETS[profile].thresholds.low_max_w);
  const mediumMax = Number(automation.thresholds?.medium_max_w ?? PROFILE_PRESETS[profile].thresholds.medium_max_w);

  if (profile === "consumption_gradient") {
    if (Boolean(automation.surplus_override) && Number(latest?.grid_export_w ?? 0) > 0) return "surplus";
    const value = Number(latest?.house_consumption_w ?? 0);
    if (value < lowMax) return "low";
    if (value < mediumMax) return "medium";
    return "high";
  }

  const imported = Number(latest?.grid_import_w ?? 0);
  if (imported <= 0) return "low";
  if (imported < lowMax) return "medium";
  if (imported < mediumMax) return "high";
  return "surplus";
}

function tariffTierForTimestamp(timestamp: string | undefined): Tier {
  const date = timestamp ? new Date(timestamp) : new Date();
  const day = date.getDay();
  if (day === 0 || day === 6) return "low";
  const hour = date.getHours();
  if ((hour >= 10 && hour < 14) || (hour >= 18 && hour < 22)) return "high";
  if ((hour >= 8 && hour < 10) || (hour >= 14 && hour < 18) || (hour >= 22 && hour < 24)) return "medium";
  return "low";
}

function shouldBlinkSolarGridImport(
  profile: AutomationProfile,
  latest: { solar_w: number | null; grid_import_w: number | null } | undefined,
  automation: Record<string, any>
): boolean {
  return (
    profile === "consumption_gradient" &&
    Boolean(automation.blink_on_solar_grid_import ?? true) &&
    Number(latest?.solar_w ?? 0) > 0 &&
    Number(latest?.grid_import_w ?? 0) > 0
  );
}

function sameJson(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function isFluxLight(device: Device): boolean {
  return String(device.config?.adapter) === "flux_led" || device.type === "light_controller";
}

export default function LightsPage() {
  const queryClient = useQueryClient();
  const devices = useDevices();
  const latest = useLatest();
  const [selectedLightId, setSelectedLightId] = useState<number | null>(null);
  const lightDevices = (devices.data ?? []).filter(isFluxLight);
  const preferredLight = lightDevices.find((device) => device.status === "active") ?? lightDevices[0] ?? null;
  const fluxDevice = lightDevices.find((device) => device.id === selectedLightId) ?? preferredLight;
  const deviceState = useDeviceState(fluxDevice?.id ?? null);

  const [token, setToken] = useState(DEFAULT_TOKEN);
  const [manualColor, setManualColor] = useState("#ff7814");
  const [manualBrightness, setManualBrightness] = useState(255);
  const [draft, setDraft] = useState<DeviceUpdate["config"]>({});
  const [feedback, setFeedback] = useState<Feedback>(null);

  useEffect(() => {
    if (!preferredLight) return;
    if (!lightDevices.some((device) => device.id === selectedLightId)) {
      setSelectedLightId(preferredLight.id);
    }
  }, [lightDevices, preferredLight, selectedLightId]);

  useEffect(() => {
    const raw = deviceState.data?.raw ?? {};
    if (raw && typeof raw === "object") {
      setManualColor(rgbArrayToHex((raw as Record<string, unknown>).rgb));
      const brightness = (raw as Record<string, unknown>).brightness;
      if (typeof brightness === "number") {
        setManualBrightness(brightness);
      }
    }
  }, [deviceState.data]);

  useEffect(() => {
    if (!fluxDevice) return;
    const config = (fluxDevice.config ?? {}) as Record<string, unknown>;
    const automation = typeof config.automation === "object" && config.automation ? (config.automation as Record<string, unknown>) : {};
    const profile = (automation.profile as AutomationProfile | undefined) ?? "consumption_gradient";
    const nextDraft = buildAutomationDraft(config, profile);
    nextDraft.ip_address = fluxDevice.ip_address ?? (typeof config.ip_address === "string" ? config.ip_address : null);
    setDraft(nextDraft);
  }, [fluxDevice]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["devices"] }),
      queryClient.invalidateQueries({ queryKey: ["device-state", fluxDevice?.id] }),
      queryClient.invalidateQueries({ queryKey: ["latest"] })
    ]);
  };

  const onOffMutation = useMutation({
    mutationFn: async (turnOn: boolean) =>
      turnOn ? api.deviceTurnOn(fluxDevice!.id, token) : api.deviceTurnOff(fluxDevice!.id, token),
    onSuccess: async (result) => {
      setFeedback({ tone: "success", text: result.message });
      await refresh();
    },
    onError: (error) => setFeedback({ tone: "error", text: errorText(error) })
  });

  const colorMutation = useMutation({
    mutationFn: async () => {
      if (fluxDevice?.control_mode !== "manual") {
        await api.deviceSetMode(fluxDevice!.id, { mode: "manual" }, token);
      }
      return api.deviceSetColor(fluxDevice!.id, { rgb: hexToRgbTuple(manualColor), brightness: manualBrightness }, token);
    },
    onSuccess: async (result) => {
      setFeedback({ tone: "success", text: "Color aplicado y modo manual activado." });
      await refresh();
    },
    onError: (error) => setFeedback({ tone: "error", text: errorText(error) })
  });

  const modeMutation = useMutation({
    mutationFn: async (mode: "manual" | "automatic") => {
      if (mode === "automatic") {
        await api.updateDevice(fluxDevice!.id, { config: draft, control_mode: "automatic" }, token);
        return api.deviceApplyAutomation(fluxDevice!.id, token);
      }
      return api.deviceSetMode(fluxDevice!.id, { mode }, token);
    },
    onSuccess: async (result) => {
      setFeedback({ tone: "success", text: result.message });
      await refresh();
      await queryClient.invalidateQueries({ queryKey: ["devices"] });
    },
    onError: (error) => setFeedback({ tone: "error", text: errorText(error) })
  });

  const saveMutation = useMutation({
    mutationFn: async () => api.updateDevice(fluxDevice!.id, { config: draft, control_mode: fluxDevice?.control_mode }, token),
    onSuccess: async () => {
      setFeedback({ tone: "success", text: "Configuracion guardada." });
      await refresh();
    },
    onError: (error) => setFeedback({ tone: "error", text: errorText(error) })
  });

  const applyMutation = useMutation({
    mutationFn: async () => {
      await api.updateDevice(fluxDevice!.id, { config: draft, control_mode: fluxDevice?.control_mode }, token);
      return api.deviceApplyAutomation(fluxDevice!.id, token);
    },
    onSuccess: async (result) => {
      setFeedback({ tone: "success", text: result.message });
      await refresh();
    },
    onError: (error) => setFeedback({ tone: "error", text: errorText(error) })
  });

  if (!fluxDevice) {
    return <div className="panel p-4">No hay ninguna luz `flux_led` configurada.</div>;
  }

  const automation = (draft?.automation as Record<string, any> | undefined) ?? {};
  const profile = (automation.profile as AutomationProfile | undefined) ?? "consumption_gradient";
  const preset = PROFILE_PRESETS[profile];
  const activeTier = currentTier(profile, latest.data, automation);
  const blinkActive = shouldBlinkSolarGridImport(profile, latest.data, automation);
  const activePrice = Number(automation.prices?.[activeTier] ?? preset.prices[activeTier]);
  const hasPendingChanges =
    !sameJson(draft, fluxDevice.config) || fluxDevice.control_mode !== "manual" && fluxDevice.control_mode !== "automatic";
  const busy =
    onOffMutation.isPending ||
    colorMutation.isPending ||
    modeMutation.isPending ||
    saveMutation.isPending ||
    applyMutation.isPending;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">Luces</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Control manual y automatico de luces Flux LED / Magic Home</p>
          <p className="text-xs text-slate-400 dark:text-slate-500">Selecciona la lampara o tira que quieres controlar y aplica color manual, consumo o importacion desde red.</p>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          <span className="label">Admin token</span>
          <input className="field min-w-72" value={token} onChange={(event) => setToken(event.target.value)} />
        </label>
      </div>

      {feedback ? (
        <div
          className={`rounded-md border px-4 py-3 text-sm ${
            feedback.tone === "success"
              ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200"
              : feedback.tone === "error"
                ? "border-red-300 bg-red-50 text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200"
                : "border-slate-300 bg-slate-50 text-slate-800 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"
          }`}
        >
          {feedback.text}
        </div>
      ) : null}

      {hasPendingChanges ? (
        <div className="rounded-md border border-sky-300 bg-sky-50 px-4 py-3 text-sm text-sky-900 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-100">
          Hay cambios locales sin guardar. `Guardar configuracion`, `Modo automatico` y `Probar automatizacion ahora` usarán el borrador actual.
        </div>
      ) : null}

      <section className="panel p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-base font-semibold">Luces conectadas</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Dispositivo seleccionado: <strong>{fluxDevice.name}</strong> {fluxDevice.ip_address ? `(${fluxDevice.ip_address})` : ""}
            </p>
          </div>
          <select
            className="field min-w-72"
            value={fluxDevice.id}
            onChange={(event) => setSelectedLightId(Number(event.target.value))}
          >
            {lightDevices.map((device) => (
              <option key={device.id} value={device.id}>
                #{device.id} {device.name} {device.ip_address ? `- ${device.ip_address}` : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {lightDevices.map((device) => (
            <button
              key={device.id}
              className={`rounded-xl border p-4 text-left transition ${
                device.id === fluxDevice.id
                  ? "border-sky-400 bg-sky-50 text-sky-950 shadow-sm dark:border-sky-400/60 dark:bg-sky-500/10 dark:text-sky-50"
                  : "border-slate-200 bg-white hover:border-slate-300 dark:border-white/10 dark:bg-white/5 dark:hover:border-white/20"
              }`}
              onClick={() => setSelectedLightId(device.id)}
              type="button"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-semibold">{device.name}</p>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{device.model ?? "Flux LED"} · {device.zone ?? "sin zona"}</p>
                </div>
                <span className={`rounded-full px-2 py-1 text-[11px] ${device.status === "active" ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200" : "bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300"}`}>
                  {device.status}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-500 dark:text-slate-400">
                <span>ID #{device.id}</span>
                <span>{device.control_mode}</span>
                <span className="col-span-2">{device.ip_address ?? String(device.config?.ip_address ?? "sin IP")}</span>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-4">
        <Tile label="Dispositivo" value={fluxDevice.name} />
        <Tile label="Online" value={deviceState.data?.online ? "si" : "no"} />
        <Tile label="Modo" value={fluxDevice.control_mode} />
        <Tile label="Perfil LED" value={profile === "consumption_gradient" ? "consumo" : profile === "grid_import_alert" ? "solo importacion" : "precio horario"} />
        <Tile label="Color esperado auto" value={tierLabel(profile, activeTier)} />
        {profile === "tariff_price" ? <Tile label="Precio tramo" value={`${activePrice.toFixed(3)} €/kWh`} /> : null}
        <Tile label="Alerta parpadeo" value={blinkActive ? "solar + importacion" : "no"} />
        <Tile label="Ultimo consumo" value={formatW(latest.data?.house_consumption_w)} />
        <Tile label="Importacion red" value={formatW(latest.data?.grid_import_w)} />
        <Tile label="Color actual" value={rgbArrayToHex((deviceState.data?.raw ?? {}).rgb)} />
        <Tile label="Estado" value={deviceState.data?.is_on ? "encendida" : "apagada"} />
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <div className="panel p-4">
          <h3 className="text-base font-semibold">Control manual</h3>
          <div className="mt-4 grid gap-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1">
                <span className="label">Color</span>
                <input className="h-10 w-full rounded-md border border-slate-300 bg-white p-1 dark:border-white/10 dark:bg-neutral-950" type="color" value={manualColor} onChange={(event) => setManualColor(event.target.value)} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="label">Brillo ({manualBrightness})</span>
                <input type="range" min="0" max="255" value={manualBrightness} onChange={(event) => setManualBrightness(Number(event.target.value))} />
              </label>
            </div>
            <div className="flex flex-wrap gap-2">
              <ActionButton disabled={busy} pending={colorMutation.isPending} onClick={() => colorMutation.mutate()} primary>
                Aplicar color
              </ActionButton>
              <ActionButton disabled={busy} pending={onOffMutation.isPending} onClick={() => onOffMutation.mutate(true)}>
                Encender
              </ActionButton>
              <ActionButton disabled={busy} pending={onOffMutation.isPending} onClick={() => onOffMutation.mutate(false)}>
                Apagar
              </ActionButton>
              <ActionButton disabled={busy} pending={modeMutation.isPending} onClick={() => modeMutation.mutate("manual")}>
                Modo manual
              </ActionButton>
            </div>
          </div>
        </div>

        <div className="panel p-4">
          <h3 className="text-base font-semibold">Automatizacion</h3>
          <div className="mt-4 grid gap-3">
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={Boolean(automation.enabled)}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    automation: { ...(current?.automation as Record<string, unknown>), enabled: event.target.checked }
                  }))
                }
              />
              <span>Automatizacion activada</span>
            </label>

            <label className="flex flex-col gap-1">
              <span className="label">Perfil LED</span>
              <select
                className="field"
                value={profile}
                onChange={(event) => {
                  const nextProfile = event.target.value as AutomationProfile;
                  setDraft((current) => {
                    const currentConfig = (current ?? {}) as Record<string, unknown>;
                    const rebuilt = buildAutomationDraft(currentConfig, nextProfile);
                    return {
                      ...current,
                      automation: rebuilt.automation
                    };
                  });
                }}
              >
                <option value="consumption_gradient">Visualizar consumo</option>
                <option value="grid_import_alert">Solo importacion de red</option>
                <option value="tariff_price">Precio horario: valle / llano / punta</option>
              </select>
            </label>

            <p className="text-xs text-slate-500 dark:text-slate-400">{preset.description}</p>
            {fluxDevice.control_mode === "automatic" ? (
              <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100">
                En automatico la app repinta el LED con cada lectura. Ahora mismo el color esperado es <strong>{tierLabel(profile, activeTier)}</strong>
                {blinkActive
                  ? ` y debe parpadear porque hay solar (${formatW(latest.data?.solar_w)}) e importacion (${formatW(latest.data?.grid_import_w)}).`
                  : profile === "tariff_price"
                    ? ` porque el tramo horario estimado cuesta ${activePrice.toFixed(3)} €/kWh.`
                  : profile === "consumption_gradient" && activeTier === "surplus"
                    ? ` porque hay excedente (${formatW(latest.data?.grid_export_w)}).`
                    : "."}
              </div>
            ) : null}

            {profile === "consumption_gradient" ? (
              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={Boolean(automation.surplus_override)}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      automation: { ...(current?.automation as Record<string, unknown>), surplus_override: event.target.checked }
                    }))
                  }
                />
                <span>Usar color especial de excedente</span>
              </label>
            ) : null}

            {profile === "consumption_gradient" ? (
              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={Boolean(automation.blink_on_solar_grid_import ?? true)}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      automation: {
                        ...(current?.automation as Record<string, unknown>),
                        blink_on_solar_grid_import: event.target.checked
                      }
                    }))
                  }
                />
                <span>Parpadear si hay sol e importas de la red</span>
              </label>
            ) : null}

            {profile !== "tariff_price" ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <NumberField
                  label={profile === "consumption_gradient" ? "Bajo hasta W" : "Importacion baja hasta W"}
                  value={Number(automation.thresholds?.low_max_w ?? preset.thresholds.low_max_w)}
                  onChange={(value) =>
                    setDraft((current) => ({
                      ...current,
                      automation: {
                        ...(current?.automation as Record<string, unknown>),
                        thresholds: { ...((current?.automation as Record<string, unknown> | undefined)?.thresholds as Record<string, unknown> ?? {}), low_max_w: value }
                      }
                    }))
                  }
                />
                <NumberField
                  label={profile === "consumption_gradient" ? "Medio hasta W" : "Importacion media hasta W"}
                  value={Number(automation.thresholds?.medium_max_w ?? preset.thresholds.medium_max_w)}
                  onChange={(value) =>
                    setDraft((current) => ({
                      ...current,
                      automation: {
                        ...(current?.automation as Record<string, unknown>),
                        thresholds: { ...((current?.automation as Record<string, unknown> | undefined)?.thresholds as Record<string, unknown> ?? {}), medium_max_w: value }
                      }
                    }))
                  }
                />
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-3">
                {(["low", "medium", "high"] as const).map((tier) => (
                  <NumberField
                    key={tier}
                    label={`Precio ${tierLabel(profile, tier)} €/kWh`}
                    value={Number(automation.prices?.[tier] ?? preset.prices[tier])}
                    step="0.001"
                    onChange={(value) =>
                      setDraft((current) => ({
                        ...current,
                        automation: {
                          ...(current?.automation as Record<string, unknown>),
                          prices: { ...((current?.automation as Record<string, unknown> | undefined)?.prices as Record<string, unknown> ?? {}), [tier]: value }
                        }
                      }))
                    }
                  />
                ))}
              </div>
            )}

            <GradientPreview
              profile={profile}
              lowColor={String(automation.colors?.low ?? preset.colors.low)}
              mediumColor={String(automation.colors?.medium ?? preset.colors.medium)}
              highColor={String(automation.colors?.high ?? preset.colors.high)}
              surplusColor={String(automation.colors?.surplus ?? preset.colors.surplus)}
              lowMax={Number(automation.thresholds?.low_max_w ?? preset.thresholds.low_max_w)}
              mediumMax={Number(automation.thresholds?.medium_max_w ?? preset.thresholds.medium_max_w)}
              currentConsumption={Number(latest.data?.house_consumption_w ?? 0)}
              currentImport={Number(latest.data?.grid_import_w ?? 0)}
              currentExport={Number(latest.data?.grid_export_w ?? 0)}
              surplusEnabled={Boolean(automation.surplus_override)}
              activeTier={activeTier}
              prices={(automation.prices as Record<Tier, number> | undefined) ?? preset.prices}
            />

            <div className="grid gap-3 sm:grid-cols-2">
              {(["low", "medium", "high", "surplus"] as const).map((tier) => (
                <div key={tier} className="rounded-md border border-slate-200 p-3 dark:border-white/10">
                  <label className="flex flex-col gap-1">
                    <span className="label">Color {tierLabel(profile, tier)}</span>
                    <input
                      type="color"
                      value={String(automation.colors?.[tier] ?? preset.colors[tier])}
                      onChange={(event) =>
                        setDraft((current) => ({
                          ...current,
                          automation: {
                            ...(current?.automation as Record<string, unknown>),
                            colors: { ...((current?.automation as Record<string, unknown> | undefined)?.colors as Record<string, unknown> ?? {}), [tier]: event.target.value }
                          }
                        }))
                      }
                    />
                  </label>
                  <label className="mt-3 flex flex-col gap-1">
                    <span className="label">Brillo {tierLabel(profile, tier)} ({Number(automation.brightness?.[tier] ?? preset.brightness[tier])})</span>
                    <input
                      type="range"
                      min="0"
                      max="255"
                      value={Number(automation.brightness?.[tier] ?? preset.brightness[tier])}
                      onChange={(event) =>
                        setDraft((current) => ({
                          ...current,
                          automation: {
                            ...(current?.automation as Record<string, unknown>),
                            brightness: { ...((current?.automation as Record<string, unknown> | undefined)?.brightness as Record<string, unknown> ?? {}), [tier]: Number(event.target.value) }
                          }
                        }))
                      }
                    />
                  </label>
                </div>
              ))}
            </div>

            <div className="flex flex-wrap gap-2">
              <ActionButton disabled={busy} pending={saveMutation.isPending} onClick={() => saveMutation.mutate()} primary>
                Guardar configuracion
              </ActionButton>
              <ActionButton disabled={busy} pending={modeMutation.isPending} onClick={() => modeMutation.mutate("automatic")}>
                Modo automatico
              </ActionButton>
              <ActionButton disabled={busy} pending={applyMutation.isPending} onClick={() => applyMutation.mutate()}>
                Probar automatizacion ahora
              </ActionButton>
            </div>

            <p className="text-xs text-slate-500 dark:text-slate-400">
              `Aplicar color` cambia primero a manual para que la automatizacion no te lo sobrescriba. `Probar automatizacion ahora` aplica una vista previa inmediata con la ultima lectura.
            </p>
          </div>
        </div>
      </section>
    </div>
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

function NumberField({
  label,
  value,
  onChange,
  step = "1"
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: string;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="label">{label}</span>
      <input className="field" type="number" step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function GradientPreview({
  profile,
  lowColor,
  mediumColor,
  highColor,
  surplusColor,
  lowMax,
  mediumMax,
  currentConsumption,
  currentImport,
  currentExport,
  surplusEnabled,
  activeTier,
  prices
}: {
  profile: AutomationProfile;
  lowColor: string;
  mediumColor: string;
  highColor: string;
  surplusColor: string;
  lowMax: number;
  mediumMax: number;
  currentConsumption: number;
  currentImport: number;
  currentExport: number;
  surplusEnabled: boolean;
  activeTier: Tier;
  prices: Record<Tier, number>;
}) {
  const safeLowMax = Math.max(1, lowMax);
  const safeMediumMax = Math.max(safeLowMax + 1, mediumMax);
  const focusValue = profile === "consumption_gradient" ? currentConsumption : currentImport;
  const previewMax = Math.max(safeMediumMax * 1.2, safeMediumMax + 300);
  const markerLeft = clamp((focusValue / previewMax) * 100, 0, 100);
  const useSpecialState = profile === "consumption_gradient" && surplusEnabled && currentExport > 0;
  const tariffMarker = profile === "tariff_price" ? { low: 16, medium: 50, high: 84, surplus: 84 }[activeTier] : markerLeft;

  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-white/10">
      <div className="flex items-center justify-between gap-3 text-xs text-slate-500 dark:text-slate-400">
        <span>
          {profile === "consumption_gradient"
            ? "Preview del degradado"
            : profile === "grid_import_alert"
              ? "Preview de alerta de importacion"
              : "Preview precio horario"}
        </span>
        <span>
          {profile === "tariff_price"
            ? `${tierLabel(profile, activeTier)}: ${Number(prices[activeTier] ?? 0).toFixed(3)} €/kWh`
            : useSpecialState
            ? `Excedente activo: ${formatW(currentExport)}`
            : profile === "consumption_gradient"
              ? `Consumo actual: ${formatW(currentConsumption)}`
              : `Importacion actual: ${formatW(currentImport)}`}
        </span>
      </div>
      <div
        className="relative mt-3 h-4 overflow-hidden rounded-full"
        style={{
          background:
            profile === "tariff_price"
              ? `linear-gradient(90deg, ${lowColor} 0%, ${lowColor} 33%, ${mediumColor} 33%, ${mediumColor} 66%, ${highColor} 66%, ${highColor} 100%)`
              : profile === "consumption_gradient"
              ? `linear-gradient(90deg, ${lowColor} 0%, ${mediumColor} ${Math.round((safeLowMax / previewMax) * 100)}%, ${highColor} ${Math.round((safeMediumMax / previewMax) * 100)}%, ${highColor} 100%)`
              : `linear-gradient(90deg, ${lowColor} 0%, ${lowColor} ${Math.round((safeLowMax / previewMax) * 100)}%, ${mediumColor} ${Math.round((safeLowMax / previewMax) * 100)}%, ${highColor} ${Math.round((safeMediumMax / previewMax) * 100)}%, ${surplusColor} 100%)`
        }}
      >
        {!useSpecialState ? (
          <div
            className="absolute top-1/2 h-6 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white bg-slate-950 shadow-sm"
            style={{ left: `${tariffMarker}%` }}
          />
        ) : null}
      </div>
      {profile === "tariff_price" ? (
        <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-slate-500 dark:text-slate-400">
          <span>Valle</span>
          <span>Llano</span>
          <span>Punta</span>
        </div>
      ) : (
        <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-slate-500 dark:text-slate-400">
          <span>0 W</span>
          <span>{safeLowMax} W</span>
          <span>{safeMediumMax} W</span>
          <span>{Math.round(previewMax)} W</span>
        </div>
      )}
      <div className="mt-3 flex items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
        <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: lowColor }} />
        <span>{tierLabel(profile, "low")}</span>
        <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: mediumColor }} />
        <span>{tierLabel(profile, "medium")}</span>
        <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: highColor }} />
        <span>{tierLabel(profile, "high")}</span>
        <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: surplusColor }} />
        <span>{tierLabel(profile, "surplus")}</span>
      </div>
    </div>
  );
}
