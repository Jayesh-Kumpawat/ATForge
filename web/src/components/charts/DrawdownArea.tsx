"use client";

import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

interface Props {
  data: Array<{ t: number; drawdown: number }>;
}

export function DrawdownArea({ data }: Props) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data}>
        <CartesianGrid strokeDasharray="3 3" className="opacity-20" />
        <XAxis dataKey="t" tickFormatter={(t) => new Date(t).toLocaleDateString()} className="text-xs" />
        <YAxis className="text-xs" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
        <Tooltip
          labelFormatter={(t) => new Date(t).toLocaleDateString()}
          formatter={(value) => [typeof value === "number" ? `${(value * 100).toFixed(2)}%` : String(value), "Drawdown"]}
        />
        <Area type="monotone" dataKey="drawdown" stroke="#ef4444" fill="#ef4444" fillOpacity={0.3} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
