"use client";

import { Activity, BookOpen, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/monitor",    label: "Monitor",  icon: Activity,  desc: "Live pipeline" },
  { href: "/strategies", label: "Library",  icon: BookOpen,  desc: "All strategies" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      {/* Sidebar */}
      <aside className="hidden md:flex w-56 flex-col border-r border-border bg-card shrink-0">
        {/* Brand */}
        <div className="px-4 py-5 border-b border-border">
          <div className="text-base font-bold tracking-tight">ATForge</div>
          <div className="text-xs text-muted-foreground mt-0.5">Agentic Trading Forge</div>
        </div>

        {/* Nav */}
        <nav className="flex flex-col gap-1 p-3 flex-1">
          {NAV.map(({ href, label, icon: Icon, desc }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors",
                  active
                    ? "bg-primary text-primary-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )}
              >
                <Icon className="size-4 shrink-0" />
                <div className="flex flex-col">
                  <span className="leading-none">{label}</span>
                  <span className={cn("text-xs mt-0.5 leading-none", active ? "text-primary-foreground/70" : "text-muted-foreground")}>{desc}</span>
                </div>
              </Link>
            );
          })}
        </nav>

        {/* Theme toggle */}
        <div className="p-3 border-t border-border">
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start gap-2 text-muted-foreground"
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
          >
            {resolvedTheme === "dark"
              ? <><Sun className="size-4" /> Light mode</>
              : <><Moon className="size-4" /> Dark mode</>
            }
          </Button>
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 inset-x-0 z-20 flex items-center justify-between px-4 h-12 bg-card border-b border-border">
        <span className="font-bold text-sm">ATForge</span>
        <div className="flex gap-1">
          {NAV.map(({ href, label }) => (
            <Link key={href} href={href} className={cn(
              "text-xs px-2 py-1 rounded",
              pathname.startsWith(href) ? "bg-primary text-primary-foreground" : "text-muted-foreground"
            )}>{label}</Link>
          ))}
        </div>
      </div>

      {/* Content */}
      <main className="flex-1 p-6 md:p-6 pt-16 md:pt-6 overflow-x-hidden min-h-screen">
        {children}
      </main>
    </div>
  );
}
