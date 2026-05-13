"use client";

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { useTheme } from "next-themes";

interface Props {
  data: Array<{ t: number; equity: number }>;
}

export function EquityCurve({ data }: Props) {
  const { resolvedTheme } = useTheme();
  const stroke = resolvedTheme === "dark" ? "#a3e635" : "#16a34a";

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" className="opacity-20" />
        <XAxis dataKey="t" tickFormatter={(t) => new Date(t).toLocaleDateString()} className="text-xs" />
        <YAxis className="text-xs" domain={["auto", "auto"]} tickFormatter={(v) => v.toFixed(0)} />
        <Tooltip
          labelFormatter={(t) => new Date(t).toLocaleDateString()}
          formatter={(value) => [typeof value === "number" ? value.toFixed(2) : String(value), "Equity"]}
        />
        <Line type="monotone" dataKey="equity" stroke={stroke} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
