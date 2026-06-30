"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, Database, FileText, Upload, Wand2 } from "lucide-react";
import { api } from "@/lib/api";
import { useProposalStore } from "@/lib/store";
import type { ClientContext, IntakeProfile } from "@/lib/types";
import {
  CONTAINER_OPTIONS,
  DATABASE_OPTIONS,
  DATA_WAREHOUSE_OPTIONS,
  DELIVERY_MODEL_OPTIONS,
  HOSTING_OPTIONS,
  MIDDLEWARE_OPTIONS,
  MODULE_LIBRARY,
  PROJECT_MODE_OPTIONS,
  PRODUCT_LIBRARY,
  REPORTING_OPTIONS,
  SAMPLE_PROMPTS,
  SEGMENT_OPTIONS,
  UPGRADE_TYPE_OPTIONS,
  TEMENOS_PRODUCT_OPTIONS,
  getChannelsForSegments,
  getInterfacesForSegments,
  getPhaseOptions,
  getModulesForSegments,
  getProductsForSegments,
} from "@/lib/intakeOptions";
import { DropdownMultiSelect } from "@/components/DropdownMultiSelect";
import { Button } from "@/components/ui/button";
import { Input, Textarea, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { KbStatus } from "@/components/KbStatus";
import { cn } from "@/lib/utils";

const EMPTY_SETUP_CONTEXT: ClientContext = {
  client_name: "",
  industry: "",
  client_profile: "established",
  canonical_product: ["Temenos Transact"],
  selected_documents: [],
  intake: {
    project_mode: "implementation",
    upgrade_type: "unknown",
    launch_segments: [],
    module_list: [],
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
    current_system: "",
    current_version: "",
    target_version: "",
    upgrade_strategy: "",
    hardware_requirements: "",
    infrastructure_requirements: "",
    current_gaps: "",
    desired_capabilities: "",
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

function SectionShell({
  title,
  subtitle,
  children,
  defaultOpen = true,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details open={defaultOpen} className="group rounded-2xl border border-border bg-card">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-4">
        <div>
          <div className="text-sm font-semibold">{title}</div>
          {subtitle ? <div className="mt-1 text-xs text-muted-foreground">{subtitle}</div> : null}
        </div>
        <ChevronDown className="h-4 w-4 shrink-0 transition-transform duration-200 group-open:rotate-180" />
      </summary>
      <div className="border-t border-border px-4 pb-4">{children}</div>
    </details>
  );
}

function canonicalProductLabel(values: string[]) {
  return values.filter(Boolean).join(", ");
}

function OptionBadge({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1.5 text-xs transition active:scale-[0.98]",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border bg-background text-foreground hover:bg-muted"
      )}
    >
      {label}
    </button>
  );
}

export default function SetupPage() {
  const router = useRouter();
  const store = useProposalStore();
  const [prompt, setPrompt] = useState("");
  const [context, setContext] = useState({ ...EMPTY_SETUP_CONTEXT });
  const [models, setModels] = useState<string[]>([]);
  const [knowledgeDocuments, setKnowledgeDocuments] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");

  const intake = context.intake;

  const selectedSegments = intake.launch_segments;
  const segmentProducts = useMemo(
    () => getProductsForSegments(selectedSegments),
    [selectedSegments]
  );
  const allowedPhase2Products = useMemo(
    () => getPhaseOptions(segmentProducts, intake.phase_1_products),
    [segmentProducts, intake.phase_1_products]
  );
  const allowedInterfaces = useMemo(
    () => getInterfacesForSegments(selectedSegments),
    [selectedSegments]
  );
  const allowedChannels = useMemo(
    () => getChannelsForSegments(selectedSegments),
    [selectedSegments]
  );
  const allowedModules = useMemo(
    () => getModulesForSegments(selectedSegments),
    [selectedSegments]
  );
  const showPhase2 = intake.delivery_model !== "Big Bang";
  const showPhase3 = intake.delivery_model === "Hybrid Phased Rollout";

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

  useEffect(() => {
    api
      .listKnowledgeChunks(2000)
      .then((res) => {
        const docs = Array.from(
          new Set(
            res.chunks
              .map((chunk) => chunk.source_document || chunk.source_proposal)
              .filter((value): value is string => Boolean(value && value.trim()))
          )
        ).sort((a, b) => a.localeCompare(b));
        setKnowledgeDocuments(docs);
      })
      .catch(() => setKnowledgeDocuments([]));
  }, []);

  useEffect(() => {
    if (intake.delivery_model === "Big Bang") {
      updateIntake({
        phase_2_products: [],
        regulatory_interfaces_phase_2: [],
        channels_phase_2: [],
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intake.delivery_model]);

  useEffect(() => {
    const cleanedPhase2Products = intake.phase_2_products.filter((item) =>
      allowedPhase2Products.includes(item)
    );
    if (cleanedPhase2Products.length !== intake.phase_2_products.length) {
      updateIntake({ phase_2_products: cleanedPhase2Products });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowedPhase2Products.join("|")]);

  useEffect(() => {
    const cleanedInterfaces = intake.regulatory_interfaces_phase_1.filter((item) =>
      allowedInterfaces.includes(item)
    );
    if (cleanedInterfaces.length !== intake.regulatory_interfaces_phase_1.length) {
      updateIntake({ regulatory_interfaces_phase_1: cleanedInterfaces });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowedInterfaces.join("|")]);

  useEffect(() => {
    const cleanedChannels = intake.channels_phase_1.filter((item) =>
      allowedChannels.includes(item)
    );
    if (cleanedChannels.length !== intake.channels_phase_1.length) {
      updateIntake({ channels_phase_1: cleanedChannels });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowedChannels.join("|")]);

  function updateContext(patch: Partial<ClientContext>) {
    setContext((current) => ({ ...current, ...patch }));
  }

  function updateIntake(patch: Partial<IntakeProfile>) {
    setContext((current) => ({
      ...current,
      intake: { ...current.intake, ...patch },
    }));
  }

  async function handleGenerate() {
    if (!prompt.trim()) {
      setError("Please describe the proposal you want to generate.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      setStage("Extracting context and scope...");
      const ctx = await api.generateContext({
        prompt,
        model: store.model,
        client_name: context.client_name || undefined,
        industry: context.industry || undefined,
        client_profile: context.client_profile || "established",
        canonical_product: context.canonical_product[0] || undefined,
        selected_documents: context.selected_documents,
        intake: context.intake,
      });
      store.setPrompt(prompt);
      store.setContext({
        ...ctx.context,
        canonical_product: Array.isArray(ctx.context.canonical_product)
          ? ctx.context.canonical_product
          : [ctx.context.canonical_product].filter(Boolean),
        selected_documents: Array.isArray(ctx.context.selected_documents)
          ? ctx.context.selected_documents
          : [],
      });
      store.setProposalFamily(ctx.proposal_family);
      store.setFamilyRationale(ctx.family_rationale);

      setStage("Selecting a corpus pattern...");
      const tpl = await api.suggestTemplate({
        prompt,
        context: ctx.context,
        proposal_family: ctx.proposal_family,
        model: store.model,
      });
      store.setTemplate(tpl.suggested);

      setStage("Building the TOC...");
      const toc = await api.buildToc({
        prompt,
        context: ctx.context,
        proposal_family: ctx.proposal_family,
        template: tpl.suggested,
        model: store.model,
      });
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

  const productTabs = useMemo(() => {
    const all = segmentProducts.length ? segmentProducts : Object.values(PRODUCT_LIBRARY).flat();
    return Array.from(new Set(all));
  }, [segmentProducts]);
  const moduleTabs = useMemo(() => {
    const all = allowedModules.length ? allowedModules : Object.values(MODULE_LIBRARY).flat();
    return Array.from(new Set(all));
  }, [allowedModules]);

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <FileText className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Proposal Copilot</h1>
            <p className="text-sm text-muted-foreground">
              Controlled intake, correlated scope, evidence-first proposal generation.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => router.push("/knowledge-base")}>
            <Database className="h-4 w-4" />
            Knowledge Base
          </Button>
          <Button variant="outline" size="sm" onClick={() => router.push("/knowledge-base?view=upload")}>
            <Upload className="h-4 w-4" />
            Add Docs
          </Button>
          <KbStatus />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <section className="space-y-6 rounded-3xl border border-border bg-card p-5 shadow-sm">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Client Name</Label>
              <Input
                value={context.client_name}
                onChange={(e) => updateContext({ client_name: e.target.value })}
                placeholder="Bank Alfalah"
              />
            </div>
            <div className="space-y-2">
              <Label>Industry</Label>
              <Input
                value={context.industry}
                onChange={(e) => updateContext({ industry: e.target.value })}
                placeholder="Banking"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <DropdownMultiSelect
                label="Canonical Product"
                options={TEMENOS_PRODUCT_OPTIONS}
                value={context.canonical_product}
                onChange={(next) => updateContext({ canonical_product: next })}
                placeholder="Add canonical product"
                helper="Select one or more canonical Temenos products to guide wording and scope."
              />
            </div>
          </div>

          <SectionShell
            title="Engagement Mode"
            subtitle="Choose implementation or upgrade first so the rest of the intake stays correlated."
          >
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Project Mode</Label>
                <Select
                  value={intake.project_mode}
                  onChange={(e) => updateIntake({ project_mode: e.target.value as IntakeProfile["project_mode"] })}
                >
                  {PROJECT_MODE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option.charAt(0).toUpperCase() + option.slice(1)}
                    </option>
                  ))}
                  <option value="unknown">Unknown</option>
                </Select>
              </div>

              {intake.project_mode === "upgrade" ? (
                <div className="space-y-2">
                  <Label>Upgrade Type</Label>
                  <Select
                    value={intake.upgrade_type}
                    onChange={(e) =>
                      updateIntake({ upgrade_type: e.target.value as IntakeProfile["upgrade_type"] })
                    }
                  >
                    <option value="unknown">Select upgrade type</option>
                    {UPGRADE_TYPE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option.charAt(0).toUpperCase() + option.slice(1)}
                      </option>
                    ))}
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    Functional upgrades bias business scope and modules. Technical upgrades bias platform, database, and cutover detail. Non-functional upgrades bias NFRs, security, performance, and resilience.
                  </p>
                </div>
              ) : (
                <div className="rounded-2xl border border-dashed border-border p-4 text-sm text-muted-foreground">
                  Implementation mode is selected. Upgrade-specific questions stay de-emphasized unless you switch the project mode.
                </div>
              )}
            </div>
          </SectionShell>

          <SectionShell
            title="Delivery Model"
            subtitle="Controls how many phases appear in the intake and proposal plan."
          >
            <div className="grid gap-3 md:grid-cols-3">
              {DELIVERY_MODEL_OPTIONS.map((option) => (
                <OptionBadge
                  key={option}
                  label={option}
                  active={intake.delivery_model === option}
                  onClick={() => updateIntake({ delivery_model: option })}
                />
              ))}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              Big Bang shows only Phase 1. Phased MVP shows Phase 1 and Phase 2. Hybrid rollout can open a third phase in the planner.
            </p>
          </SectionShell>

          <SectionShell title="Client Segments" subtitle="Segments drive the product and channel options below.">
            <div className="grid gap-3 md:grid-cols-4">
              {SEGMENT_OPTIONS.map((option) => (
                <OptionBadge
                  key={option}
                  label={option}
                  active={intake.launch_segments.includes(option)}
                  onClick={() =>
                    updateIntake({
                      launch_segments: intake.launch_segments.includes(option)
                        ? intake.launch_segments.filter((item) => item !== option)
                        : [...intake.launch_segments, option],
                    })
                  }
                />
              ))}
            </div>
          </SectionShell>

          <SectionShell
            title="Module List"
            subtitle="Choose the modules in scope so the timeline builder can map delivery workstreams."
          >
            <DropdownMultiSelect
              label="Available modules"
              options={moduleTabs}
              value={intake.module_list}
              onChange={(next) => updateIntake({ module_list: next })}
              helper="This list is reused by the planner and timeline builder."
            />
            <div className="mt-3 flex flex-wrap gap-2">
              {moduleTabs.map((item) => (
                <OptionBadge
                  key={item}
                  label={item}
                  active={intake.module_list.includes(item)}
                  onClick={() =>
                    updateIntake({
                      module_list: intake.module_list.includes(item)
                        ? intake.module_list.filter((value) => value !== item)
                        : [...intake.module_list, item],
                    })
                  }
                />
              ))}
            </div>
          </SectionShell>

          <SectionShell
            title="Reference Documents"
            subtitle="Limit proposal generation to selected KB documents. Leave empty to use the full knowledge base."
          >
            <DropdownMultiSelect
              label="Selected documents"
              options={knowledgeDocuments}
              value={context.selected_documents}
              onChange={(next) => updateContext({ selected_documents: next })}
              placeholder="Choose reference documents"
              helper="Only these documents will feed proposal generation, planner guidance, and section writing when selected."
            />
            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => updateContext({ selected_documents: knowledgeDocuments })}>
                Select all docs
              </Button>
              <Button variant="outline" size="sm" onClick={() => updateContext({ selected_documents: [] })}>
                Use full KB
              </Button>
            </div>
          </SectionShell>

          <SectionShell title="Phase Scope" subtitle="Phase 1 and Phase 2 are shown side by side.">
            <div className={cn("grid gap-4", showPhase2 ? "md:grid-cols-2" : "md:grid-cols-1")}>
              <div className="space-y-4 rounded-2xl border border-border p-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold">Phase 1</h3>
                  <span className="text-xs text-muted-foreground">{intake.phase_1_products.length} selected</span>
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  {productTabs.map((item) => (
                    <OptionBadge
                      key={item}
                      label={item}
                      active={intake.phase_1_products.includes(item)}
                      onClick={() =>
                        updateIntake({
                          phase_1_products: intake.phase_1_products.includes(item)
                            ? intake.phase_1_products.filter((value) => value !== item)
                            : [...intake.phase_1_products, item],
                          phase_2_products: intake.phase_2_products.filter((value) => value !== item),
                        })
                      }
                    />
                  ))}
                </div>
                <DropdownMultiSelect
                  label="Selected products"
                  options={productTabs}
                  value={intake.phase_1_products}
                  onChange={(next) =>
                    updateIntake({
                      phase_1_products: next,
                      phase_2_products: intake.phase_2_products.filter((item) => !next.includes(item)),
                    })
                  }
                  helper="Choose from the full segment-driven product pool."
                />
              </div>

              {showPhase2 ? (
                <div className="space-y-4 rounded-2xl border border-border p-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold">Phase 2</h3>
                    <span className="text-xs text-muted-foreground">{intake.phase_2_products.length} selected</span>
                  </div>
                  <div className="grid gap-2 md:grid-cols-2">
                    {allowedPhase2Products.map((item) => (
                      <OptionBadge
                        key={item}
                        label={item}
                        active={intake.phase_2_products.includes(item)}
                        onClick={() =>
                          updateIntake({
                            phase_2_products: intake.phase_2_products.includes(item)
                              ? intake.phase_2_products.filter((value) => value !== item)
                              : [...intake.phase_2_products, item],
                          })
                        }
                      />
                    ))}
                  </div>
                  <DropdownMultiSelect
                    label="Remaining products"
                    options={allowedPhase2Products}
                    value={intake.phase_2_products}
                    onChange={(next) => updateIntake({ phase_2_products: next })}
                    helper="Phase 2 cannot repeat phase 1 selections."
                  />
                </div>
              ) : null}
            </div>
            {showPhase3 ? (
              <p className="mt-3 text-xs text-muted-foreground">
                Hybrid rollout selected. Use the planner to stage a third wave if the RFP requires it.
              </p>
            ) : null}
          </SectionShell>

          <SectionShell title="Demand & Growth" subtitle="Customer and account projections are collapsed until needed.">
            <details open={false} className="rounded-2xl border border-border p-4">
              <summary className="cursor-pointer list-none text-sm font-semibold">Year 1 Customers</summary>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>Year 1 Customers</Label>
                  <Input value={intake.target_customers_year_1} onChange={(e) => updateIntake({ target_customers_year_1: e.target.value })} />
                </div>
                <div className="space-y-2">
                  <Label>Year 2 Customers</Label>
                  <Input value={intake.target_customers_year_2} onChange={(e) => updateIntake({ target_customers_year_2: e.target.value })} />
                </div>
              </div>
            </details>
            <details className="mt-3 rounded-2xl border border-border p-4">
              <summary className="cursor-pointer list-none text-sm font-semibold">Year 3 Customers</summary>
              <div className="mt-3 space-y-2">
                <Label>Year 3 Customers</Label>
                <Input value={intake.target_customers_year_3} onChange={(e) => updateIntake({ target_customers_year_3: e.target.value })} />
              </div>
            </details>
            <details className="mt-3 rounded-2xl border border-border p-4">
              <summary className="cursor-pointer list-none text-sm font-semibold">Yearly Accounts</summary>
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                <div className="space-y-2">
                  <Label>Year 1 Accounts</Label>
                  <Input value={intake.target_accounts_year_1} onChange={(e) => updateIntake({ target_accounts_year_1: e.target.value })} />
                </div>
                <div className="space-y-2">
                  <Label>Year 2 Accounts</Label>
                  <Input value={intake.target_accounts_year_2} onChange={(e) => updateIntake({ target_accounts_year_2: e.target.value })} />
                </div>
                <div className="space-y-2">
                  <Label>Year 3 Accounts</Label>
                  <Input value={intake.target_accounts_year_3} onChange={(e) => updateIntake({ target_accounts_year_3: e.target.value })} />
                </div>
              </div>
            </details>
          </SectionShell>

          <SectionShell title="Regulatory Interfaces" subtitle="Collapsed by default. Expand when you need interface scope." defaultOpen={false}>
            <div className="space-y-4">
              <DropdownMultiSelect
                label="Phase 1 Interfaces"
                options={allowedInterfaces}
                value={intake.regulatory_interfaces_phase_1}
                onChange={(next) =>
                  updateIntake({
                    regulatory_interfaces_phase_1: next,
                    regulatory_interfaces_phase_2: intake.regulatory_interfaces_phase_2.filter(
                      (item) => !next.includes(item)
                    ),
                  })
                }
              />
              {showPhase2 ? (
                <DropdownMultiSelect
                  label="Phase 2 Interfaces"
                  options={getPhaseOptions(allowedInterfaces, intake.regulatory_interfaces_phase_1)}
                  value={intake.regulatory_interfaces_phase_2}
                  onChange={(next) => updateIntake({ regulatory_interfaces_phase_2: next })}
                />
              ) : null}
            </div>
          </SectionShell>

          <SectionShell title="Channels" subtitle="Collapsed by default. Expand when you need channel scope." defaultOpen={false}>
            <div className="space-y-4">
              <DropdownMultiSelect
                label="Phase 1 Channels"
                options={allowedChannels}
                value={intake.channels_phase_1}
                onChange={(next) =>
                  updateIntake({
                    channels_phase_1: next,
                    channels_phase_2: intake.channels_phase_2.filter((item) => !next.includes(item)),
                  })
                }
              />
              {showPhase2 ? (
                <DropdownMultiSelect
                  label="Phase 2 Channels"
                  options={getPhaseOptions(allowedChannels, intake.channels_phase_1)}
                  value={intake.channels_phase_2}
                  onChange={(next) => updateIntake({ channels_phase_2: next })}
                />
              ) : null}
            </div>
          </SectionShell>

          <SectionShell title="Platform Stack" subtitle="Collapsed by default to reduce noise." defaultOpen={false}>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Middleware</Label>
                <Select
                  value={intake.middleware_platform}
                  onChange={(e) => updateIntake({ middleware_platform: e.target.value })}
                >
                  <option value="">Select middleware</option>
                  {MIDDLEWARE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Reporting</Label>
                <Select
                  value={intake.reporting_platform}
                  onChange={(e) => updateIntake({ reporting_platform: e.target.value })}
                >
                  <option value="">Select reporting</option>
                  {REPORTING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Database</Label>
                <Select
                  value={intake.database_platform}
                  onChange={(e) => updateIntake({ database_platform: e.target.value })}
                >
                  <option value="">Select database</option>
                  {DATABASE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Hosting</Label>
                <Select
                  value={intake.hosting_model}
                  onChange={(e) => updateIntake({ hosting_model: e.target.value })}
                >
                  <option value="">Select hosting</option>
                  {HOSTING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Container Platform</Label>
                <Select
                  value={intake.container_platform}
                  onChange={(e) => updateIntake({ container_platform: e.target.value })}
                >
                  <option value="">Select container platform</option>
                  {CONTAINER_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Data Warehouse</Label>
                <Select
                  value={intake.data_warehouse_platform}
                  onChange={(e) => updateIntake({ data_warehouse_platform: e.target.value })}
                >
                  <option value="">Select warehouse</option>
                  {DATA_WAREHOUSE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </Select>
              </div>
            </div>
          </SectionShell>

          <div className="space-y-2">
            <Label>Prompt</Label>
            <Textarea
              rows={5}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the proposal you want to generate..."
            />
            <div className="flex flex-wrap gap-2">
              {SAMPLE_PROMPTS.map((sample) => (
                <Button key={sample} variant="outline" size="sm" onClick={() => setPrompt(sample)}>
                  Use sample
                </Button>
              ))}
            </div>
          </div>

          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          {stage ? <p className="text-sm text-muted-foreground">{stage}</p> : null}

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={handleGenerate} disabled={loading}>
              {loading ? <Spinner /> : <Wand2 className="h-4 w-4" />}
              Generate proposal
            </Button>
            <Button variant="outline" onClick={() => setContext({ ...EMPTY_SETUP_CONTEXT })}>
              Reset form
            </Button>
          </div>
        </section>

        <aside className="space-y-4">
          <section className="rounded-3xl border border-border bg-card p-5 shadow-sm">
            <h2 className="mb-2 text-sm font-semibold">LLM Settings</h2>
            <p className="text-sm text-muted-foreground">
              Manage the OpenRouter key from the dedicated Settings tab.
            </p>
            <div className="mt-3 flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={() => router.push("/settings")}>
                Open Settings
              </Button>
              <span className="text-xs text-muted-foreground">
                Key persistence and LLM checks live there.
              </span>
            </div>
            <div className="mt-4">
              <Label>Model</Label>
              <Select value={store.model} onChange={(e) => store.setModel(e.target.value)}>
                {models.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </Select>
            </div>
          </section>

          <section className="rounded-3xl border border-border bg-card p-5 shadow-sm">
            <h2 className="mb-2 text-sm font-semibold">Current Snapshot</h2>
            <div className="space-y-2 text-xs text-muted-foreground">
              <p>Client: {context.client_name || "Not set"}</p>
              <p>Industry: {context.industry || "Not set"}</p>
              <p>Canonical Product: {canonicalProductLabel(context.canonical_product)}</p>
              <p>Project Mode: {intake.project_mode}</p>
              {intake.project_mode === "upgrade" ? <p>Upgrade Type: {intake.upgrade_type}</p> : null}
              <p>Reference Docs: {context.selected_documents.length ? context.selected_documents.join(", ") : "All docs"}</p>
              <p>Segments: {intake.launch_segments.join(", ") || "None"}</p>
              <p>Phase 1: {intake.phase_1_products.join(", ") || "None"}</p>
              {showPhase2 ? <p>Phase 2: {intake.phase_2_products.join(", ") || "None"}</p> : null}
            </div>
          </section>

          <section className="rounded-3xl border border-border bg-card p-5 shadow-sm">
            <h2 className="mb-2 text-sm font-semibold">Scope Rules</h2>
            <div className="space-y-3 text-sm leading-6 text-muted-foreground">
              <p>• Big Bang hides Phase 2.</p>
              <p>• Phase 2 options exclude Phase 1 selections.</p>
              <p>• Segments constrain products, interfaces, and channels.</p>
              <p>• Selected reference documents are the only sources used for proposal generation when chosen.</p>
              <p>• The canonical product is selected from a fixed Temenos list.</p>
            </div>
          </section>
        </aside>
      </div>
    </main>
  );
}



