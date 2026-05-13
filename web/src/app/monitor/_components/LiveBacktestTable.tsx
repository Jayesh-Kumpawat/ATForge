"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { EventEnvelope } from "@/lib/api/runs";
import { SHARPE_COLOR } from "@/lib/constants";

export function LiveBacktestTable({ events }: { events: EventEnvelope[] }) {
  const backtests = events
    .filter((e) => e.event_type === "EvtBacktestDone")
    .slice(-50)
    .reverse();

  return (
    <div className="rounded-lg border overflow-x-auto">
      <div className="px-4 pt-3 pb-2 text-sm font-medium">Live Backtests (latest 50)</div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Symbol</TableHead>
            <TableHead>Strategy</TableHead>
            <TableHead className="text-right">Sharpe</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {backtests.map((e) => (
            <TableRow key={e.event_id}>
              <TableCell>{String(e.payload?.symbol ?? "")}</TableCell>
              <TableCell className="font-medium">{String(e.payload?.strategy ?? "")}</TableCell>
              <TableCell className={`text-right ${SHARPE_COLOR(typeof e.payload?.sharpe === "number" ? e.payload.sharpe : null)}`}>
                {typeof e.payload?.sharpe === "number" ? e.payload.sharpe.toFixed(2) : "—"}
              </TableCell>
              <TableCell>{e.payload?.success ? "✓" : "✗"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
