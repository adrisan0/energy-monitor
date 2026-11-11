import type {
  Annotation,
  Device,
  DaikinLatestResponse,
  DaikinReadingsResponse,
  DeviceColorUpdate,
  DeviceModeUpdate,
  DeviceState,
  DeviceUpdate,
  EnergyComparison,
  EnergySummary,
  EventResponse,
  LatestResponse,
  MessageResponse,
  MeasurementsResponse,
  RawPayload,
  SystemStatus,
  SmartPlugReadingsResponse,
  Tariff
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  latest: () => request<LatestResponse>("/latest"),
  status: () => request<SystemStatus>("/system/status"),
  daikinLatest: () => request<DaikinLatestResponse>("/climate/daikin/latest"),
  daikinReadings: (range: string) => request<DaikinReadingsResponse>(`/climate/daikin/readings?${range}&limit=20000`),
  smartPlugReadings: (deviceId: number, range: string) => request<SmartPlugReadingsResponse>(`/smart-plugs/readings?device_id=${deviceId}&${range}&limit=50000`),
  measurements: (resolution: string, range: string) =>
    request<MeasurementsResponse>(`/measurements?resolution=${resolution}&${range}&limit=50000`),
  rawLatest: () => request<RawPayload>("/measurements/raw/latest"),
  summary: (period = "day") => request<EnergySummary>(`/energy/summary?period=${period}`),
  comparison: (period = "day") => request<EnergyComparison>(`/energy/comparison?period=${period}`),
  tariff: () => request<Tariff>("/tariff"),
  updateTariff: (payload: Tariff, token: string) =>
    request<Tariff>("/tariff", {
      method: "PUT",
      headers: { "X-Admin-Token": token },
      body: JSON.stringify(payload)
    }),
  annotations: () => request<Annotation[]>("/annotations"),
  createAnnotation: (payload: Omit<Annotation, "id">) =>
    request<Annotation>("/annotations", { method: "POST", body: JSON.stringify(payload) }),
  devices: () => request<Device[]>("/devices"),
  deviceState: (deviceId: number) => request<DeviceState>(`/devices/${deviceId}/state`),
  updateDevice: (deviceId: number, payload: DeviceUpdate, token: string) =>
    request<Device>(`/devices/${deviceId}`, {
      method: "PATCH",
      headers: { "X-Admin-Token": token },
      body: JSON.stringify(payload)
    }),
  deviceTurnOn: (deviceId: number, token: string) =>
    request<MessageResponse>(`/devices/${deviceId}/on`, { method: "POST", headers: { "X-Admin-Token": token } }),
  deviceTurnOff: (deviceId: number, token: string) =>
    request<MessageResponse>(`/devices/${deviceId}/off`, { method: "POST", headers: { "X-Admin-Token": token } }),
  deviceSetColor: (deviceId: number, payload: DeviceColorUpdate, token: string) =>
    request<MessageResponse>(`/devices/${deviceId}/color`, {
      method: "POST",
      headers: { "X-Admin-Token": token },
      body: JSON.stringify(payload)
    }),
  deviceSetMode: (deviceId: number, payload: DeviceModeUpdate, token: string) =>
    request<MessageResponse>(`/devices/${deviceId}/mode`, {
      method: "POST",
      headers: { "X-Admin-Token": token },
      body: JSON.stringify(payload)
    }),
  deviceApplyAutomation: (deviceId: number, token: string) =>
    request<MessageResponse>(`/devices/${deviceId}/apply-automation`, {
      method: "POST",
      headers: { "X-Admin-Token": token }
    }),
  events: () => request<EventResponse>("/events"),
  backupsRun: (token: string) =>
    request("/backups/run", { method: "POST", headers: { "X-Admin-Token": token } }),
  csvUrl: (range: string) => `${API_BASE}/export/csv?${range}`
};
