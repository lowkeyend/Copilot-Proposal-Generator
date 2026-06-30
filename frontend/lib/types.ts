export interface ClientContext {
  client_name: string;
  industry: string;
  client_profile: "established" | "greenfield" | "unknown";
  canonical_product: string[];
  selected_documents: string[];
  intake: IntakeProfile;
  tone: string;
  special_instructions: string;
}

export interface IntakeProfile {
  project_mode: "implementation" | "upgrade" | "unknown";
  upgrade_type: "functional" | "technical" | "non-functional" | "mixed" | "unknown";
  launch_segments: string[];
  module_list: string[];
  phase_1_products: string[];
  phase_2_products: string[];
  regulatory_interfaces_phase_1: string[];
  regulatory_interfaces_phase_2: string[];
  channels_phase_1: string[];
  channels_phase_2: string[];
  middleware_platform: string;
  reporting_platform: string;
  database_platform: string;
  hosting_model: string;
  container_platform: string;
  data_warehouse_platform: string;
  implementation_methodology: string;
  delivery_model: string;
  current_system: string;
  current_version: string;
  target_version: string;
  upgrade_strategy: string;
  hardware_requirements: string;
  infrastructure_requirements: string;
  current_gaps: string;
  desired_capabilities: string;
  target_customers_year_1: string;
  target_customers_year_2: string;
  target_customers_year_3: string;
  target_accounts_year_1: string;
  target_accounts_year_2: string;
  target_accounts_year_3: string;
  launch_plan: string;
  questionnaire_notes: string;
}

export interface TemplateSection {
  title: string;
  keywords: string[];
  description: string;
}

export interface ProposalTemplate {
  id: string;
  name: string;
  proposal_family: string;
  sections: TemplateSection[];
  origin: "discovered" | "user";
  support: number;
  created_at?: string;
  updated_at?: string;
}

export interface TocSection {
  id: string;
  title: string;
  keywords: string[];
  description: string;
}

export interface EvidenceChunk {
  text: string;
  score: number;
  summary: string;
  source_proposal: string;
  source_section: string;
  source_document: string;
  proposal_family: string;
  chunk_id: string;
  source_type: string;
}

export interface SectionResult {
  id: string;
  title: string;
  content: string;
  evidence: EvidenceChunk[];
  locked: boolean;
  model: string;
  generated_at: string;
}

export interface ReviewIssue {
  severity: "info" | "warning" | "error";
  category: string;
  message: string;
  section_title: string;
}

export interface KnowledgeBaseStatus {
  connected: boolean;
  collection: string;
  points: number;
  mode: string;
  embedding_ready?: boolean;
  embedding_provider?: string;
  embedding_model?: string;
  message: string;
}

export interface OpenRouterSettingsStatus {
  api_key_set: boolean;
  source: "runtime" | "env" | "none";
  default_model: string;
  models: string[];
}

export interface OpenRouterSettingsUpdate {
  api_key: string;
  model?: string;
}

export interface OpenRouterSettingsCheckResponse {
  ok: boolean;
  fallback: boolean;
  source: "request" | "runtime" | "env" | "none";
  model: string;
  message: string;
  detail: string;
}

export interface KnowledgeBaseChunk {
  chunk_id: string;
  summary: string;
  text: string;
  source_proposal: string;
  source_section: string;
  source_document: string;
  proposal_family: string;
  score: number;
  payload: Record<string, unknown>;
}

export interface KnowledgeBaseChunkUpdate {
  text?: string;
  source_proposal?: string;
  source_section?: string;
  proposal_family?: string;
  source_document?: string;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface DocumentQueryResponse {
  answer: string;
  evidence: EvidenceChunk[];
  used_documents: string[];
}

export interface ParsedField {
  key: string;
  label: string;
  value: string;
  category: string;
  confidence: number;
  source_excerpt: string;
  notes: string;
}

export interface RfpParseResponse {
  filename: string;
  title: string;
  project_mode: "implementation" | "upgrade" | "unknown";
  storyline: string;
  fields: ParsedField[];
  intake: IntakeProfile;
  summary: string;
  missing_fields: string[];
  next_steps: string[];
}

export interface PlannerResponse {
  next_steps: string[];
  risks: string[];
  verifications: string[];
  milestones: string[];
  open_questions: string[];
  timeline_notes: string[];
  manday_estimates: MandayEstimate[];
  role_assignments: RoleAssignment[];
  decision_gates: string[];
}

export interface InsightItem {
  title: string;
  detail: string;
  severity: "low" | "medium" | "high";
  evidence: string[];
  action: string;
}

export interface MandayEstimate {
  workstream: string;
  low: number;
  high: number;
  rationale: string;
}

export interface RoleAssignment {
  role: string;
  owns: string[];
  checkpoints: string[];
}

export interface ModuleHardwareClassification {
  module: string;
  complexity: "low" | "medium" | "high";
  hardware_band: "small" | "medium" | "large";
  signals: string[];
  recommendation: string;
}

export interface InsightResponse {
  summary: string;
  insight_items: InsightItem[];
  leakage_warnings: InsightItem[];
  scope_gaps: InsightItem[];
  manday_estimates: MandayEstimate[];
  role_assignments: RoleAssignment[];
  module_hardware: ModuleHardwareClassification[];
  proposal_targets: string[];
  next_best_actions: string[];
}

export interface KnowledgeBaseUploadResponse {
  files: string[];
  chunks_written: number;
  collection: string;
  detail: string;
}

export interface ProposalQualitySettings {
  include_temenos_official: boolean;
  use_hybrid_retrieval: boolean;
  require_evidence: boolean;
  detail_level: "balanced" | "corpus" | "exhaustive";
  top_k: number;
}

export interface VersionMeta {
  version_id: string;
  label: string;
  created_at: string;
  sections: number;
}
