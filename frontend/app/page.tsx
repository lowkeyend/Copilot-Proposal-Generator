"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Sparkles, FileText, ArrowRight, Wand2, Database, Upload, Globe2, SlidersHorizontal } from "lucide-react";
import { api } from "@/lib/api";
import { useProposalStore } from "@/lib/store";
import type { ClientContext, IntakeProfile } from "@/lib/types";
import {
  CHANNEL_PHASE_1_OPTIONS,
  CHANNEL_PHASE_2_OPTIONS,
  CONTAINER_OPTIONS,
  DATABASE_OPTIONS,
  DATA_WAREHOUSE_OPTIONS,
  DELIVERY_MODEL_OPTIONS,
  HOSTING_OPTIONS,
  METHODOLOGY_OPTIONS,
  MIDDLEWARE_OPTIONS,
  PRODUCT_PHASE_1_OPTIONS,
  PRODUCT_PHASE_2_OPTIONS,
  REGULATORY_INTERFACE_PHASE_1_OPTIONS,
  REGULATORY_INTERFACE_PHASE_2_OPTIONS,
  SAMPLE_PROMPTS,
  SEGMENT_OPTIONS,
  REPORTING_OPTIONS,
} from "@/lib/intakeOptions";
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

const EMPTY_SETUP_CONTEXT: ClientContext = {
  client_name: "",
  industry: "",
  project_type: "",
  client_profile: "established",
  implementation_context: "",
  canonical_product: "",
  intake: {
    launch_segments: [],
    phase_1_products: [],
    phase_2_products: [],
    regulatory_interfaces_phase_1: [],
    regulatory_interfaces_phase_2: [],
    channels_phase_1: [],
    channels_phase_2: [],
    middleware_platform: "",
    reporting_platform: "",
    database_platform: "",
    hosting_model: "",
    container_platform: "",
    data_warehouse_platform: "",
    implementation_methodology: "TIM",
    delivery_model: "Phased MVP",
    target_customers_year_1: "",
    target_customers_year_2: "",
    target_customers_year_3: "",
    target_accounts_year_1: "",
    target_accounts_year_2: "",
    target_accounts_year_3: "",
    launch_plan: "",
    questionnaire_notes: "",
  } satisfies IntakeProfile,
  tone: "Formal",
  special_instructions: "",
};

