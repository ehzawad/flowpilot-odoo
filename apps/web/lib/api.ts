import type {
  ActionProposal,
  AgentRunResponse,
  CaseEvent,
  CaseView,
  DashboardSummary,
  Integration,
  Job,
  UsageSummary,
} from "./types";

const base = "/api/flowpilot";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep the status line when the upstream returned no JSON body.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const api = {
  dashboard: () => request<DashboardSummary>("/dashboard"),
  cases: () => request<CaseView[]>("/cases"),
  events: (caseId: string) => request<CaseEvent[]>(`/cases/${caseId}/events`),
  approvals: () => request<ActionProposal[]>("/approvals"),
  integrations: () => request<Integration[]>("/integrations"),
  usage: () => request<UsageSummary>("/usage"),
  enqueueAgent: (caseId: string, message: string, clientRequestId: string) =>
    request<Job>(`/cases/${caseId}/investigations`, {
      method: "POST",
      body: JSON.stringify({ message, client_request_id: clientRequestId }),
    }),
  job: (jobId: string) => request<Job>(`/jobs/${jobId}`),
  agentRun: (caseId: string, runId: string) =>
    request<AgentRunResponse>(`/cases/${caseId}/agent-runs/${runId}`),
  decide: (action: ActionProposal, decision: "approve" | "reject", reason?: string) =>
    request<{ action: ActionProposal; execution_job_id?: string | null }>(
      `/actions/${action.id}/decision`,
      {
        method: "POST",
        body: JSON.stringify({
          decision,
          expected_payload_hash: action.payload_hash,
          reason,
        }),
      },
    ),
};
