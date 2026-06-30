"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  Cpu,
  FileSearch,
  Gauge,
  Network,
  ShieldAlert,
  Users2,
} from "lucide-react";
import { api } from "@/lib/api";
import type { InsightItem, InsightResponse } from "@/lib/types";
import { useProposalStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const FOCUS = ["Scope", "Leakage", "Mandays", "Hardware", "Roles", "Evidence"];

function severityTone(severity: InsightItem["severity"]) {
  if (severity === "high") return "border-red-300 bg-red-50 text-red-900";
  if (severity === "medium") return "border-amber-300 bg-amber-50 text-amber-950";
  return "border-emerald-300 bg-emerald-50 text-emerald-950";
}

function ItemList({ items, empty }: { items: InsightItem[]; empty: string }) {
  if (!items.length) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <div className="grid gap-3">
      {items.map((item) => (
        <div key={`${item.title}-${item.detail}`} className={cn("rounded-md border p-3", severityTone(item.severity))}>
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold">{item.title}</div>
            <span className="text-[10px] uppercase tracking-wide">{item.severity}</span>
          </div>
          <p className="mt-1 text-sm leading-5">{item.detail}</p>
          {item.action ? <p className="mt-2 text-xs leading-5 opacity-80">Action: {item.action}</p> : null}
          {item.evidence.length ? <p className="mt-2 text-xs leading-5 opacity-75">Signals: {item.evidence.join(", ")}</p> : null}
        </div>
      ))}
    </div>
  );
}

