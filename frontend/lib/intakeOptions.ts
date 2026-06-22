export const SEGMENT_OPTIONS = [
  "Retail",
  "SME",
  "Corporate",
  "Treasury",
  "Institutional",
];

export const PRODUCT_PHASE_1_OPTIONS = [
  "Savings Accounts",
  "Current Accounts",
  "Customer Onboarding / KYC",
  "Domestic Payments",
  "ATM Services",
  "AML Screening",
  "Internal Transfers",
  "Teller Operations",
];

export const PRODUCT_PHASE_2_OPTIONS = [
  "International Transfers",
  "Internet Banking",
  "Mobile Banking",
  "Retail Lending",
  "SME Lending",
  "Corporate Lending",
  "Trade Finance",
  "Treasury Products",
  "Cards",
  "POS / Merchant Acquiring",
];

export const REGULATORY_INTERFACE_PHASE_1_OPTIONS = [
  "MMA Reporting",
  "RTGS / ACH",
  "AML / Sanctions Screening",
  "ATM Switch",
  "Identity Verification",
];

export const REGULATORY_INTERFACE_PHASE_2_OPTIONS = [
  "Credit Bureau",
  "Card Schemes",
  "Government e-KYC",
  "SWIFT",
];

export const CHANNEL_PHASE_1_OPTIONS = [
  "Branch / Teller",
  "ATM",
  "Payment Switch",
  "Call Center",
  "CRM",
];

export const CHANNEL_PHASE_2_OPTIONS = [
  "Mobile Banking",
  "Internet Banking",
  "USSD",
  "ERP / Finance",
  "Notifications / AI Chatbots",
];

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

export const METHODOLOGY_OPTIONS = [
  "TIM",
  "TIM + MVP",
  "Agile / Scrum",
  "Prince2 + Scrum",
  "Waterfall with Stage Gates",
];

export const DELIVERY_MODEL_OPTIONS = [
  "Phased MVP",
  "Single Big Bang",
  "Hybrid Phased Rollout",
];

export const SAMPLE_PROMPTS = [
  "Prepare a phased Temenos proposal for an established bank modernization. Use TIM, include segment, product, integration, reporting, security, testing, and cutover details only from the provided questionnaire and knowledge base.",
  "Create a greenfield bank launch proposal with MVP phase 1 and phase 2 expansion. Focus on retail and SME first, then add corporate, treasury, integrations, and regulatory reporting.",
  "Draft a core banking RFP response for a bank moving to AWS with OpenShift optionality, using questionnaire selections to define scope, interfaces, and go-live plan.",
  "Write a Temenos implementation proposal for a retail/SME launch with clear phase-1 product scope, phase-2 digital channels, and TIM governance.",
];
