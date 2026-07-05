import type { EChartsOption } from "echarts";
import type { Aggregate, Measurement } from "../api/types";

export function powerLineOption(rows: Measurement[] | Aggregate[], resolution: string): EChartsOption {
  const points = normalizeRows(rows, resolution);
  return {
    color: ["#f59e0b", "#ef4444", "#2563eb", "#10b981", "#8b5cf6"],
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { top: 52, left: 50, right: 20, bottom: 70 },
    toolbox: { feature: { dataZoom: {}, saveAsImage: {} } },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 24 }],
    xAxis: { type: "time" },
    yAxis: { type: "value", name: resolution === "raw" ? "W" : "kWh" },
    series: [
      { name: "Solar", type: "line", smooth: true, symbol: "none", data: points.map((p) => [p.time, p.solar]) },
      { name: "Consumo", type: "line", smooth: true, symbol: "none", data: points.map((p) => [p.time, p.consumption]) },
      { name: "Importacion", type: "line", smooth: true, symbol: "none", data: points.map((p) => [p.time, p.imported]) },
      { name: "Exportacion", type: "line", smooth: true, symbol: "none", data: points.map((p) => [p.time, p.exported]) },
      { name: "Autoconsumo", type: "line", smooth: true, symbol: "none", data: points.map((p) => [p.time, p.self]) }
    ]
  };
}

export function flowAreaOption(rows: Measurement[] | Aggregate[], resolution: string): EChartsOption {
  const points = normalizeRows(rows, resolution);
  return {
    color: ["#f59e0b", "#2563eb", "#10b981"],
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { top: 52, left: 50, right: 20, bottom: 70 },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 24 }],
    xAxis: { type: "time" },
    yAxis: { type: "value" },
    series: [
      { name: "Autoconsumo", type: "line", stack: "flow", areaStyle: {}, symbol: "none", data: points.map((p) => [p.time, p.self]) },
      { name: "Importacion", type: "line", stack: "flow", areaStyle: {}, symbol: "none", data: points.map((p) => [p.time, p.imported]) },
      { name: "Exportacion", type: "line", stack: "flow", areaStyle: {}, symbol: "none", data: points.map((p) => [p.time, p.exported]) }
    ]
  };
}

export function hourlyBarOption(rows: Measurement[] | Aggregate[], resolution: string): EChartsOption {
  const points = normalizeRows(rows, resolution);
  const buckets = new Map<number, { solar: number; consumption: number }>();
  points.forEach((point) => {
    const hour = new Date(point.time).getHours();
    const current = buckets.get(hour) ?? { solar: 0, consumption: 0 };
    current.solar += point.solar;
    current.consumption += point.consumption;
    buckets.set(hour, current);
  });
  const hours = Array.from({ length: 24 }, (_, index) => index);
  return {
    color: ["#f59e0b", "#ef4444"],
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { top: 52, left: 45, right: 20, bottom: 35 },
    xAxis: { type: "category", data: hours.map((hour) => `${hour}:00`) },
    yAxis: { type: "value" },
    series: [
      { name: "Solar", type: "bar", data: hours.map((hour) => buckets.get(hour)?.solar ?? 0) },
      { name: "Consumo", type: "bar", data: hours.map((hour) => buckets.get(hour)?.consumption ?? 0) }
    ]
  };
}

export function heatmapOption(rows: Measurement[] | Aggregate[], resolution: string): EChartsOption {
  const points = normalizeRows(rows, resolution);
  const data = points.map((point) => {
    const date = new Date(point.time);
    return [date.getHours(), date.getDay(), Math.round(point.consumption)];
  });
  return {
    tooltip: { position: "top" },
    grid: { top: 20, left: 55, right: 20, bottom: 40 },
    xAxis: { type: "category", data: Array.from({ length: 24 }, (_, i) => `${i}`), splitArea: { show: true } },
    yAxis: { type: "category", data: ["Dom", "Lun", "Mar", "Mie", "Jue", "Vie", "Sab"], splitArea: { show: true } },
    visualMap: { min: 0, max: 5000, calculable: true, orient: "horizontal", left: "center", bottom: 0 },
    series: [{ name: "Consumo", type: "heatmap", data }]
  };
}

function normalizeRows(rows: Measurement[] | Aggregate[], resolution: string) {
  return [...rows]
    .reverse()
    .map((row) => {
      if (resolution === "raw" && "timestamp_utc" in row) {
        return {
          time: row.timestamp_local,
          solar: row.solar_w ?? 0,
          consumption: row.house_consumption_w ?? 0,
          imported: row.grid_import_w ?? 0,
          exported: row.grid_export_w ?? 0,
          self: row.solar_self_consumption_w ?? 0
        };
      }
      const aggregate = row as Aggregate;
      return {
        time: aggregate.period_start_local,
        solar: aggregate.solar_kwh,
        consumption: aggregate.house_consumption_kwh,
        imported: aggregate.grid_import_kwh,
        exported: aggregate.grid_export_kwh,
        self: aggregate.solar_self_consumption_kwh
      };
    });
}
