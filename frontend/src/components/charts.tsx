import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

/* Chart conventions (dataviz method): thin marks, 2px lines, recessive grid, one axis,
   categorical slots in fixed order (series-1 blue, series-2 orange), text in ink tokens,
   legend for >= 2 series, hover tooltips on every mark. */

const axisTick = { fill: "var(--muted)", fontSize: 12 };

function TipBox({ title, rows }: { title: ReactNode; rows: { color?: string; label: string; value: ReactNode }[] }) {
  return (
    <div className="card px-3 py-2 text-[12.5px]" style={{ boxShadow: "var(--shadow-lg)" }}>
      <div className="mb-1 font-medium text-ink">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2 text-ink-2">
          {r.color && <span className="inline-block h-0.5 w-3 rounded" style={{ background: r.color }} />}
          <span className="font-semibold text-ink tabular">{r.value}</span>
          <span>{r.label}</span>
        </div>
      ))}
    </div>
  );
}

export function TrendChart({ data, series, xKey, xFormat, height = 260 }: {
  data: any[]; series: { key: string; label: string; color: string }[]; xKey: string; xFormat: (v: string) => string; height?: number;
}) {
  const last = data.length - 1;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 16, right: 56, bottom: 0, left: -8 }}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey={xKey} tickFormatter={xFormat} tick={axisTick} axisLine={{ stroke: "var(--axis)" }} tickLine={false} />
        <YAxis tick={axisTick} axisLine={false} tickLine={false} allowDecimals={false} width={44} />
        <Tooltip cursor={{ stroke: "var(--axis)", strokeWidth: 1 }}
          content={({ active, payload, label }) => active && payload?.length ? (
            <TipBox title={xFormat(String(label))} rows={series.map((s) => ({ color: s.color, label: s.label, value: (payload.find((p) => p.dataKey === s.key)?.value as number)?.toLocaleString() }))} />
          ) : null} />
        <Legend verticalAlign="top" align="left" height={28} iconType="plainline"
          formatter={(v) => <span style={{ color: "var(--text-2)", fontSize: 12.5 }}>{v}</span>} />
        {series.map((s) => (
          <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2}
            dot={{ r: 3, strokeWidth: 0, fill: s.color }} activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }}>
            <LabelList dataKey={s.key} content={(p: any) => p.index === last ? (
              <text x={p.x + 8} y={p.y + 4} fontSize={12} fill="var(--text-2)">{s.label}</text>) : null} />
          </Line>
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function HBarChart({ data, labelKey, valueKey, valueLabel, format = (v: number) => v.toLocaleString(), height, onSelect }: {
  data: any[]; labelKey: string; valueKey: string; valueLabel: string; format?: (v: number) => string; height?: number;
  onSelect?: (row: any) => void;
}) {
  const h = height ?? Math.max(120, data.length * 34 + 16);
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 64, bottom: 0, left: 0 }} barCategoryGap={8}>
        <CartesianGrid horizontal={false} stroke="var(--grid)" />
        <XAxis type="number" hide />
        <YAxis type="category" dataKey={labelKey} width={170} tick={{ ...axisTick, fill: "var(--text-2)" }} axisLine={false} tickLine={false}
          tickFormatter={(v: string) => (v.length > 24 ? v.slice(0, 23) + "…" : v)} />
        <Tooltip cursor={{ fill: "var(--surface-3)" }}
          content={({ active, payload }) => active && payload?.length ? (
            <TipBox title={payload[0].payload[labelKey]} rows={[{ color: "var(--series-1)", label: valueLabel, value: format(payload[0].value as number) }]} />
          ) : null} />
        <Bar dataKey={valueKey} fill="var(--series-1)" radius={[0, 4, 4, 0]} maxBarSize={22}
          cursor={onSelect ? "pointer" : undefined} onClick={(d: any) => onSelect?.(d.payload ?? d)}>
          <LabelList dataKey={valueKey} content={(p: any) => (
            <text x={p.x + p.width + 6} y={p.y + p.height / 2} dy={4} fontSize={12} fill="var(--text-2)" className="tabular">{format(p.value)}</text>
          )} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
