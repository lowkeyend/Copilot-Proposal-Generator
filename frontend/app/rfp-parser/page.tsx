"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, ClipboardCopy, ClipboardList, FileUp, Layers3, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import type { ParsedField, RfpParseResponse } from "@/lib/types";
import { useProposalStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { cn } from "@/lib/utils";

function FieldCard({ field }: { field: ParsedField }) {
  const missing = !field.value;
  return (
    <div className={cn("rounded-2xl border p-3", missing ? "border-amber-200 bg-amber-50/60" : "border-border bg-background/70")}>
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium">{field.label}</div>
        <div className={cn("text-xs", missing ? "text-amber-700" : "text-muted-foreground")}>
          {field.category} | {Math.round(field.confidence * 100)}%
        </div>
      </div>
      <div className={cn("mt-2 text-sm leading-6", missing ? "text-amber-900" : "text-foreground")}>
        {field.value || "Needs clarification"}
      </div>
      {field.source_excerpt ? (
        <details className="mt-2 text-xs text-muted-foreground">
          <summary className="cursor-pointer">Source hint</summary>
          <p className="mt-1 leading-5">{field.source_excerpt}</p>
        </details>
      ) : null}
    </div>
  );
}

function buildRfpContext(result: RfpParseResponse) {
  const filled = result.fields.filter((field) => field.value);
  const grouped = filled.reduce<Record<string, ParsedField[]>>((acc, field) => {
    const key = field.category || "Other";
    acc[key] = [...(acc[key] || []), field];
    return acc;
  }, {});
  const fieldLines = Object.entries(grouped).flatMap(([category, fields]) => [
    `\n[${category}]`,
    ...fields.map((field) => `- ${field.label}: ${field.value}`),
  ]);
  return [
    `Parsed RFP Context: ${result.title}`,
    `Project mode: ${result.project_mode}`,
    `Storyline: ${result.storyline || result.summary}`,
    `Missing/clarification items: ${result.missing_fields.join(", ") || "None listed"}`,
    ...fieldLines,
    "",
    "Instruction for proposal generation:",
    "Use only these mapped RFP facts plus retrieved evidence. Do not invent missing scope. Preserve phase, module, interface, version, infrastructure, testing, migration, and dependency boundaries.",
  ].join("\n");
}

export default function RfpParserPage() {
  const store = useProposalStore();
  const [files, setFiles] = useState<File[]>([]);
  const [model, setModel] = useState(store.model);
  const [result, setResult] = useState<RfpParseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeCategory, setActiveCategory] = useState("Overview");
  const [fieldMode, setFieldMode] = useState<"all" | "filled" | "missing">("filled");

  const grouped = useMemo(() => {
    const map = new Map<string, ParsedField[]>();
    for (const field of result?.fields || []) {
      const key = field.category || "Other";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(field);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [result]);

  const categories = grouped.map(([name]) => name);
  const selectedFields = grouped.find(([name]) => name === activeCategory)?.[1] || [];
  const visibleFields = selectedFields.filter((field) => {
    if (fieldMode === "filled") return Boolean(field.value);
    if (fieldMode === "missing") return !field.value;
    return true;
  });
  const filledCount = result?.fields.filter((field) => field.value).length || 0;
  const missingCount = result ? result.fields.length - filledCount : 0;

  const summary = useMemo(() => {
    if (!result) return "";
    return `${result.title} | ${result.project_mode} | ${result.fields.length} mapped fields`;
  }, [result]);

  useEffect(() => {
    if (!grouped.length) return;
    if (!grouped.some(([name]) => name === activeCategory)) {
      setActiveCategory(grouped[0][0]);
    }
  }, [grouped, activeCategory]);

  async function parse() {
    if (files.length === 0) {
      setError("Upload a PDF or DOCX first.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const parsed = await api.parseRfp(files, model);
      setResult(parsed);
      setActiveCategory("Overview");
    } catch (e: any) {
      setError(e.message || "RFP parsing failed.");
    } finally {
      setLoading(false);
    }
  }

  function applyToStore() {
    if (!result) return;
    store.setParsedRfp(result);
    store.setContext({
      client_name: store.context.client_name || result.title,
      intake: result.intake,
    } as any);
  }

  function mapToPrompt() {
    if (!result) return;
    const prompt = buildRfpContext(result);
    store.setPrompt(prompt);
    navigator.clipboard?.writeText(prompt).catch(() => undefined);
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
        <Card className="h-fit">
          <CardContent className="space-y-4 pt-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
                <ClipboardList className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-lg font-bold">RFP Parser</h1>
                <p className="text-xs text-muted-foreground">
                  Upload an RFP and extract the storyline, modules, phases, and delivery constraints.
                </p>
              </div>
            </div>

            <div className="rounded-2xl border border-border bg-muted/20 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Sparkles className="h-4 w-4" />
                Parser controls
              </div>
              <div className="mt-4 space-y-3">
                <div className="space-y-2">
                  <Label>Files</Label>
                  <Input
                    type="file"
                    accept=".pdf,.docx"
                    multiple
                    onChange={(e) => setFiles(Array.from(e.target.files || []))}
                  />
                  <p className="text-xs text-muted-foreground">
                    {files.length ? `${files.length} file(s) selected.` : "No file selected."}
                  </p>
                </div>

                <div className="space-y-2">
                  <Label>Model</Label>
                  <Input value={model} onChange={(e) => setModel(e.target.value)} />
                </div>

                {error ? <p className="text-sm text-destructive">{error}</p> : null}

                <Button className="w-full" onClick={parse} disabled={loading || files.length === 0}>
                  {loading ? "Parsing..." : "Parse RFP"}
                  <FileUp className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {result ? (
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" onClick={applyToStore}>
                    Use parsed data in proposal
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                  <Button variant="outline" onClick={mapToPrompt}>
                    Copy proposal context
                    <ClipboardCopy className="h-4 w-4" />
                  </Button>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-2xl border border-border bg-card p-3">
                    <CheckCircle2 className="mb-2 h-4 w-4 text-emerald-600" />
                    <div className="text-lg font-semibold">{filledCount}</div>
                    <div className="text-xs text-muted-foreground">Mapped facts</div>
                  </div>
                  <div className="rounded-2xl border border-border bg-card p-3">
                    <AlertTriangle className="mb-2 h-4 w-4 text-amber-600" />
                    <div className="text-lg font-semibold">{missingCount}</div>
                    <div className="text-xs text-muted-foreground">Need clarification</div>
                  </div>
                  <div className="rounded-2xl border border-border bg-card p-3">
                    <Layers3 className="mb-2 h-4 w-4 text-primary" />
                    <div className="text-lg font-semibold">{categories.length}</div>
                    <div className="text-xs text-muted-foreground">Requirement groups</div>
                  </div>
                </div>

                <div className="rounded-2xl border border-border bg-card p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-semibold">Extraction Summary</div>
                    <span className="text-xs text-muted-foreground">{result.fields.length} fields</span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    {summary || "Parsed output will appear here."}
                  </p>
                </div>

                <div className="rounded-2xl border border-border bg-card p-4">
                  <div className="text-sm font-semibold">Storyline</div>
                  <p className="mt-2 text-sm leading-6 text-foreground">
                    {result.storyline || result.summary || "A storyline will be generated from the extracted fields."}
                  </p>
                </div>

                <div className="rounded-2xl border border-border bg-card p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-semibold">Clarification focus</div>
                    <span className="text-xs text-muted-foreground">{missingCount} open</span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    {result.missing_fields.length
                      ? result.missing_fields.slice(0, 8).join(", ")
                      : missingCount
                        ? "Review amber cards before generation."
                        : "No major missing fields detected."}
                  </p>
                </div>

                <div className="rounded-2xl border border-border bg-card p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <Layers3 className="h-4 w-4" />
                    Next steps
                  </div>
                  <ul className="mt-2 space-y-2 text-sm leading-6 text-muted-foreground">
                    {result.next_steps.length ? result.next_steps.map((step) => <li key={step}>- {step}</li>) : <li>Plan steps will appear here.</li>}
                  </ul>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="space-y-4">
          {result ? (
            <Card>
              <CardContent className="space-y-4 pt-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-sm font-semibold">Mapped Fields</h2>
                    <p className="text-xs text-muted-foreground">
                      Grouped by category to avoid a long scrolling wall of text.
                    </p>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {categories.length} categories
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {categories.map((category) => (
                    <button
                      key={category}
                      type="button"
                      onClick={() => setActiveCategory(category)}
                      className={cn(
                        "rounded-full border px-3 py-1.5 text-xs transition",
                        activeCategory === category
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border bg-background text-foreground hover:bg-muted"
                      )}
                    >
                      {category}
                    </button>
                  ))}
                </div>

                <div className="flex flex-wrap gap-2">
                  {(["filled", "missing", "all"] as const).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setFieldMode(mode)}
                      className={cn(
                        "rounded-full border px-3 py-1.5 text-xs capitalize transition",
                        fieldMode === mode
                          ? "border-foreground bg-foreground text-background"
                          : "border-border bg-background text-foreground hover:bg-muted"
                      )}
                    >
                      {mode}
                    </button>
                  ))}
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  {visibleFields.map((field) => (
                    <FieldCard key={field.key} field={field} />
                  ))}
                  {visibleFields.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-border p-6 text-sm text-muted-foreground">
                      No fields match this filter in the selected category.
                    </div>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="pt-5">
                <p className="text-sm text-muted-foreground">
                  Parsed fields will appear here. Use the controls on the left to upload the RFP and extract the narrative plus structured field map.
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </main>
  );
}
