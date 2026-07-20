"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Database, FileText, Sparkles, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { useProposalStore } from "@/lib/store";
import type { ClientContext, IntakeProfile } from "@/lib/types";
import {
  CHANNEL_LIBRARY,
  DELIVERY_MODEL_OPTIONS,
  HOSTING_OPTIONS,
  MIDDLEWARE_OPTIONS,
  MODULE_LIBRARY,
  PRODUCT_LIBRARY,
  PROJECT_MODE_OPTIONS,
  REGULATORY_INTERFACE_LIBRARY,
  REPORTING_OPTIONS,
  DATABASE_OPTIONS,
  CONTAINER_OPTIONS,
  DATA_WAREHOUSE_OPTIONS,
  SAMPLE_PROMPTS,
  SEGMENT_OPTIONS,
  TEMENOS_PRODUCT_OPTIONS,
  UPGRADE_TYPE_OPTIONS,
  getPhaseOptions,
} from "@/lib/intakeOptions";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { KbStatus } from "@/components/KbStatus";

const EMPTY_INTAKE: IntakeProfile = {
  project_mode: "implementation",
  upgrade_type: "unknown",
  launch_segments: [], module_list: [], phase_1_products: [], phase_2_products: [],
  regulatory_interfaces_phase_1: [], regulatory_interfaces_phase_2: [],
  channels_phase_1: [], channels_phase_2: [], middleware_platform: "",
  reporting_platform: "", database_platform: "", hosting_model: "", container_platform: "",
  data_warehouse_platform: "", implementation_methodology: "TIM", delivery_model: "Phased MVP",
  current_system: "", current_version: "", target_version: "", upgrade_strategy: "",
  hardware_requirements: "", infrastructure_requirements: "", current_gaps: "",
  desired_capabilities: "", target_customers_year_1: "", target_customers_year_2: "",
  target_customers_year_3: "", target_accounts_year_1: "", target_accounts_year_2: "",
  target_accounts_year_3: "", launch_plan: "", questionnaire_notes: "",
};

const EMPTY_CONTEXT: ClientContext = {
  client_name: "", industry: "", client_profile: "established", canonical_product: [],
  selected_documents: [], intake: EMPTY_INTAKE, tone: "Formal", special_instructions: "",
};

type MultiKey = "launch_segments" | "module_list" | "phase_1_products" | "phase_2_products" |
  "regulatory_interfaces_phase_1" | "regulatory_interfaces_phase_2" | "channels_phase_1" | "channels_phase_2";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label>{label}</Label>{children}</div>;
}

function Choices({ options, value, onChange }: { options: string[]; value: string[]; onChange: (value: string[]) => void }) {
  return <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
    {options.map((option) => {
      const selected = value.includes(option);
      return <button key={option} type="button" onClick={() => onChange(selected ? value.filter((item) => item !== option) : [...value, option])}
        className={`rounded-lg border px-3 py-2 text-left text-sm transition ${selected ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card hover:border-primary/50"}`}>
        {option}
      </button>;
    })}
  </div>;
}

