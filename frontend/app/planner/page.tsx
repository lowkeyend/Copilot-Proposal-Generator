"use client";

import { useMemo, useState } from "react";
import { CalendarCheck2, TriangleAlert, ListTodo, FileText, Sparkles, Users2, Gauge } from "lucide-react";
import { api } from "@/lib/api";
import { useProposalStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/input";

export default function PlannerPage() {
  const store = useProposalStore();
  const parsedRfp = useProposalStore((state) => state.parsedRfp);
  const [loading, setLoading] = useState(false);
  const [sourceMode, setSourceMode] = useState<"intake" | "rfp" | "both">("both");
  const [nextSteps, setNextSteps] = useState<string[]>([]);
  const [risks, setRisks] = useState<string[]>([]);
  const [verifications, setVerifications] = useState<string[]>([]);
  const [milestones, setMilestones] = useState<string[]>([]);
  const [openQuestions, setOpenQuestions] = useState<string[]>([]);
  const [timelineNotes, setTimelineNotes] = useState<string[]>([]);
  const [decisionGates, setDecisionGates] = useState<string[]>([]);
  const [mandays, setMandays] = useState<{ workstream: string; low: number; high: number; rationale: string }[]>([]);
  const [roles, setRoles] = useState<{ role: string; owns: string[]; checkpoints: string[] }[]>([]);
  const [error, setError] = useState("");

  const sourceLabel = useMemo(() => {
    if (sourceMode === "rfp") return "Parsed RFP only";
    if (sourceMode === "intake") return "Current intake only";
    return "Parsed RFP + current intake";
  }, [sourceMode]);

  async function run() {
    setLoading(true);
    setError("");
    try {
      const res = await api.planNextSteps({
        context: store.context,
        parsed_rfp: sourceMode === "intake" ? null : parsedRfp,
        model: store.model,
      });
      setNextSteps(res.next_steps);
      setRisks(res.risks);
      setVerifications(res.verifications);
      setMilestones(res.milestones);
      setOpenQuestions(res.open_questions);
      setTimelineNotes(res.timeline_notes);
      setDecisionGates(res.decision_gates || []);
      setMandays(res.manday_estimates || []);
      setRoles(res.role_assignments || []);
    } catch (e: any) {
      setError(e.message || "Planner failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto grid max-w-7xl gap-6 px-4 py-6 lg:grid-cols-[0.95fr_1.05fr]">
      <Card>
        <CardContent className="space-y-4 pt-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <CalendarCheck2 className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-lg font-bold">Planner Agent</h1>
              <p className="text-xs text-muted-foreground">
                Plan next steps from the extracted RFP and intake, not from a generic migration lens.
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <Label>Generate from</Label>
            <Select value={sourceMode} onChange={(e) => setSourceMode(e.target.value as typeof sourceMode)}>
              <option value="both">Parsed RFP + current intake</option>
              <option value="rfp">Parsed RFP only</option>
              <option value="intake">Current intake only</option>
            </Select>
          </div>

          <Button onClick={run} disabled={loading}>
            {loading ? "Planning..." : "Generate next steps"}
          </Button>
          <Button variant="outline" onClick={() => window.location.assign("/timeline")}>
            <Sparkles className="h-4 w-4" />
            Open Timeline Builder
          </Button>

          {error ? <p className="text-sm text-destructive">{error}</p> : null}

          <div className="rounded-2xl border border-border bg-muted/20 p-4 text-sm">
            <div className="font-medium">Source selected</div>
            <p className="mt-1 text-muted-foreground">{sourceLabel}</p>
          </div>

          {parsedRfp ? (
            <div className="rounded-2xl border border-border bg-muted/20 p-4 text-sm">
              <div className="flex items-center gap-2 font-medium">
                <FileText className="h-4 w-4" />
                Parsed RFP ready
              </div>
              <p className="mt-1 text-muted-foreground">
                {parsedRfp.title} | {parsedRfp.fields.length} mapped fields | {parsedRfp.next_steps.length} suggested follow-ups
              </p>
            </div>
          ) : null}

          <div className="rounded-2xl border border-border bg-muted/20 p-4 text-sm">
            <div className="font-medium">Scope lens</div>
            <p className="mt-1 text-muted-foreground">Project mode: {store.context.intake.project_mode}</p>
            {store.context.intake.project_mode === "upgrade" ? (
              <p className="mt-1 text-muted-foreground">Upgrade type: {store.context.intake.upgrade_type}</p>
            ) : null}
            <p className="mt-1 text-muted-foreground">
              Reference docs: {store.context.selected_documents.length ? store.context.selected_documents.join(", ") : "All KB documents"}
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4">
        <Card>
          <CardContent className="space-y-3 pt-5">
            <div className="flex items-center gap-2">
              <ListTodo className="h-4 w-4" />
              <h2 className="font-semibold">Next Steps</h2>
            </div>
            {nextSteps.length ? nextSteps.map((item) => <p key={item} className="text-sm leading-6">{item}</p>) : <p className="text-sm text-muted-foreground">Generated actions will appear here.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-3 pt-5">
            <div className="flex items-center gap-2">
              <TriangleAlert className="h-4 w-4" />
              <h2 className="font-semibold">Risks</h2>
            </div>
            {risks.length ? risks.map((item) => <p key={item} className="text-sm leading-6">{item}</p>) : <p className="text-sm text-muted-foreground">Risk notes will appear here.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-3 pt-5">
            <h2 className="font-semibold">Milestones</h2>
            {milestones.length ? milestones.map((item) => <p key={item} className="text-sm leading-6">{item}</p>) : <p className="text-sm text-muted-foreground">Milestones will appear here.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-3 pt-5">
            <div className="flex items-center gap-2">
              <Gauge className="h-4 w-4" />
              <h2 className="font-semibold">Manday Forecast</h2>
            </div>
            {mandays.length ? (
              <div className="grid gap-2 md:grid-cols-2">
                {mandays.map((item) => (
                  <div key={item.workstream} className="rounded-md border border-border bg-muted/20 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm font-medium">{item.workstream}</div>
                      <div className="text-xs font-semibold">{item.low}-{item.high} MD</div>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">{item.rationale}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Manday forecast will appear here.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-3 pt-5">
            <div className="flex items-center gap-2">
              <Users2 className="h-4 w-4" />
              <h2 className="font-semibold">Role Ownership</h2>
            </div>
            {roles.length ? roles.map((item) => (
              <div key={item.role} className="rounded-md border border-border bg-card p-3">
                <div className="text-sm font-medium">{item.role}</div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">Owns: {item.owns.join(", ")}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">Checkpoints: {item.checkpoints.join(", ")}</p>
              </div>
            )) : <p className="text-sm text-muted-foreground">Role mapping will appear here.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-3 pt-5">
            <h2 className="font-semibold">Decision Gates</h2>
            {decisionGates.length ? decisionGates.map((item) => <p key={item} className="text-sm leading-6">{item}</p>) : <p className="text-sm text-muted-foreground">Decision gates will appear here.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-3 pt-5">
            <h2 className="font-semibold">Open Questions</h2>
            {openQuestions.length ? openQuestions.map((item) => <p key={item} className="text-sm leading-6">{item}</p>) : <p className="text-sm text-muted-foreground">Open questions will appear here.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-3 pt-5">
            <h2 className="font-semibold">Timeline Notes</h2>
            {timelineNotes.length ? timelineNotes.map((item) => <p key={item} className="text-sm leading-6">{item}</p>) : <p className="text-sm text-muted-foreground">Timeline notes will appear here.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-3 pt-5">
            <h2 className="font-semibold">Verification Checklist</h2>
            {verifications.length ? verifications.map((item) => <p key={item} className="text-sm leading-6">{item}</p>) : <p className="text-sm text-muted-foreground">Verification items will appear here.</p>}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
