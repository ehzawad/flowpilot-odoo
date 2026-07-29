export type DashboardSummary = {
  open_cases: number;
  critical_cases: number;
  pending_approvals: number;
  at_risk_value: string | number;
  currency: string;
};

export type CaseView = {
  id: string;
  organization_id: string;
  title: string;
  summary: string;
  category: string;
  severity: string;
  status: string;
  source: string;
  external_ref: string;
  at_risk_value: string | number;
  currency: string;
  context_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type CaseEvent = {
  id: string;
  case_id: string;
  event_type: string;
  actor_type: string;
  actor_id?: string | null;
  message: string;
  payload_json: Record<string, unknown>;
  created_at: string;
};

export type Evidence = {
  source_type: string;
  source_id: string;
  title: string;
  excerpt: string;
  observed_at?: string | null;
  confidence: number;
  metadata: Record<string, unknown>;
};

export type AgentAnswer = {
  headline: string;
  answer: string;
  diagnosis: string[];
  recommended_next_steps: string[];
  evidence: Evidence[];
  confidence: number;
  requires_human: boolean;
  safety_notes: string[];
};

export type ActionProposal = {
  id: string;
  organization_id: string;
  case_id: string;
  agent_run_id?: string | null;
  tool_name: string;
  title: string;
  rationale: string;
  target: string;
  payload_json: Record<string, unknown>;
  payload_hash: string;
  risk_level: string;
  approval_status: string;
  execution_status: string;
  expires_at: string;
  approved_by?: string | null;
  approved_at?: string | null;
  executed_at?: string | null;
  execution_result_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AgentRunResponse = {
  id: string;
  case_id: string;
  status: string;
  runtime: string;
  model: string;
  trace_id?: string | null;
  output: AgentAnswer;
  actions: ActionProposal[];
  usage: Record<string, number>;
  created_at: string;
};

export type Integration = {
  id: string;
  kind: string;
  display_name: string;
  status: string;
  external_account_id: string;
  last_synced_at?: string | null;
};

export type UsageSummary = {
  agent_runs: number;
  input_tokens: number;
  output_tokens: number;
  tool_calls: number;
  cost_usd: number;
};

export type Job = {
  id: string;
  organization_id: string;
  job_type: string;
  state: string;
  attempts: number;
  max_attempts: number;
  available_at: string;
  last_error?: string | null;
  result_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};
