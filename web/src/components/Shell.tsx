"use client";

import { LayoutDashboard, Activity, ListOrdered, BookOpen, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard, exact: true },
  { href: "/monitor", label: "Monitor", icon: Activity, exact: false },
  { href: "/runs", label: "Runs", icon: ListOrdered, exact: false },
  { href: "/strategies", label: "Strategies", icon: BookOpen, exact: false },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="hidden md:flex w-52 shrink-0 flex-col border-r border-border bg-surface">
        <div className="border-b border-border px-4 py-4">
          <div className="text-sm font-bold tracking-tight">ATForge</div>
          <div className="mt-0.5 text-[11px] text-text-muted">Agentic Trading Forge</div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3">
          {NAV.map(({ href, label, icon: Icon, exact }) => {
            const active = exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-primary/12 font-medium text-primary"
                    : "text-text-secondary hover:bg-accent hover:text-foreground",
                )}
              >
                <Icon className="size-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-border p-3">
          <button
            type="button"
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-text-secondary hover:bg-accent hover:text-foreground"
          >
            {resolvedTheme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            {resolvedTheme === "dark" ? "Light mode" : "Dark mode"}
          </button>
        </div>
      </aside>

      <div className="md:hidden fixed inset-x-0 top-0 z-20 flex h-12 items-center justify-between border-b border-border bg-surface px-4">
        <span className="text-sm font-bold">ATForge</span>
        <div className="flex gap-1">
          {NAV.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "rounded px-2 py-1 text-xs",
                (href === "/" ? pathname === href : pathname.startsWith(href))
                  ? "bg-primary/12 text-primary"
                  : "text-text-muted",
              )}
            >
              {label}
            </Link>
          ))}
        </div>
      </div>

      <main className="flex-1 overflow-x-hidden p-6 pt-16 md:pt-6">{children}</main>
    </div>
  );
}
