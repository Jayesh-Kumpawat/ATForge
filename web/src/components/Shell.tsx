"use client";

import { Activity, BookOpen, Moon, Sun, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/monitor", label: "Monitor", icon: Activity },
  { href: "/strategies", label: "Library", icon: BookOpen },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="hidden md:flex w-56 flex-col border-r border-border p-4 gap-2">
        <div className="text-lg font-semibold mb-4">ATForge</div>

        <nav className="flex flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent",
                  active && "bg-accent font-medium",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto flex items-center justify-between gap-2 pt-4 border-t border-border">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label="Toggle theme"
          >
            <Sun className="size-4 hidden dark:block" />
            <Moon className="size-4 block dark:hidden" />
          </Button>
          <Button variant="ghost" size="sm" aria-label="Settings">
            <Settings className="size-4" />
          </Button>
        </div>
      </aside>

      <main className="flex-1 p-6 overflow-x-hidden">{children}</main>
    </div>
  );
}
