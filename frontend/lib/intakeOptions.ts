export const SEGMENT_OPTIONS = ["Retail", "SME", "Corporate", "Treasury"];

export const PROJECT_MODE_OPTIONS: Array<"implementation" | "upgrade"> = [
  "implementation",
  "upgrade",
];

export const UPGRADE_TYPE_OPTIONS = [
  "functional",
  "technical",
  "non-functional",
  "mixed",
] as const;

export const TEMENOS_PRODUCT_OPTIONS = [
  "Temenos Transact",
  "Temenos Infinity",
  "Temenos Payments Hub",
  "Temenos Financial Crime Mitigation",
  "Temenos Analytics",
  "Temenos Data Hub",
  "Temenos Journey Manager",
];

export const DELIVERY_MODEL_OPTIONS = [
  "Big Bang",
  "Phased MVP",
  "Hybrid Phased Rollout",
];

export const PRODUCT_LIBRARY: Record<string, string[]> = {
  Retail: [
    "Savings Accounts",
    "Current Accounts",
    "Customer Onboarding / KYC",
    "Domestic Payments",
    "ATM Services",
    "AML Screening",
    "Internal Transfers",
    "Teller Operations",
    "Internet Banking",
    "Mobile Banking",
    "Cards",
    "POS / Merchant Acquiring",
    "Retail Lending",
  ],
  SME: [
    "Current Accounts",
    "Customer Onboarding / KYC",
    "Domestic Payments",
    "AML Screening",
    "Internal Transfers",
    "Teller Operations",
    "Internet Banking",
    "Mobile Banking",
    "SME Lending",
    "Cash Management",
    "Trade Services",
  ],
  Corporate: [
    "Current Accounts",
    "Customer Onboarding / KYC",
    "Domestic Payments",
    "International Transfers",
    "Corporate Lending",
    "Trade Finance",
    "Treasury Products",
    "Cash Management",
    "SWIFT",
    "ERP / Finance",
  ],
  Treasury: [
    "Treasury Products",
    "International Transfers",
    "Cash Management",
    "FX",
    "Money Market",
    "Liquidity Management",
    "SWIFT",
    "Risk Controls",
  ],
};

export const MODULE_LIBRARY: Record<string, string[]> = {
  Retail: [
    "Deposits",
    "Savings",
    "Current Accounts",
    "Customer Onboarding",
    "Cards",
    "Payments",
    "Lending",
    "Digital Banking",
  ],
  SME: [
    "Business Accounts",
    "Customer Onboarding",
    "Payments",
    "Cash Management",
    "SME Lending",
    "Digital Banking",
    "Trade Services",
  ],
  Corporate: [
    "Corporate Accounts",
    "Cash Management",
    "Trade Finance",
    "Lending",
    "Treasury",
    "Payments",
    "Corporate Digital Channels",
  ],
  Treasury: [
    "Treasury Dealing",
    "Liquidity Management",
    "FX",
    "Money Market",
    "Risk Controls",
    "Settlement",
  ],
};

export const REGULATORY_INTERFACE_LIBRARY: Record<string, string[]> = {
  Retail: ["MMA Reporting", "RTGS / ACH", "AML / Sanctions Screening", "ATM Switch", "Identity Verification"],
  SME: ["MMA Reporting", "RTGS / ACH", "AML / Sanctions Screening", "Identity Verification"],
  Corporate: ["MMA Reporting", "RTGS / ACH", "SWIFT", "Credit Bureau", "Card Schemes"],
  Treasury: ["MMA Reporting", "SWIFT", "RTGS / ACH", "Regulatory Reporting Pack"],
};

export const CHANNEL_LIBRARY: Record<string, string[]> = {
  Retail: ["Branch / Teller", "ATM", "Payment Switch", "Call Center", "Internet Banking", "Mobile Banking"],
  SME: ["Branch / Teller", "Call Center", "Internet Banking", "Mobile Banking", "Notifications / AI Chatbots"],
  Corporate: ["Branch / Teller", "Call Center", "CRM", "ERP / Finance", "Internet Banking"],
  Treasury: ["Call Center", "CRM", "ERP / Finance", "SWIFT"],
};

export const MIDDLEWARE_OPTIONS = [
  "Temenos Integration Framework",
  "ESB / API Gateway",
  "MuleSoft",
  "WSO2",
  "Kafka / Event Bus",
];

export const REPORTING_OPTIONS = [
  "Temenos Reporting",
  "Temenos TDH",
  "Enterprise MIS",
  "Regulatory Reporting Pack",
];

export const DATABASE_OPTIONS = [
  "Oracle 19c+",
  "PostgreSQL",
  "Microsoft SQL Server",
  "MySQL",
  "Temenos-managed",
];

export const HOSTING_OPTIONS = [
  "AWS Cloud",
  "Azure Cloud",
  "Google Cloud",
  "Hybrid Cloud",
  "On-Premise",
];

export const CONTAINER_OPTIONS = [
  "Red Hat OpenShift",
  "Kubernetes",
  "Docker / Containerized",
  "Not Mandatory for MVP",
];

export const DATA_WAREHOUSE_OPTIONS = [
  "Temenos TDH",
  "Microsoft Data Warehouse",
  "Enterprise Data Warehouse",
  "No DWH in MVP",
];

export const SAMPLE_PROMPTS = [
  "Prepare a phased Temenos proposal for an established bank modernization. Use client name, industry, segments, phase scope, integrations, reporting, security, testing, and cutover details only from the provided questionnaire and knowledge base.",
  "Create a greenfield bank launch proposal with phase 1 and phase 2 expansion. Focus on retail and SME first, then add corporate, treasury, integrations, and regulatory reporting.",
  "Draft a core banking RFP response for a bank moving to AWS with OpenShift optionality, using questionnaire selections to define scope, interfaces, and go-live plan.",
  "Write a Temenos implementation proposal for a retail/SME launch with clear phase-1 product scope, phase-2 digital channels, and TIM governance.",
];

export function getProductsForSegments(segments: string[]): string[] {
  const pool = new Set<string>();
  const selected = segments.length ? segments : Object.keys(PRODUCT_LIBRARY);
  for (const segment of selected) {
    for (const item of PRODUCT_LIBRARY[segment] || []) pool.add(item);
  }
  return Array.from(pool);
}

export function getInterfacesForSegments(segments: string[]): string[] {
  const pool = new Set<string>();
  const selected = segments.length ? segments : Object.keys(REGULATORY_INTERFACE_LIBRARY);
  for (const segment of selected) {
    for (const item of REGULATORY_INTERFACE_LIBRARY[segment] || []) pool.add(item);
  }
  return Array.from(pool);
}

export function getChannelsForSegments(segments: string[]): string[] {
  const pool = new Set<string>();
  const selected = segments.length ? segments : Object.keys(CHANNEL_LIBRARY);
  for (const segment of selected) {
    for (const item of CHANNEL_LIBRARY[segment] || []) pool.add(item);
  }
  return Array.from(pool);
}

export function getModulesForSegments(segments: string[]): string[] {
  const pool = new Set<string>();
  const selected = segments.length ? segments : Object.keys(MODULE_LIBRARY);
  for (const segment of selected) {
    for (const item of MODULE_LIBRARY[segment] || []) pool.add(item);
  }
  return Array.from(pool);
}

export function getPhaseOptions(base: string[], selectedPhase1: string[] = []): string[] {
  return base.filter((item) => !selectedPhase1.includes(item));
}
