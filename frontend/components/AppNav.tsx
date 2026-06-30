"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Start" },
  { href: "/workspace", label: "Workspace" },
  { href: "/knowledge-base", label: "Knowledge Base" },
  { href: "/docs-query", label: "Query from Doc" },
  { href: "/rfp-parser", label: "RFP Parser" },
  { href: "/insight-studio", label: "Insight Studio" },
  { href: "/planner", label: "Planner" },
  { href: "/timeline", label: "Timeline Builder" },
  { href: "/workflow-maker", label: "Workflow Maker" },
  { href: "/settings", label: "Settings" },
];

export function AppNav() {
  const pathname = usePathname();
  return (
    <div className="sticky top-0 z-30 border-b border-border/70 bg-background/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl gap-2 overflow-x-auto px-4 py-3">
        {LINKS.map((link) => {
          const active =
            pathname === link.href || (link.href !== "/" && pathname?.startsWith(link.href));
          return (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "whitespace-nowrap rounded-full border px-4 py-2 text-sm transition",
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-card text-muted-foreground hover:text-foreground"
              )}
            >
              {link.label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