export default function SetupPage() {
  const router = useRouter();
  const store = useProposalStore();
  const [prompt, setPrompt] = useState("");
  const [context, setContext] = useState({ ...EMPTY_SETUP_CONTEXT });
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");

  const updateIntake = (patch: Partial<IntakeProfile>) => {
    setContext((current) => ({
      ...current,
      intake: { ...current.intake, ...patch },
    }));
  };

  const toggleIntakeItem = (
    key:
      | "launch_segments"
      | "phase_1_products"
      | "phase_2_products"
      | "regulatory_interfaces_phase_1"
      | "regulatory_interfaces_phase_2"
      | "channels_phase_1"
      | "channels_phase_2",
    value: string
  ) => {
    setContext((current) => {
      const list = current.intake[key];
      const next = list.includes(value)
        ? list.filter((item) => item !== value)
        : [...list, value];
      return {
        ...current,
        intake: { ...current.intake, [key]: next },
      };
    });
  };

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
    if (!prompt.trim()) {
      setError("Please describe the proposal you want to generate.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      setStage("Understanding request & detecting proposal type…");
      const ctx = await api.generateContext({
        prompt,
        model: store.model,
        client_name: context.client_name || undefined,
        industry: context.industry || undefined,
        project_type: context.project_type || undefined,
        client_profile: context.client_profile || "established",
        implementation_context: context.implementation_context || undefined,
        canonical_product: context.canonical_product || undefined,
        intake: context.intake,
      });
      store.setPrompt(prompt);
      store.setContext(ctx.context);
      store.setProposalFamily(ctx.proposal_family);
      store.setFamilyRationale(ctx.family_rationale);

      setStage("Suggesting a proposal pattern from your corpus…");
      const tpl = await api.suggestTemplate({
        prompt,
        context: ctx.context,
        proposal_family: ctx.proposal_family,
        model: store.model,
      });
      store.setTemplate(tpl.suggested);

      setStage("Building an editable table of contents…");
      const toc = await api.buildToc({
        prompt,
        context: ctx.context,
        proposal_family: ctx.proposal_family,
        template: tpl.suggested,
        model: store.model,
      });
      store.setToc(toc.toc);
      store.resetWorkspace();
      store.setToc(toc.toc);

      setPrompt("");
      setContext({ ...EMPTY_SETUP_CONTEXT });
      router.push("/workspace");
    } catch (e: any) {
      setError(e.message || "Something went wrong.");
    } finally {
      setLoading(false);
      setStage("");
    }
  }

  const intake = context.intake;

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
                  placeholder="Bank Alfalah"
                  value={context.client_name}
                  onChange={(e) => setContext((current) => ({ ...current, client_name: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Industry</Label>
                <Input
                  placeholder="Banking"
                  value={context.industry}
                  onChange={(e) => setContext((current) => ({ ...current, industry: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Project Type</Label>
                <Input
                  placeholder="Temenos implementation"
                  value={context.project_type}
                  onChange={(e) => setContext((current) => ({ ...current, project_type: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label>Client Profile</Label>
                <Select
                  value={context.client_profile || "established"}
                  onChange={(e) =>
                    setContext((current) => ({
                      ...current,
                      client_profile: e.target.value as "established" | "greenfield" | "unknown",
                    }))
                  }
                >
                  <option value="established">Established / modernization</option>
                  <option value="greenfield">Greenfield / new bank</option>
                  <option value="unknown">Unknown / infer from prompt</option>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Implementation Methodology</Label>
                <Select
                  value={intake.implementation_methodology}
                  onChange={(e) => updateIntake({ implementation_methodology: e.target.value })}
                >
                  {METHODOLOGY_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Delivery Model</Label>
                <Select
                  value={intake.delivery_model}
                  onChange={(e) => updateIntake({ delivery_model: e.target.value })}
                >
                  {DELIVERY_MODEL_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </Select>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Canonical Product</Label>
                <Input
                  placeholder="Temenos Transact"
                  value={context.canonical_product}
                  onChange={(e) => setContext((current) => ({ ...current, canonical_product: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Implementation Context</Label>
                <Input
                  placeholder="Modernization / migration for an existing institution"
                  value={context.implementation_context}
                  onChange={(e) => setContext((current) => ({ ...current, implementation_context: e.target.value }))}
                />
              </div>
            </div>

            <Card className="border-border/70 bg-muted/20">
              <CardContent className="space-y-4 pt-5">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold">Launch Segments</h2>
                  <span className="text-xs text-muted-foreground">{intake.launch_segments.length} selected</span>
                </div>
                <div className="grid gap-2 sm:grid-cols-5">
                  {SEGMENT_OPTIONS.map((option) => (
                    <Button
                      key={option}
                      type="button"
                      variant={intake.launch_segments.includes(option) ? "default" : "outline"}
                      size="sm"
                      onClick={() => toggleIntakeItem("launch_segments", option)}
                    >
                      {option}
                    </Button>
                  ))}
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold">Phase 1 Products</h3>
                      <span className="text-xs text-muted-foreground">{intake.phase_1_products.length} selected</span>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {PRODUCT_PHASE_1_OPTIONS.map((option) => (
                        <Button key={option} type="button" variant={intake.phase_1_products.includes(option) ? "default" : "outline"} size="sm" onClick={() => toggleIntakeItem("phase_1_products", option)}>
                          {option}
                        </Button>
                      ))}
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold">Phase 2 Products</h3>
                      <span className="text-xs text-muted-foreground">{intake.phase_2_products.length} selected</span>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {PRODUCT_PHASE_2_OPTIONS.map((option) => (
                        <Button key={option} type="button" variant={intake.phase_2_products.includes(option) ? "default" : "outline"} size="sm" onClick={() => toggleIntakeItem("phase_2_products", option)}>
                          {option}
                        </Button>
                      ))}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-border/70 bg-muted/20">
              <CardContent className="space-y-4 pt-5">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold">Integrations, Channels, Hosting</h2>
                  <span className="text-xs text-muted-foreground">Build scope from regulatory and channel inputs</span>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold">Regulatory Interfaces - Phase 1</h3>
                      <span className="text-xs text-muted-foreground">{intake.regulatory_interfaces_phase_1.length}</span>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {REGULATORY_INTERFACE_PHASE_1_OPTIONS.map((option) => (
                        <Button key={option} type="button" variant={intake.regulatory_interfaces_phase_1.includes(option) ? "default" : "outline"} size="sm" onClick={() => toggleIntakeItem("regulatory_interfaces_phase_1", option)}>
                          {option}
                        </Button>
                      ))}
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold">Regulatory Interfaces - Phase 2</h3>
                      <span className="text-xs text-muted-foreground">{intake.regulatory_interfaces_phase_2.length}</span>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {REGULATORY_INTERFACE_PHASE_2_OPTIONS.map((option) => (
                        <Button key={option} type="button" variant={intake.regulatory_interfaces_phase_2.includes(option) ? "default" : "outline"} size="sm" onClick={() => toggleIntakeItem("regulatory_interfaces_phase_2", option)}>
                          {option}
                        </Button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold">Channels - Phase 1</h3>
                      <span className="text-xs text-muted-foreground">{intake.channels_phase_1.length}</span>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {CHANNEL_PHASE_1_OPTIONS.map((option) => (
                        <Button key={option} type="button" variant={intake.channels_phase_1.includes(option) ? "default" : "outline"} size="sm" onClick={() => toggleIntakeItem("channels_phase_1", option)}>
                          {option}
                        </Button>
                      ))}
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold">Channels - Phase 2</h3>
                      <span className="text-xs text-muted-foreground">{intake.channels_phase_2.length}</span>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {CHANNEL_PHASE_2_OPTIONS.map((option) => (
                        <Button key={option} type="button" variant={intake.channels_phase_2.includes(option) ? "default" : "outline"} size="sm" onClick={() => toggleIntakeItem("channels_phase_2", option)}>
                          {option}
                        </Button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <div className="space-y-1.5">
                    <Label>Middleware</Label>
                    <Select value={intake.middleware_platform} onChange={(e) => updateIntake({ middleware_platform: e.target.value })}>
                      <option value="">Select middleware</option>
                      {MIDDLEWARE_OPTIONS.map((option) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Reporting</Label>
                    <Select value={intake.reporting_platform} onChange={(e) => updateIntake({ reporting_platform: e.target.value })}>
                      <option value="">Select reporting</option>
                      {REPORTING_OPTIONS.map((option) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Database</Label>
                    <Select value={intake.database_platform} onChange={(e) => updateIntake({ database_platform: e.target.value })}>
                      <option value="">Select database</option>
                      {DATABASE_OPTIONS.map((option) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Hosting</Label>
                    <Select value={intake.hosting_model} onChange={(e) => updateIntake({ hosting_model: e.target.value })}>
                      <option value="">Select hosting</option>
                      {HOSTING_OPTIONS.map((option) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </Select>
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label>Container Platform</Label>
                    <Select value={intake.container_platform} onChange={(e) => updateIntake({ container_platform: e.target.value })}>
                      <option value="">Select container platform</option>
                      {CONTAINER_OPTIONS.map((option) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Data Warehouse</Label>
                    <Select value={intake.data_warehouse_platform} onChange={(e) => updateIntake({ data_warehouse_platform: e.target.value })}>
                      <option value="">Select warehouse</option>
                      {DATA_WAREHOUSE_OPTIONS.map((option) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </Select>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-border/70 bg-muted/20">
              <CardContent className="space-y-4 pt-5">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold">Volumes & Launch Plan</h2>
                  <span className="text-xs text-muted-foreground">Input the target ramp and go-live path</span>
                </div>
                <div className="grid gap-4 sm:grid-cols-3">
                  <div className="space-y-1.5">
                    <Label>Year 1 Customers</Label>
                    <Input value={intake.target_customers_year_1} onChange={(e) => updateIntake({ target_customers_year_1: e.target.value })} placeholder="15,000" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Year 2 Customers</Label>
                    <Input value={intake.target_customers_year_2} onChange={(e) => updateIntake({ target_customers_year_2: e.target.value })} placeholder="50,000" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Year 3 Customers</Label>
                    <Input value={intake.target_customers_year_3} onChange={(e) => updateIntake({ target_customers_year_3: e.target.value })} placeholder="120,000" />
                  </div>
                </div>
                <div className="grid gap-4 sm:grid-cols-3">
                  <div className="space-y-1.5">
                    <Label>Year 1 Accounts</Label>
                    <Input value={intake.target_accounts_year_1} onChange={(e) => updateIntake({ target_accounts_year_1: e.target.value })} placeholder="20,000" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Year 2 Accounts</Label>
                    <Input value={intake.target_accounts_year_2} onChange={(e) => updateIntake({ target_accounts_year_2: e.target.value })} placeholder="65,000" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Year 3 Accounts</Label>
                    <Input value={intake.target_accounts_year_3} onChange={(e) => updateIntake({ target_accounts_year_3: e.target.value })} placeholder="150,000" />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label>Launch Plan / Milestones</Label>
                  <Textarea
                    rows={3}
                    placeholder="Phase 1: regulatory go-live. Phase 2: digital channels. Phase 3: expansion."
                    value={intake.launch_plan}
                    onChange={(e) => updateIntake({ launch_plan: e.target.value })}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Questionnaire Notes</Label>
                  <Textarea
                    rows={3}
                    placeholder="Any assumptions, exclusions, country-specific dependencies, or RFP clarifications."
                    value={intake.questionnaire_notes}
                    onChange={(e) => updateIntake({ questionnaire_notes: e.target.value })}
                  />
                </div>
              </CardContent>
            </Card>

            <div className="space-y-1.5">
              <Label>Prompt</Label>
              <Textarea
                rows={4}
                placeholder="Describe the proposal in plain English…"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />
              <div className="flex flex-wrap gap-2 pt-1">
                {SAMPLE_PROMPTS.map((ex, i) => (
                  <button
                    key={i}
                    onClick={() => setPrompt(ex)}
                    className="rounded-full border border-border bg-muted px-2.5 py-1 text-[11px] text-muted-foreground hover:bg-border"
                  >
                    <Wand2 className="mr-1 inline h-3 w-3" />
                    Sample {i + 1}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Model</Label>
                <Select value={store.model} onChange={(e) => store.setModel(e.target.value)}>
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
                  value={context.tone}
                  onChange={(e) => setContext((current) => ({ ...current, tone: e.target.value }))}
                >
                  {["Formal", "Confident", "Consultative", "Concise", "Persuasive"].map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Special Instructions</Label>
              <Textarea
                rows={2}
                placeholder="Emphasize migration and security. Keep executive summary under one page."
                value={context.special_instructions}
                onChange={(e) =>
                  setContext((current) => ({
                    ...current,
                    special_instructions: e.target.value,
                  }))
                }
              />
            </div>

            <div className="rounded-md border border-border bg-muted/30 p-3">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 className="flex items-center gap-2 text-sm font-semibold">
                  <SlidersHorizontal className="h-4 w-4" />
                  Proposal Quality
                </h2>
                <span className="text-xs text-muted-foreground">
                  {store.quality.detail_level}
                </span>
              </div>
              <div className="grid gap-3 sm:grid-cols-4">
                <Button
                  type="button"
                  variant={store.quality.include_temenos_official ? "default" : "outline"}
                  size="sm"
                  onClick={() =>
                    store.setQuality({
                      include_temenos_official: !store.quality.include_temenos_official,
                    })
                  }
                  title="Allow official Temenos website snippets in retrieval"
                >
                  <Globe2 className="h-4 w-4" />
                  Temenos Web
                </Button>
                <Button
                  type="button"
                  variant={store.quality.use_hybrid_retrieval ? "default" : "outline"}
                  size="sm"
                  onClick={() =>
                    store.setQuality({
                      use_hybrid_retrieval: !store.quality.use_hybrid_retrieval,
                    })
                  }
                >
                  Hybrid RAG
                </Button>
                <Button
                  type="button"
                  variant={store.quality.require_evidence ? "default" : "outline"}
                  size="sm"
                  onClick={() =>
                    store.setQuality({
                      require_evidence: !store.quality.require_evidence,
                    })
                  }
                >
                  Evidence Only
                </Button>
                <Select
                  value={store.quality.detail_level}
                  onChange={(e) =>
                    store.setQuality({
                      detail_level: e.target.value as "balanced" | "corpus" | "exhaustive",
                    })
                  }
                >
                  <option value="balanced">Balanced</option>
                  <option value="corpus">Match Corpus</option>
                  <option value="exhaustive">Exhaustive</option>
                </Select>
              </div>
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
