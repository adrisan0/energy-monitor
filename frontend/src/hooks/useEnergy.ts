import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useLatest() {
  return useQuery({
    queryKey: ["latest"],
    queryFn: api.latest,
    refetchInterval: 30_000
  });
}

export function useSystemStatus() {
  return useQuery({
    queryKey: ["system-status"],
    queryFn: api.status,
    refetchInterval: 30_000
  });
}

export function useDaikinLatest() {
  return useQuery({
    queryKey: ["daikin-latest"],
    queryFn: api.daikinLatest,
    refetchInterval: 60_000
  });
}

export function useDaikinReadings(range: string) {
  return useQuery({
    queryKey: ["daikin-readings", range],
    queryFn: () => api.daikinReadings(range),
    refetchInterval: 60_000
  });
}

export function useSmartPlugReadings(deviceId: number | null, range: string) {
  return useQuery({
    queryKey: ["smart-plug-readings", deviceId, range],
    queryFn: () => api.smartPlugReadings(deviceId as number, range),
    enabled: deviceId != null,
    refetchInterval: 60_000
  });
}

export function useMeasurements(resolution: string, range: string) {
  return useQuery({
    queryKey: ["measurements", resolution, range],
    queryFn: () => api.measurements(resolution, range),
    refetchInterval: resolution === "raw" ? 30_000 : 60_000
  });
}

export function useDevices() {
  return useQuery({
    queryKey: ["devices"],
    queryFn: api.devices,
    refetchInterval: 30_000
  });
}

export function useDeviceState(deviceId: number | null) {
  return useQuery({
    queryKey: ["device-state", deviceId],
    queryFn: () => api.deviceState(deviceId as number),
    enabled: deviceId != null,
    refetchInterval: 10_000
  });
}
