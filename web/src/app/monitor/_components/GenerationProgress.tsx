"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { EventEnvelope } from "@/lib/api/runs";

export function GenerationProgress({ events }: { events: EventEnvelope[] }) {
  const byGen = new Map<number, { backtests: number; verdicts: { accepted: number; rejected: number }; vetoes: number; bestSharpe: number | null; }>();

  for (const e of events) {
    const gen = e.generation ?? -1;
    if (gen < 0) continue;
    const slot = byGen.get(gen) ?? { backtests: 0, verdicts: { accepted: 0, rejected: 0 }, vetoes: 0, bestSharpe: null };

    if (e.event_type === "EvtBacktestDone") {
      slot.backtests++;
      const s = e.payload?.sharpe;
      if (typeof s === "number" && (slot.bestSharpe === null || s > slot.bestSharpe)) slot.bestSharpe = s;
    } else if (e.event_type === "EvtRatchetVerdict") {
      if (e.payload?.accepted) slot.verdicts.accepted++;
      else slot.verdicts.rejected++;
    } else if (e.event_type === "EvtCriticVerdict") {
      if (!e.payload?.accepted) slot.vetoes++;
    }

    byGen.set(gen, slot);
  }

  const gens = Array.from(byGen.keys()).sort((a, b) => a - b);

  return (
    <div className="rounded-lg border overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Gen</TableHead>
            <TableHead className="text-right">Backtests</TableHead>
            <TableHead className="text-right">Accepted</TableHead>
            <TableHead className="text-right">Rejected</TableHead>
            <TableHead className="text-right">Vetoes</TableHead>
            <TableHead className="text-right">Best Sharpe</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {gens.map((g) => {
            const s = byGen.get(g)!;
            return (
              <TableRow key={g}>
                <TableCell>{g}</TableCell>
                <TableCell className="text-right">{s.backtests}</TableCell>
                <TableCell className="text-right text-green-500">{s.verdicts.accepted}</TableCell>
                <TableCell className="text-right text-red-500">{s.verdicts.rejected}</TableCell>
                <TableCell className="text-right text-orange-500">{s.vetoes}</TableCell>
                <TableCell className="text-right">{s.bestSharpe?.toFixed(2) ?? "—"}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
