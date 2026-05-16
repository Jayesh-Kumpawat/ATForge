"use client";

import { cn } from "@/lib/utils";

export interface Column<T> {
  key: string;
  label: string;
  align?: "left" | "right";
  sortable?: boolean;
  render: (row: T) => React.ReactNode;
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  sortKey?: string;
  sortDir?: "asc" | "desc";
  onSort?: (key: string) => void;
  onRowClick?: (row: T) => void;
  empty?: React.ReactNode;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  sortKey,
  sortDir,
  onSort,
  onRowClick,
  empty,
}: Props<T>) {
  if (rows.length === 0 && empty) return <>{empty}</>;

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-elevated">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border">
            {columns.map((c) => {
              const isSorted = sortKey === c.key;
              const clickable = c.sortable && onSort;
              return (
                <th
                  key={c.key}
                  onClick={clickable ? () => onSort!(c.key) : undefined}
                  className={cn(
                    "px-3 py-2 text-[10px] font-medium uppercase tracking-wide text-text-muted",
                    c.align === "right" ? "text-right" : "text-left",
                    clickable && "cursor-pointer select-none hover:text-foreground",
                    isSorted && "text-primary",
                  )}
                >
                  {c.label}
                  {isSorted ? <span className="ml-1">{sortDir === "asc" ? "▲" : "▼"}</span> : null}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cn(
                "border-b border-border/60 last:border-0",
                onRowClick && "cursor-pointer hover:bg-accent/40",
              )}
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={cn(
                    "px-3 py-2 text-foreground",
                    c.align === "right" && "text-right",
                  )}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
