import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import { api } from "../api/client";
import type { Tariff } from "../api/types";
import { formatKwh, formatMoney } from "../utils/format";

export default function MoneyPage() {
  const [period, setPeriod] = useState("day");
  const [token, setToken] = useState("");
  const queryClient = useQueryClient();
  const summary = useQuery({ queryKey: ["summary", period], queryFn: () => api.summary(period), refetchInterval: 60_000 });
  const comparison = useQuery({ queryKey: ["comparison", period], queryFn: () => api.comparison(period), refetchInterval: 60_000 });
  const tariff = useQuery({ queryKey: ["tariff"], queryFn: api.tariff });
  const [form, setForm] = useState<Tariff | null>(null);

  useEffect(() => {
    if (tariff.data) setForm(tariff.data);
  }, [tariff.data]);

  const saveTariff = useMutation({
    mutationFn: () => {
      if (!form) throw new Error("Sin tarifa");
      return api.updateTariff(form, token);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tariff"] })
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">Energia y dinero</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Estimaciones configurables</p>
        </div>
        <select className="field" value={period} onChange={(event) => setPeriod(event.target.value)}>
          <option value="day">Diario</option>
          <option value="month">Mensual</option>
        </select>
      </div>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Amount label="kWh producidos" value={formatKwh(summary.data?.solar_kwh)} />
        <Amount label="kWh importados" value={formatKwh(summary.data?.grid_import_kwh)} />
        <Amount label="kWh exportados" value={formatKwh(summary.data?.grid_export_kwh)} />
        <Amount label="kWh autoconsumidos" value={formatKwh(summary.data?.solar_self_consumption_kwh)} />
        <Amount label="Autosuficiencia" value={summary.data?.self_sufficiency_percent == null ? "-- %" : `${summary.data.self_sufficiency_percent.toFixed(1)} %`} />
        <Amount label="Excedentes vertidos" value={summary.data?.surplus_export_percent == null ? "-- %" : `${summary.data.surplus_export_percent.toFixed(1)} %`} />
        <Amount label="Cambio consumo" value={comparison.data ? formatKwh(comparison.data.delta_house_consumption_kwh) : "--"} />
        <Amount label="Cambio coste neto" value={comparison.data ? formatMoney(comparison.data.delta_net_cost_eur) : "--"} />
      </section>

      <section className="panel p-4">
        <h3 className="text-base font-semibold">Desglose estimado</h3>
        <div className="mt-4 grid gap-3 md:grid-cols-5">
          <Breakdown label="Coste variable" value={formatMoney(summary.data?.estimated_cost_eur)} />
          <Breakdown label="+ Costes fijos" value={formatMoney(summary.data?.fixed_cost_eur)} />
          <Breakdown label="+ Impuestos" value={formatMoney(summary.data?.taxes_eur)} />
          <Breakdown label="- Compensacion" value={formatMoney(summary.data?.compensation_eur)} />
          <Breakdown label="= Coste final" value={formatMoney(summary.data?.net_cost_eur)} strong />
        </div>
        <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">{summary.data?.note}</p>
      </section>

      <section className="panel p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-base font-semibold">Tarifa configurable</h3>
          <div className="flex gap-2">
            <input className="field w-48" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Token admin" type="password" />
            <button type="button" onClick={() => saveTariff.mutate()} className="inline-flex h-10 items-center gap-2 rounded-md bg-slate-900 px-3 text-sm font-medium text-white dark:bg-white dark:text-slate-950">
              <Save className="h-4 w-4" aria-hidden />
              Guardar
            </button>
          </div>
        </div>
        {form ? (
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <SelectField label="Modo" value={form.mode} onChange={(value) => setForm({ ...form, mode: value as Tariff["mode"] })} />
            <TariffField label="Precio plano EUR/kWh" value={form.flat_price_eur_per_kwh} onChange={(value) => setForm({ ...form, flat_price_eur_per_kwh: value })} />
            <TariffField label="Punta EUR/kWh" value={form.peak_price_eur_per_kwh} onChange={(value) => setForm({ ...form, peak_price_eur_per_kwh: value })} />
            <TariffField label="Llano EUR/kWh" value={form.shoulder_price_eur_per_kwh} onChange={(value) => setForm({ ...form, shoulder_price_eur_per_kwh: value })} />
            <TariffField label="Valle EUR/kWh" value={form.valley_price_eur_per_kwh} onChange={(value) => setForm({ ...form, valley_price_eur_per_kwh: value })} />
            <TariffField label="Compensacion EUR/kWh" value={form.surplus_compensation_eur_per_kwh} onChange={(value) => setForm({ ...form, surplus_compensation_eur_per_kwh: value })} />
            <TariffField label="Coste fijo mensual" value={form.monthly_fixed_cost_eur} onChange={(value) => setForm({ ...form, monthly_fixed_cost_eur: value })} />
            <TariffField label="Alquiler contador" value={form.meter_rental_monthly_eur} onChange={(value) => setForm({ ...form, meter_rental_monthly_eur: value })} />
            <TariffField label="Impuesto electrico %" value={form.electricity_tax_percent} onChange={(value) => setForm({ ...form, electricity_tax_percent: value })} />
            <TariffField label="IVA %" value={form.vat_percent} onChange={(value) => setForm({ ...form, vat_percent: value })} />
          </div>
        ) : null}
        {saveTariff.error ? <p className="mt-3 text-sm text-red-500">{String(saveTariff.error.message)}</p> : null}
      </section>
    </div>
  );
}

function Amount({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <p className="label">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function Breakdown({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={`rounded-md p-3 ${strong ? "bg-slate-900 text-white dark:bg-white dark:text-slate-950" : "bg-slate-100 dark:bg-white/5"}`}>
      <p className="text-xs opacity-75">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}

function TariffField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <input className="field mt-1 w-full" value={value} onChange={(event) => onChange(event.target.value)} inputMode="decimal" />
    </label>
  );
}

function SelectField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <select className="field mt-1 w-full" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="flat">Precio plano</option>
        <option value="time_of_use">Punta / llano / valle</option>
        <option value="future_pvpc">PVPC futuro</option>
      </select>
    </label>
  );
}
