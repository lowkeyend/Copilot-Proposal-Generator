"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  ClipboardCopy,
  FileSearch,
  GitBranch,
  GripVertical,
  Layers3,
  ShieldCheck,
  TimerReset,
  Workflow,
} from "lucide-react";
import { useProposalStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type Step = {
  id: string;
  title: string;
  owner: string;
  output: string;
  route: string;
  source: "library" | "active";
};

const LIBRARY: Step[] = [
  { id: "rfp-parser", title: "Parse RFP", owner: "Bid Analyst", output: "Extract requirement facts, gaps, storyline, and intake fields", route: "/rfp-parser", source: "library" },
  { id: "query-docs", title: "Query KB", owner: "Solution Lead", output: "Answer clarifications from uploaded evidence only", route: "/docs-query", source: "library" },
  { id: "insight-studio", title: "Run Insight Studio", owner: "Proposal Lead", output: "Find scope leakage, contradictions, module gaps, manday drivers, and risks", route: "/insight-studio", source: "library" },
  { id: "planner", title: "Generate Plan", owner: "PMO", output: "Produce next actions, decision gates, verifications, owners, and timelines", route: "/planner", source: "library" },
  { id: "timeline", title: "Build Timeline", owner: "Delivery Manager", output: "Sequence modules, workstreams, milestones, and dependencies", route: "/timeline", source: "library" },
  { id: "workspace", title: "Generate Sections", owner: "Proposal Writer", output: "Draft proposal sections using mapped RFP facts and retrieved evidence", route: "/workspace", source: "library" },
  { id: "review", title: "Consistency Review", owner: "Quality Lead", output: "Check client names, product naming, phase coherence, and unsupported claims", route: "/workspace", source: "library" },
  { id: "export", title: "Export DOCX", owner: "Proposal Lead", output: "Produce submission-ready proposal package and final checklist", route: "/workspace", source: "library" },
];

const LANES = [
  { id: "intake", title: "Intake" },
  { id: "analysis", title: "Analysis" },
  { id: "drafting", title: "Drafting" },
  { id: "submission", title: "Submission" },
];

type LaneMap = Record<string, Step[]>;

function cloneStep(step: Step): Step {
  return { ...step, id: `${step.id}-${Math.random().toString(16).slice(2, 7)}`, source: "active" };
}

export default function WorkflowMakerPage() {
  const store = useProposalStore();
  const parsedRfp = useProposalStore((state) => state.parsedRfp);
  const [dragStep, setDragStep] = useState<Step | null>(null);
  const [lanes, setLanes] = useState<LaneMap>({
    intake: [cloneStep(LIBRARY[0])],
    analysis: [cloneStep(LIBRARY[2]), cloneStep(LIBRARY[3])],
    drafting: [cloneStep(LIBRARY[5])],
    submission: [cloneStep(LIBRARY[6]), cloneStep(LIBRARY[7])],
  });

  const mappedFields = parsedRfp?.fields.filter((field) => field.value) || [];
  const missingFields = parsedRfp?.fields.filter((field) => !field.value).slice(0, 12) || [];
  const readinessScore = parsedRfp?.fields.length
    ? Math.round((mappedFields.length / parsedRfp.fields.length) * 100)
    : 0;
  const categorySummary = useMemo(() => {
    const counts = mappedFields.reduce<Record<string, number>>((acc, field) => {
      const key = field.category || "Other";
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([category, count]) => `${category}: ${count}`)
      .join(" | ");
  }, [mappedFields]);

  const workflowText = useMemo(() => {
    const lines = LANES.flatMap((lane) =>
      (lanes[lane.id] || []).map(
        (step, index) => `${lane.title}.${index + 1} ${step.title} | Owner: ${step.owner} | Output: ${step.output}`
      )
    );
    const gates = [
      "Gate 1 - RFP facts mapped: client, scope, project mode, products/modules, integrations, infrastructure, dates, and assumptions are explicit.",
      "Gate 2 - Evidence lock: every proposal section has retrieved support and no cross-client leakage.",
      "Gate 3 - Delivery coherence: methodology, phases, timeline, testing, migration, and governance agree with each other.",
      "Gate 4 - Submission readiness: consistency review is clean, open questions are either answered or listed as assumptions.",
    ];
    const promptBlock = [
      "Reusable generation prompt:",
      `Generate a proposal for ${store.context.client_name || parsedRfp?.title || "the client"} using this workflow.`,
      "Use parsed RFP facts and retrieved evidence only.",
      "Preserve phase boundaries, product names, module names, interfaces, infrastructure, and client terminology.",
      "If a field is missing, state it as a clarification or assumption. Do not invent scope.",
    ];
    return [
      `Proposal Workflow Brief for ${store.context.client_name || parsedRfp?.title || "current proposal"}`,
      `Parsed RFP: ${parsedRfp ? parsedRfp.title : "not mapped"}`,
      `Readiness: ${readinessScore || 0}% mapped`,
      `Mapped categories: ${categorySummary || "none"}`,
      `Current prompt length: ${store.prompt?.length || 0} characters`,
      `TOC sections: ${store.toc.length}`,
      "",
      "Inputs used:",
      `- RFP Parser fields: ${mappedFields.length}`,
      `- Start tab client/context: ${store.context.client_name || "not set"}`,
      `- Evidence mode: ${store.quality.require_evidence ? "strict" : "flexible"}`,
      `- Workspace TOC sections: ${store.toc.length}`,
      "",
      "Execution lanes:",
      ...lines,
      "",
      "Quality gates:",
      ...gates.map((gate) => `- ${gate}`),
      "",
      "Clarification focus:",
      ...(missingFields.length
        ? missingFields.map((field) => `- ${field.label}`)
        : ["- No missing fields currently flagged. Re-check assumptions before final submission."]),
      "",
      "Output to use next:",
      ...promptBlock.slice(1),
    ].join("\n");
  }, [categorySummary, lanes, mappedFields.length, missingFields, parsedRfp, readinessScore, store.context.client_name, store.prompt?.length, store.quality.require_evidence, store.toc.length]);

  function dropIntoLane(laneId: string) {
    if (!dragStep) return;
    setLanes((current) => {
      const next = { ...current };
      for (const id of Object.keys(next)) {
        next[id] = next[id].filter((step) => step.id !== dragStep.id);
      }
      next[laneId] = [...(next[laneId] || []), dragStep.source === "library" ? cloneStep(dragStep) : dragStep];
      return next;
    });
    setDragStep(null);
  }

  function removeStep(stepId: string) {
    setLanes((current) => {
      const next = { ...current };
      for (const id of Object.keys(next)) {
        next[id] = next[id].filter((step) => step.id !== stepId);
      }
      return next;
    });
  }

  function copyWorkflow() {
    store.setPrompt(workflowText);
    navigator.clipboard?.writeText(workflowText).catch(() => undefined);
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <GitBranch className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold">Workflow Maker</h1>
            <p className="text-xs text-muted-foreground">Compose a proposal workflow from the app agents, evidence checks, and delivery controls.</p>
          </div>
        </div>
        <Button variant="outline" onClick={copyWorkflow}>
          <ClipboardCopy className="h-4 w-4" />
          Copy workflow to prompt
        </Button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
        <aside className="space-y-4">
          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center gap-2">
                <Workflow className="h-4 w-4" />
                <h2 className="text-sm font-semibold">How to run it</h2>
              </div>
              <div className="space-y-2 text-xs leading-5 text-muted-foreground">
                <p>1. Parse the RFP so facts are loaded.</p>
                <p>2. Drag steps into lanes or keep the default sequence.</p>
                <p>3. Click Open tool on each active card and run that tab.</p>
                <p>4. Copy the execution brief into Workspace or your prompt.</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center gap-2">
                <FileSearch className="h-4 w-4" />
                <h2 className="text-sm font-semibold">Data sources</h2>
              </div>
              <div className="space-y-2 text-xs leading-5 text-muted-foreground">
                <p>Parsed RFP: {parsedRfp?.title || "not loaded"}</p>
                <p>Mapped fields: {mappedFields.length}</p>
                <p>Client context: {store.context.client_name || "not set"}</p>
                <p>TOC sections: {store.toc.length}</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3 pt-5">
            <div className="flex items-center gap-2">
              <Layers3 className="h-4 w-4" />
              <h2 className="text-sm font-semibold">Step Library</h2>
            </div>
            <p className="text-xs leading-5 text-muted-foreground">
              Drag a step into a lane. Active steps link to the tab that performs the work.
            </p>
            <div className="space-y-2">
              {LIBRARY.map((step) => (
                <button
                  key={step.id}
                  type="button"
                  draggable
                  onDragStart={() => setDragStep(step)}
                  className="flex w-full items-start gap-2 rounded-md border border-border bg-card p-3 text-left text-sm transition hover:bg-muted"
                >
                  <GripVertical className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  <span>
                    <span className="block font-medium">{step.title}</span>
                    <span className="mt-1 block text-xs leading-5 text-muted-foreground">{step.output}</span>
                    <span className="mt-1 block text-[11px] text-muted-foreground">Runs in {step.route}</span>
                  </span>
                </button>
              ))}
            </div>
            </CardContent>
          </Card>
        </aside>

        <section className="space-y-4">
          <div className="grid gap-3 md:grid-cols-4">
            <div className="rounded-md border border-border bg-card p-3 text-sm">
              <FileSearch className="mb-2 h-4 w-4" />
              RFP facts: {mappedFields.length}/{parsedRfp?.fields.length || 0}
            </div>
            <div className="rounded-md border border-border bg-card p-3 text-sm">
              <ShieldCheck className="mb-2 h-4 w-4" />
              Evidence mode: {store.quality.require_evidence ? "strict" : "flexible"}
            </div>
            <div className="rounded-md border border-border bg-card p-3 text-sm">
              <TimerReset className="mb-2 h-4 w-4" />
              Delivery: {store.context.intake.delivery_model}
            </div>
            <div className="rounded-md border border-border bg-card p-3 text-sm">
              <CheckCircle2 className="mb-2 h-4 w-4" />
              Readiness: {readinessScore || 0}%
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
            <div className="rounded-md border border-border bg-card p-4">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Workflow className="h-4 w-4" />
                Operating model
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Move from RFP facts to evidence validation, then planning, drafting, consistency review, and final package export.
                The copied brief includes gates and clarification focus so proposal generation does not drift.
              </p>
            </div>
            <div className="rounded-md border border-border bg-card p-4">
              <div className="text-sm font-semibold">Clarification focus</div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {missingFields.length
                  ? missingFields.map((field) => field.label).join(", ")
                  : "No parser gaps loaded. Parse an RFP to activate this."}
              </p>
            </div>
          </div>

          <div className="grid gap-3 xl:grid-cols-4">
            {LANES.map((lane) => (
              <div
                key={lane.id}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => dropIntoLane(lane.id)}
                className="min-h-[420px] rounded-md border border-border bg-muted/20 p-3"
              >
                <div className="mb-3 flex items-center justify-between gap-2">
                  <h2 className="text-sm font-semibold">{lane.title}</h2>
                  <Badge tone="muted">{lanes[lane.id]?.length || 0}</Badge>
                </div>
                <div className="space-y-2">
                  {(lanes[lane.id] || []).map((step) => (
                    <div
                      key={step.id}
                      draggable
                      onDragStart={() => setDragStep(step)}
                      className={cn("rounded-md border border-border bg-card p-3 text-sm shadow-sm")}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="font-medium">{step.title}</div>
                          <p className="mt-1 text-xs leading-5 text-muted-foreground">{step.output}</p>
                          <p className="mt-2 text-xs">Owner: {step.owner}</p>
                          <Link
                            href={step.route}
                            className="mt-2 inline-flex rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                          >
                            Open tool
                          </Link>
                        </div>
                        <button
                          type="button"
                          onClick={() => removeStep(step.id)}
                          className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-semibold">Workflow Execution Brief</h2>
                <Button variant="outline" size="sm" onClick={copyWorkflow}>
                  <ClipboardCopy className="h-4 w-4" />
                  Copy
                </Button>
              </div>
              <pre className="max-h-72 overflow-auto rounded-md border border-border bg-muted/20 p-3 text-xs leading-5 whitespace-pre-wrap">
                {workflowText}
              </pre>
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}
