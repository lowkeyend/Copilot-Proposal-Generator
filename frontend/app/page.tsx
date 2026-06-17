"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Sparkles, FileText, ArrowRight, Wand2, Database, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { useProposalStore } from "@/lib/store";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Textarea, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { KbStatus } from "@/components/KbStatus";

const EXAMPLES = [
  "Generate a proposal for XYZ Bank for Temenos implementation. Emphasize migration and security. Formal tone.",
  "Cloud migration proposal for Northwind Insurance moving on-prem workloads to Azure. Highlight cost savings and zero-downtime cutover.",
  "Managed cybersecurity services proposal for a mid-size healthcare provider. Emphasize 24/7 SOC and HIPAA compliance.",
];

export default function SetupPage() {
  const router = useRouter();
  const store = useProposalStore();
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .models()
      .then((m) => {
        setModels(m.models);
        if (!m.models.includes(store.model)) store.setModel(m.default);
      })
      .catch(() => setModels(["deepseek/deepseek-chat", "qwen/qwen3-32b"]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleGenerate() {
    if (!store.prompt.trim()) {
      setError("Please describe the proposal you want to generate.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      setStage("Understanding request & detecting proposal type…");
      const ctx = await api.generateContext({
        prompt: store.prompt,
        model: store.model,
        client_name: store.context.client_name || undefined,
        industry: store.context.industry || undefined,
        project_type: store.context.project_type || undefined,
      });
      store.setContext(ctx.context);
      store.setProposalFamily(ctx.proposal_family);
      store.setFamilyRationale(ctx.family_rationale);

      setStage("Suggesting a proposal pattern from your corpus…");
      const tpl = await api.suggestTemplate({
        prompt: store.prompt,
        context: ctx.context,
        proposal_family: ctx.proposal_family,
        model: store.model,
      });
      store.setTemplate(tpl.suggested);

      setStage("Building an editable table of contents…");
      const toc = await api.buildToc({
        prompt: store.prompt,
        context: ctx.context,
        proposal_family: ctx.proposal_family,
        template: tpl.suggested,
        model: store.model,
      });
      store.setToc(toc.toc);
      store.resetWorkspace();
      store.setToc(toc.toc);

      router.push("/workspace");
    } catch (e: any) {
      setError(e.message || "Something went wrong.");
    } finally {
      setLoading(false);
      setStage("");
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <FileText className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Proposal Copilot</h1>
            <p className="text-sm text-muted-foreground">
              From knowledge base to client-ready proposal.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => router.push("/knowledge-base")}>
            <Database className="h-4 w-4" />
            Knowledge Base
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push("/knowledge-base?view=upload")}
          >
            <Upload className="h-4 w-4" />
            Add Docs
          </Button>
          <KbStatus />
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <Card>
          <CardContent className="space-y-5 pt-6">
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label>Client Name</Label>
                <Input
                  placeholder="XYZ Bank"
                  value={store.context.client_name}
                  onChange={(e) =>
                    store.setContext({ client_name: e.target.value })
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label>Industry</Label>
                <Input
                  placeholder="Banking"
                  value={store.context.industry}
                  onChange={(e) =>
                    store.setContext({ industry: e.target.value })
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label>Project Type</Label>
                <Input
                  placeholder="Temenos implementation"
                  value={store.context.project_type}
                  onChange={(e) =>
                    store.setContext({ project_type: e.target.value })
                  }
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Prompt</Label>
              <Textarea
                rows={4}
                placeholder="Describe the proposal in plain English…"
                value={store.prompt}
                onChange={(e) => store.setPrompt(e.target.value)}
              />
              <div className="flex flex-wrap gap-2 pt-1">
                {EXAMPLES.map((ex, i) => (
                  <button
                    key={i}
                    onClick={() => store.setPrompt(ex)}
                    className="rounded-full border border-border bg-muted px-2.5 py-1 text-[11px] text-muted-foreground hover:bg-border"
                  >
                    <Wand2 className="mr-1 inline h-3 w-3" />
                    Example {i + 1}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Model</Label>
                <Select
                  value={store.model}
                  onChange={(e) => store.setModel(e.target.value)}
                >
                  {models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Tone</Label>
                <Select
                  value={store.context.tone}
                  onChange={(e) => store.setContext({ tone: e.target.value })}
                >
                  {["Formal", "Confident", "Consultative", "Concise", "Persuasive"].map(
                    (t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    )
                  )}
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Special Instructions</Label>
              <Textarea
                rows={2}
                placeholder="Emphasize migration and security. Keep executive summary under one page."
                value={store.context.special_instructions}
                onChange={(e) =>
                  store.setContext({ special_instructions: e.target.value })
                }
              />
            </div>

            {error && (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            )}

            <div className="flex items-center justify-between pt-1">
              <a
                href="/templates"
                className="text-sm text-muted-foreground underline-offset-4 hover:underline"
              >
                Manage discovered templates →
              </a>
              <Button onClick={handleGenerate} disabled={loading}>
                {loading ? <Spinner /> : <Sparkles className="h-4 w-4" />}
                {loading ? "Working…" : "Generate Proposal"}
                {!loading && <ArrowRight className="h-4 w-4" />}
              </Button>
            </div>
            {loading && stage && (
              <p className="text-xs text-muted-foreground">{stage}</p>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </main>
  );
}
