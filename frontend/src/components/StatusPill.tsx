interface StatusPillProps {
  ok: boolean;
  label: string;
}

export default function StatusPill({ ok, label }: StatusPillProps) {
  return (
    <span
      className={`inline-flex min-h-8 items-center rounded-md px-3 text-sm font-medium ${
        ok
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200"
          : "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-200"
      }`}
    >
      {label}
    </span>
  );
}
