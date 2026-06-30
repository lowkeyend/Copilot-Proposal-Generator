import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  ClientContext,
  ProposalTemplate,
  ProposalQualitySettings,
  RfpParseResponse,
  SectionResult,
  TocSection,
} from "./types";
import { uid } from "./utils";

interface ProposalState {
  // setup
  prompt: string;
  model: string;
  context: ClientContext;
  proposalFamily: string;
  familyRationale: string;
  template: ProposalTemplate | null;
  quality: ProposalQualitySettings;
  parsedRfp: RfpParseResponse | null;

  // workspace
  toc: TocSection[];
  sections: SectionResult[];
  proposalId: string | null;

  // setters
  setPrompt: (v: string) => void;
  setModel: (v: string) => void;
  setContext: (c: Partial<ClientContext>) => void;
  setProposalFamily: (v: string) => void;
  setFamilyRationale: (v: string) => void;
  setTemplate: (t: ProposalTemplate | null) => void;
  setQuality: (patch: Partial<ProposalQualitySettings>) => void;
  setParsedRfp: (value: RfpParseResponse | null) => void;

  setToc: (toc: TocSection[]) => void;
  addTocSection: (title?: string) => void;
  updateTocSection: (id: string, patch: Partial<TocSection>) => void;
  removeTocSection: (id: string) => void;
  moveTocSection: (id: string, dir: -1 | 1) => void;

  setSections: (s: SectionResult[]) => void;
  upsertSection: (s: SectionResult) => void;
  updateSection: (id: string, patch: Partial<SectionResult>) => void;
  removeSection: (id: string) => void;
  moveSection: (id: string, dir: -1 | 1) => void;
  setProposalId: (id: string | null) => void;

  resetWorkspace: () => void;
}

const emptyContext: ClientContext = {
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
  },
  tone: "Formal",
  special_instructions: "",
};

const defaultQuality: ProposalQualitySettings = {
  include_temenos_official: false,
  use_hybrid_retrieval: true,
  require_evidence: true,
  detail_level: "corpus",
  top_k: 10,
};

function move<T extends { id: string }>(arr: T[], id: string, dir: -1 | 1): T[] {
  const idx = arr.findIndex((x) => x.id === id);
  if (idx === -1) return arr;
  const next = idx + dir;
  if (next < 0 || next >= arr.length) return arr;
  const copy = [...arr];
  [copy[idx], copy[next]] = [copy[next], copy[idx]];
  return copy;
}

export const useProposalStore = create<ProposalState>()(
  persist(
    (set) => ({
      prompt: "",
      model: "openrouter/free",
      context: { ...emptyContext },
      proposalFamily: "",
      familyRationale: "",
      template: null,
      quality: { ...defaultQuality },
      parsedRfp: null,
      toc: [],
      sections: [],
      proposalId: null,

      setPrompt: (v) => set({ prompt: v }),
      setModel: (v) => set({ model: v }),
      setContext: (c) =>
        set((s) => ({ context: { ...s.context, ...c } })),
      setProposalFamily: (v) => set({ proposalFamily: v }),
      setFamilyRationale: (v) => set({ familyRationale: v }),
      setTemplate: (t) => set({ template: t }),
      setQuality: (patch) =>
        set((s) => ({ quality: { ...s.quality, ...patch } })),
      setParsedRfp: (value) => set({ parsedRfp: value }),

      setToc: (toc) => set({ toc }),
      addTocSection: (title = "New Section") =>
        set((s) => ({
          toc: [
            ...s.toc,
            { id: uid(), title, keywords: [], description: "" },
          ],
        })),
      updateTocSection: (id, patch) =>
        set((s) => ({
          toc: s.toc.map((t) => (t.id === id ? { ...t, ...patch } : t)),
        })),
      removeTocSection: (id) =>
        set((s) => ({ toc: s.toc.filter((t) => t.id !== id) })),
      moveTocSection: (id, dir) =>
        set((s) => ({ toc: move(s.toc, id, dir) })),

      setSections: (sections) => set({ sections }),
      upsertSection: (section) =>
        set((s) => {
          const exists = s.sections.some((x) => x.id === section.id);
          return {
            sections: exists
              ? s.sections.map((x) => (x.id === section.id ? section : x))
              : [...s.sections, section],
          };
        }),
      updateSection: (id, patch) =>
        set((s) => ({
          sections: s.sections.map((x) =>
            x.id === id ? { ...x, ...patch } : x
          ),
        })),
      removeSection: (id) =>
        set((s) => ({ sections: s.sections.filter((x) => x.id !== id) })),
      moveSection: (id, dir) =>
        set((s) => ({ sections: move(s.sections, id, dir) })),
      setProposalId: (id) => set({ proposalId: id }),

      resetWorkspace: () =>
        set({
          prompt: "",
          model: "openrouter/free",
          context: { ...emptyContext },
          proposalFamily: "",
          familyRationale: "",
          template: null,
          quality: { ...defaultQuality },
          parsedRfp: null,
          toc: [],
          sections: [],
          proposalId: null,
        }),
    }),
    {
      name: "proposal-copilot",
      version: 3,
      migrate: (persisted: any) => {
        const context = persisted?.context ?? {};
        const intake = context?.intake ?? {};
        const canonicalProduct = context?.canonical_product;
        const normalizedCanonicalProduct = Array.isArray(canonicalProduct)
          ? canonicalProduct.filter((item: unknown) => typeof item === "string" && item.trim())
          : typeof canonicalProduct === "string" && canonicalProduct.trim()
            ? [canonicalProduct.trim()]
            : [...emptyContext.canonical_product];
        return {
          ...persisted,
          context: {
            ...emptyContext,
            ...context,
            canonical_product: normalizedCanonicalProduct,
            selected_documents: Array.isArray(context.selected_documents)
              ? context.selected_documents.filter((item: unknown) => typeof item === "string" && item.trim())
              : [],
            intake: {
              ...emptyContext.intake,
              ...intake,
              module_list: Array.isArray(intake.module_list) ? intake.module_list : [],
            },
          },
          quality: {
            ...defaultQuality,
            ...(persisted?.quality ?? {}),
          },
          parsedRfp: persisted?.parsedRfp ?? null,
        };
      },
    }
  )
);