export default function StartPage() {
  const router = useRouter();
  const store = useProposalStore();
  const [context, setContext] = useState<ClientContext>(() => ({ ...EMPTY_CONTEXT, intake: { ...EMPTY_INTAKE } }));
  const [prompt, setPrompt] = useState("");
  const [documents, setDocuments] = useState<string[]>([]);
  const [models, setModels] = useState<string[]>(["groq/openai/gpt-oss-20b"]);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.models().then((result) => setModels(result.models)).catch(() => undefined);
    api.listKnowledgeChunks(5000).then((result) => {
      setDocuments(Array.from(new Set(result.chunks.map((chunk) => chunk.source_document).filter(Boolean))).sort());
    }).catch(() => undefined);
  }, []);

  const segments = context.intake.launch_segments;
  const products = useMemo(() => Array.from(new Set(segments.flatMap((item) => PRODUCT_LIBRARY[item] || []))), [segments]);
  const modules = useMemo(() => Array.from(new Set(segments.flatMap((item) => MODULE_LIBRARY[item] || []))), [segments]);
  const interfaces = useMemo(() => Array.from(new Set(segments.flatMap((item) => REGULATORY_INTERFACE_LIBRARY[item] || []))), [segments]);
  const channels = useMemo(() => Array.from(new Set(segments.flatMap((item) => CHANNEL_LIBRARY[item] || []))), [segments]);
  const intake = context.intake;
  const updateContext = (patch: Partial<ClientContext>) => setContext((current) => ({ ...current, ...patch }));
  const updateIntake = (patch: Partial<IntakeProfile>) => setContext((current) => ({ ...current, intake: { ...current.intake, ...patch } }));
  const updateMulti = (key: MultiKey, value: string[]) => updateIntake({ [key]: value } as Partial<IntakeProfile>);

  async function generate() {
    if (!prompt.trim()) { setError("Describe the proposal in the prompt before continuing."); return; }
    setLoading(true); setError("");
    try {
      setStage("Reading questionnaire and selected documents…");
      const generated = await api.generateContext({ prompt, model: store.model, client_name: context.client_name || undefined, industry: context.industry || undefined, client_profile: context.client_profile, selected_documents: context.selected_documents, intake: context.intake });
      store.setPrompt(prompt); store.setContext(generated.context); store.setProposalFamily(generated.proposal_family); store.setFamilyRationale(generated.family_rationale);
      setStage("Loading proposal template and table of contents…");
      const template = await api.suggestTemplate({ prompt, context: generated.context, proposal_family: generated.proposal_family, model: store.model });
      store.setTemplate(template.suggested);
      const toc = await api.buildToc({ prompt, context: generated.context, proposal_family: generated.proposal_family, template: template.suggested, model: store.model });
      store.setToc(toc.toc);
      router.push("/workspace");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to start the proposal."); }
    finally { setLoading(false); setStage(""); }
  }

  return <main className="mx-auto max-w-7xl px-4 py-8">
    <header className="mb-7 flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-3"><div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground"><FileText className="h-6 w-6" /></div><div><h1 className="text-2xl font-bold">Start a Proposal</h1><p className="text-sm text-muted-foreground">Complete the questionnaire first, then generate from grounded evidence.</p></div></div>
      <div className="flex items-center gap-2"><Button variant="outline" size="sm" onClick={() => router.push("/knowledge-base")}><Database className="h-4 w-4" /> Knowledge Base</Button><Button variant="outline" size="sm" onClick={() => router.push("/knowledge-base?view=upload")}><Upload className="h-4 w-4" /> Add Docs</Button><KbStatus /></div>
    </header>

    <div className="space-y-5">
      <Card><CardContent className="grid gap-4 pt-5 md:grid-cols-4">
        <Field label="Client Name"><Input value={context.client_name} onChange={(e) => updateContext({ client_name: e.target.value })} placeholder="Bank of Punjab" /></Field>
        <Field label="Industry"><Input value={context.industry} onChange={(e) => updateContext({ industry: e.target.value })} placeholder="Banking" /></Field>
        <Field label="Project Mode"><Select value={intake.project_mode} onChange={(e) => updateIntake({ project_mode: e.target.value as IntakeProfile["project_mode"] })}>{PROJECT_MODE_OPTIONS.map((item) => <option key={item}>{item}</option>)}</Select></Field>
        <Field label="Client Profile"><Select value={context.client_profile} onChange={(e) => updateContext({ client_profile: e.target.value as ClientContext["client_profile"] })}><option value="established">Established / modernization</option><option value="greenfield">Greenfield / new bank</option><option value="unknown">Unknown</option></Select></Field>
        <Field label="Canonical Product"><select multiple value={context.canonical_product} onChange={(e) => updateContext({ canonical_product: Array.from(e.target.selectedOptions, (option) => option.value) })} className="min-h-24 w-full rounded-md border border-input bg-card px-3 py-2 text-sm">{TEMENOS_PRODUCT_OPTIONS.map((item) => <option key={item}>{item}</option>)}</select></Field>
        <Field label="Upgrade Type"><Select value={intake.upgrade_type} onChange={(e) => updateIntake({ upgrade_type: e.target.value as IntakeProfile["upgrade_type"] })}><option value="unknown">Not applicable / unknown</option>{UPGRADE_TYPE_OPTIONS.map((item) => <option key={item}>{item}</option>)}</Select></Field>
        <Field label="Current System"><Input value={intake.current_system} onChange={(e) => updateIntake({ current_system: e.target.value })} placeholder="Current platform" /></Field>
        <Field label="Current / Target Version"><div className="grid grid-cols-2 gap-2"><Input value={intake.current_version} onChange={(e) => updateIntake({ current_version: e.target.value })} placeholder="Current" /><Input value={intake.target_version} onChange={(e) => updateIntake({ target_version: e.target.value })} placeholder="Target" /></div></Field>
      </CardContent></Card>

      <Card><CardContent className="space-y-5 pt-5"><div><h2 className="font-semibold">Scope Questionnaire</h2><p className="text-sm text-muted-foreground">Selections constrain the proposal scope and prevent unrelated phase or segment leakage.</p></div>
        <Field label="Segments"><Choices options={SEGMENT_OPTIONS} value={segments} onChange={(value) => updateMulti("launch_segments", value)} /></Field>
        <Field label="Module List"><Choices options={modules} value={intake.module_list} onChange={(value) => updateMulti("module_list", value)} /></Field>
        <div className="grid gap-5 lg:grid-cols-2"><Field label="Phase 1 Products"><Choices options={products} value={intake.phase_1_products} onChange={(value) => updateMulti("phase_1_products", value)} /></Field><Field label="Phase 2 Products"><Choices options={getPhaseOptions(products, intake.phase_1_products)} value={intake.phase_2_products} onChange={(value) => updateMulti("phase_2_products", value)} /></Field></div>
        <div className="grid gap-5 lg:grid-cols-2"><Field label="Phase 1 Regulatory Interfaces"><Choices options={interfaces} value={intake.regulatory_interfaces_phase_1} onChange={(value) => updateMulti("regulatory_interfaces_phase_1", value)} /></Field><Field label="Phase 2 Regulatory Interfaces"><Choices options={getPhaseOptions(interfaces, intake.regulatory_interfaces_phase_1)} value={intake.regulatory_interfaces_phase_2} onChange={(value) => updateMulti("regulatory_interfaces_phase_2", value)} /></Field></div>
        <div className="grid gap-5 lg:grid-cols-2"><Field label="Phase 1 Channels"><Choices options={channels} value={intake.channels_phase_1} onChange={(value) => updateMulti("channels_phase_1", value)} /></Field><Field label="Phase 2 Channels"><Choices options={getPhaseOptions(channels, intake.channels_phase_1)} value={intake.channels_phase_2} onChange={(value) => updateMulti("channels_phase_2", value)} /></Field></div>
      </CardContent></Card>

      <Card><CardContent className="space-y-5 pt-5"><h2 className="font-semibold">Delivery, Platform and Volumes</h2><div className="grid gap-4 md:grid-cols-3"><Field label="Delivery Model"><Select value={intake.delivery_model} onChange={(e) => updateIntake({ delivery_model: e.target.value })}>{DELIVERY_MODEL_OPTIONS.map((item) => <option key={item}>{item}</option>)}</Select></Field><Field label="Hosting"><Select value={intake.hosting_model} onChange={(e) => updateIntake({ hosting_model: e.target.value })}><option value="">Select hosting</option>{HOSTING_OPTIONS.map((item) => <option key={item}>{item}</option>)}</Select></Field><Field label="Database"><Select value={intake.database_platform} onChange={(e) => updateIntake({ database_platform: e.target.value })}><option value="">Select database</option>{DATABASE_OPTIONS.map((item) => <option key={item}>{item}</option>)}</Select></Field><Field label="Middleware"><Select value={intake.middleware_platform} onChange={(e) => updateIntake({ middleware_platform: e.target.value })}><option value="">Select middleware</option>{MIDDLEWARE_OPTIONS.map((item) => <option key={item}>{item}</option>)}</Select></Field><Field label="Reporting"><Select value={intake.reporting_platform} onChange={(e) => updateIntake({ reporting_platform: e.target.value })}><option value="">Select reporting</option>{REPORTING_OPTIONS.map((item) => <option key={item}>{item}</option>)}</Select></Field><Field label="Container"><Select value={intake.container_platform} onChange={(e) => updateIntake({ container_platform: e.target.value })}><option value="">Select container</option>{CONTAINER_OPTIONS.map((item) => <option key={item}>{item}</option>)}</Select></Field><Field label="Data Warehouse"><Select value={intake.data_warehouse_platform} onChange={(e) => updateIntake({ data_warehouse_platform: e.target.value })}><option value="">Select warehouse</option>{DATA_WAREHOUSE_OPTIONS.map((item) => <option key={item}>{item}</option>)}</Select></Field></div>
        <div className="grid gap-4 md:grid-cols-3">{(["target_customers_year_1", "target_customers_year_2", "target_customers_year_3", "target_accounts_year_1", "target_accounts_year_2", "target_accounts_year_3"] as const).map((key) => <Field key={key} label={key.replaceAll("_", " ")}><Input value={intake[key]} onChange={(e) => updateIntake({ [key]: e.target.value } as Partial<IntakeProfile>)} /></Field>)}</div>
        <div className="grid gap-4 md:grid-cols-2"><Field label="Launch Plan"><Textarea value={intake.launch_plan} onChange={(e) => updateIntake({ launch_plan: e.target.value })} rows={3} /></Field><Field label="Current Gaps / Desired Capabilities"><Textarea value={`${intake.current_gaps}${intake.desired_capabilities ? `\n${intake.desired_capabilities}` : ""}`} onChange={(e) => updateIntake({ current_gaps: e.target.value })} rows={3} /></Field></div>
      </CardContent></Card>

      <Card><CardContent className="space-y-4 pt-5"><div className="grid gap-4 md:grid-cols-2"><Field label="Selected Source Documents"><select multiple value={context.selected_documents} onChange={(e) => updateContext({ selected_documents: Array.from(e.target.selectedOptions, (option) => option.value) })} className="min-h-32 w-full rounded-md border border-input bg-card px-3 py-2 text-sm">{documents.map((item) => <option key={item}>{item}</option>)}</select></Field><Field label="Master Prompt"><Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={6} placeholder="Prepare a client-ready proposal using only the selected documents and questionnaire selections. Preserve source-supported detail and do not invent facts." /></Field></div><div className="flex flex-wrap gap-2">{SAMPLE_PROMPTS.map((item) => <button key={item} type="button" onClick={() => setPrompt(item)} className="rounded-full border border-border px-3 py-1.5 text-xs hover:border-primary">Use sample prompt</button>)}</div><div className="grid gap-4 md:grid-cols-3"><Field label="Tone"><Select value={context.tone} onChange={(e) => updateContext({ tone: e.target.value })}>{["Formal", "Confident", "Consultative", "Concise", "Persuasive"].map((item) => <option key={item}>{item}</option>)}</Select></Field><Field label="Model"><Select value={store.model} onChange={(e) => store.setModel(e.target.value)}>{models.map((item) => <option key={item}>{item}</option>)}</Select></Field><Field label="Special Instructions"><Input value={context.special_instructions} onChange={(e) => updateContext({ special_instructions: e.target.value })} placeholder="Formatting or emphasis" /></Field></div>{error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}<div className="flex justify-end"><Button onClick={generate} disabled={loading}>{loading ? <Spinner /> : <Sparkles className="h-4 w-4" />}{loading ? stage || "Working…" : "Continue to Workspace"}<ArrowRight className="h-4 w-4" /></Button></div></CardContent></Card>
    </div>
  </main>;
}