export default function InsightStudioPage() {
  const store = useProposalStore();
  const parsedRfp = useProposalStore((state) => state.parsedRfp);
  const [mode, setMode] = useState<"agent" | "web">("agent");
  const [focus, setFocus] = useState<string[]>(["Scope", "Leakage", "Mandays", "Hardware"]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<InsightResponse | null>(null);
  const [error, setError] = useState("");

  const totalMandays = useMemo(() => {
    if (!result) return "";
    const low = result.manday_estimates.reduce((sum, item) => sum + item.low, 0);
    const high = result.manday_estimates.reduce((sum, item) => sum + item.high, 0);
    return `${low}-${high}`;
  }, [result]);

  async function run() {
    setLoading(true);
    setError("");
    try {
      const res = await api.analyzeInsights({
        context: store.context,
        parsed_rfp: parsedRfp,
        mode,
        focus_areas: focus,
        model: store.model,
      });
      setResult(res);
    } catch (e: any) {
      setError(e.message || "Insight analysis failed.");
    } finally {
      setLoading(false);
    }
  }

  function toggleFocus(item: string) {
    setFocus((current) =>
      current.includes(item) ? current.filter((value) => value !== item) : [...current, item]
    );
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
        <section className="space-y-4">
          <Card>
            <CardContent className="space-y-4 pt-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
                  <BrainCircuit className="h-5 w-5" />
                </div>
                <div>
                  <h1 className="text-lg font-bold">Insight Studio</h1>
                  <p className="text-xs text-muted-foreground">Cross-check scope, evidence, roles, hardware, and delivery effort.</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <Button type="button" variant={mode === "agent" ? "default" : "outline"} onClick={() => setMode("agent")}>
                  <BrainCircuit className="h-4 w-4" />
                  Agent Mode
                </Button>
                <Button type="button" variant={mode === "web" ? "default" : "outline"} onClick={() => setMode("web")}>
                  <FileSearch className="h-4 w-4" />
                  Web Mode
                </Button>
              </div>

              <div className="grid grid-cols-2 gap-2">
                {FOCUS.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => toggleFocus(item)}
                    className={cn(
                      "rounded-md border px-3 py-2 text-xs transition",
                      focus.includes(item)
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-card text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {item}
                  </button>
                ))}
              </div>

              <Button onClick={run} disabled={loading} className="w-full">
                {loading ? "Analyzing..." : "Run Insight Analysis"}
                <Gauge className="h-4 w-4" />
              </Button>
              {error ? <p className="text-sm text-destructive">{error}</p> : null}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-semibold">Inputs</h2>
                <Badge tone={parsedRfp ? "accent" : "muted"}>{parsedRfp ? "RFP mapped" : "No RFP"}</Badge>
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                {store.context.client_name || "No client"} | {store.context.client_profile} | {store.context.canonical_product || "Temenos"}
              </p>
              <p className="text-xs leading-5 text-muted-foreground">
                {(store.context.intake.phase_1_products || []).slice(0, 6).join(", ") || "Phase 1 scope not selected"}
              </p>
            </CardContent>
          </Card>
        </section>

        <section className="space-y-4">
          <Card>
            <CardContent className="space-y-4 pt-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="font-semibold">Executive Intelligence</h2>
                  <p className="text-xs text-muted-foreground">{result?.summary || "Run analysis to generate proposal-specific intelligence."}</p>
                </div>
                <div className="flex gap-2">
                  <Badge tone="muted">{result ? `${result.module_hardware.length} modules` : "modules"}</Badge>
                  <Badge tone="accent">{totalMandays || "mandays"}</Badge>
                </div>
              </div>
              {result ? (
                <div className="grid gap-2 md:grid-cols-2">
                  {result.next_best_actions.map((item) => (
                    <div key={item} className="flex gap-2 rounded-md border border-border bg-muted/20 p-3 text-sm">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardContent className="space-y-3 pt-5">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4" />
                  <h2 className="font-semibold">Leakage Watch</h2>
                </div>
                <ItemList items={result?.leakage_warnings || []} empty="No leakage warnings yet." />
              </CardContent>
            </Card>
            <Card>
              <CardContent className="space-y-3 pt-5">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" />
                  <h2 className="font-semibold">Scope Gaps</h2>
                </div>
                <ItemList items={result?.scope_gaps || []} empty="No scope gaps yet." />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center gap-2">
                <Cpu className="h-4 w-4" />
                <h2 className="font-semibold">Module Hardware Classifier</h2>
              </div>
              {result?.module_hardware.length ? (
                <div className="grid gap-2 md:grid-cols-2">
                  {result.module_hardware.slice(0, 12).map((item) => (
                    <div key={item.module} className="rounded-md border border-border bg-card p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="truncate text-sm font-medium">{item.module}</div>
                        <Badge tone={item.complexity === "high" ? "accent" : "muted"}>{item.hardware_band}</Badge>
                      </div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">{item.signals.join(", ")}</p>
                      <p className="mt-2 text-xs leading-5">{item.recommendation}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Module classification will appear here.</p>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardContent className="space-y-3 pt-5">
                <div className="flex items-center gap-2">
                  <Gauge className="h-4 w-4" />
                  <h2 className="font-semibold">Manday Ranges</h2>
                </div>
                {result?.manday_estimates.length ? result.manday_estimates.map((item) => (
                  <div key={item.workstream} className="rounded-md border border-border bg-muted/20 p-3">
                    <div className="flex items-center justify-between gap-3 text-sm">
                      <span className="font-medium">{item.workstream}</span>
                      <span>{item.low}-{item.high} MD</span>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">{item.rationale}</p>
                  </div>
                )) : <p className="text-sm text-muted-foreground">Manday ranges will appear here.</p>}
              </CardContent>
            </Card>
            <Card>
              <CardContent className="space-y-3 pt-5">
                <div className="flex items-center gap-2">
                  <Users2 className="h-4 w-4" />
                  <h2 className="font-semibold">Roles and Checkpoints</h2>
                </div>
                {result?.role_assignments.length ? result.role_assignments.map((item) => (
                  <div key={item.role} className="rounded-md border border-border bg-muted/20 p-3">
                    <div className="text-sm font-medium">{item.role}</div>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">Owns: {item.owns.join(", ")}</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">Checkpoints: {item.checkpoints.join(", ")}</p>
                  </div>
                )) : <p className="text-sm text-muted-foreground">Role ownership will appear here.</p>}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center gap-2">
                <Network className="h-4 w-4" />
                <h2 className="font-semibold">Proposal Targets</h2>
              </div>
              {result?.proposal_targets.length ? result.proposal_targets.map((item) => (
                <p key={item} className="text-sm leading-6">{item}</p>
              )) : <p className="text-sm text-muted-foreground">Proposal targets will appear here.</p>}
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}
