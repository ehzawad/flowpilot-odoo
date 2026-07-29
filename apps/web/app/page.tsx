"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { api } from "@/lib/api";
import type {
  ActionProposal,
  AgentRunResponse,
  CaseEvent,
  CaseView,
  DashboardSummary,
  Integration,
  UsageSummary,
} from "@/lib/types";

const currency = (value: string | number, code = "USD") =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: code,
    maximumFractionDigits: 0,
  }).format(Number(value));

const shortDate = (value: string) =>
  new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: string }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

function Stat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <article className="stat-card">
      <p>{label}</p>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function CaseList({
  cases,
  selectedId,
  onSelect,
}: {
  cases: CaseView[];
  selectedId: string | null;
  onSelect: (item: CaseView) => void;
}) {
  return (
    <section className="panel case-list-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Exception queue</span>
          <h2>Operational cases</h2>
        </div>
        <Badge>{cases.length} active</Badge>
      </div>
      <div className="case-list">
        {cases.map((item) => (
          <button
            className={`case-row ${selectedId === item.id ? "case-row-active" : ""}`}
            key={item.id}
            onClick={() => onSelect(item)}
          >
            <span className={`severity-dot severity-${item.severity}`} />
            <span className="case-row-copy">
              <span className="case-row-topline">
                <strong>{item.title}</strong>
                <span>{currency(item.at_risk_value, item.currency)}</span>
              </span>
              <span className="case-row-meta">
                {item.category.replaceAll("_", " ")} · {item.status.replaceAll("_", " ")} · {shortDate(item.updated_at)}
              </span>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function Timeline({ events }: { events: CaseEvent[] }) {
  return (
    <div className="timeline">
      {events.slice().reverse().map((event) => (
        <div className="timeline-item" key={event.id}>
          <span className="timeline-marker" />
          <div>
            <div className="timeline-topline">
              <strong>{event.message || event.event_type}</strong>
              <time>{shortDate(event.created_at)}</time>
            </div>
            <p>{event.event_type.replaceAll(".", " · ")}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function AgentResult({ result }: { result: AgentRunResponse }) {
  return (
    <div className="agent-result">
      <div className="agent-result-heading">
        <div>
          <span className="eyebrow">Evidence-backed analysis</span>
          <h3>{result.output.headline}</h3>
        </div>
        <Badge tone="good">{Math.round(result.output.confidence * 100)}% confidence</Badge>
      </div>
      <p>{result.output.answer}</p>
      <div className="diagnosis-grid">
        <div>
          <h4>Diagnosis</h4>
          <ul>{result.output.diagnosis.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
        <div>
          <h4>Recommended next steps</h4>
          <ol>{result.output.recommended_next_steps.map((item) => <li key={item}>{item}</li>)}</ol>
        </div>
      </div>
      <details>
        <summary>Evidence packet ({result.output.evidence.length})</summary>
        <div className="evidence-list">
          {result.output.evidence.map((item) => (
            <article key={`${item.source_type}:${item.source_id}`}>
              <div><Badge>{item.source_type}</Badge><strong>{item.title}</strong></div>
              <p>{item.excerpt}</p>
            </article>
          ))}
        </div>
      </details>
      <div className="run-meta">
        Model: {result.model} · Tool calls: {result.usage.tool_calls ?? 0} · Latency: {result.usage.latency_ms ?? 0} ms
      </div>
    </div>
  );
}

function ApprovalCard({
  action,
  busy,
  onDecision,
}: {
  action: ActionProposal;
  busy: boolean;
  onDecision: (action: ActionProposal, decision: "approve" | "reject") => void;
}) {
  return (
    <article className="approval-card">
      <div className="approval-card-heading">
        <div>
          <Badge tone={action.risk_level === "high" ? "warn" : "neutral"}>{action.risk_level} risk</Badge>
          <h3>{action.title}</h3>
        </div>
        <code>{action.tool_name}</code>
      </div>
      <p>{action.rationale}</p>
      <dl>
        <div><dt>Target</dt><dd>{action.target}</dd></div>
        <div><dt>Expires</dt><dd>{shortDate(action.expires_at)}</dd></div>
        <div><dt>Payload hash</dt><dd><code>{action.payload_hash.slice(0, 16)}…</code></dd></div>
      </dl>
      <pre>{JSON.stringify(action.payload_json, null, 2)}</pre>
      <div className="approval-actions">
        <button className="button button-secondary" disabled={busy} onClick={() => onDecision(action, "reject")}>Reject</button>
        <button className="button button-primary" disabled={busy} onClick={() => onDecision(action, "approve")}>{busy ? "Recording…" : "Approve exact payload"}</button>
      </div>
    </article>
  );
}

export default function OperationsConsole() {
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [cases, setCases] = useState<CaseView[]>([]);
  const [approvals, setApprovals] = useState<ActionProposal[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [selected, setSelected] = useState<CaseView | null>(null);
  const [events, setEvents] = useState<CaseEvent[]>([]);
  const [agentResult, setAgentResult] = useState<AgentRunResponse | null>(null);
  const [message, setMessage] = useState("Investigate this exception, cite the evidence, and propose the safest next action.");
  const [loading, setLoading] = useState(true);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentPhase, setAgentPhase] = useState<string | null>(null);
  const [decisionBusy, setDecisionBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<"case" | "approvals">("case");

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [nextDashboard, nextCases, nextApprovals, nextIntegrations, nextUsage] = await Promise.all([
        api.dashboard(), api.cases(), api.approvals(), api.integrations(), api.usage(),
      ]);
      setDashboard(nextDashboard);
      setCases(nextCases);
      setApprovals(nextApprovals);
      setIntegrations(nextIntegrations);
      setUsage(nextUsage);
      setSelected((current) => nextCases.find((item) => item.id === current?.id) ?? nextCases[0] ?? null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load FlowPilot");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!selected) { setEvents([]); return; }
    void api.events(selected.id).then(setEvents).catch((nextError) => setError(String(nextError)));
  }, [selected]);

  const selectedApprovals = useMemo(
    () => approvals.filter((item) => item.case_id === selected?.id),
    [approvals, selected],
  );

  async function submitAgent(event: FormEvent) {
    event.preventDefault();
    if (!selected || !message.trim()) return;
    setAgentBusy(true);
    setAgentPhase("Queueing durable investigation…");
    setError(null);
    try {
      const clientRequestId = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}`;
      let job = await api.enqueueAgent(selected.id, message.trim(), clientRequestId);
      setAgentPhase(`Job ${job.state}; waiting for a worker…`);

      for (let attempt = 0; attempt < 180 && !["succeeded", "dead"].includes(job.state); attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        job = await api.job(job.id);
        setAgentPhase(`Job ${job.state} · attempt ${job.attempts}/${job.max_attempts}`);
      }
      if (job.state === "dead") {
        throw new Error(job.last_error ?? "The investigation job exhausted its retries");
      }
      if (job.state !== "succeeded") {
        throw new Error("The investigation is still running; its durable job can be resumed later");
      }
      const runId = job.result_json.run_id;
      if (typeof runId !== "string") {
        throw new Error("The completed job did not return an agent run identifier");
      }
      const result = await api.agentRun(selected.id, runId);
      setAgentResult(result);
      await refresh();
      setEvents(await api.events(selected.id));
      setAgentPhase("Investigation completed");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Agent run failed");
      setAgentPhase(null);
    } finally {
      setAgentBusy(false);
    }
  }

  async function decide(action: ActionProposal, decision: "approve" | "reject") {
    setDecisionBusy(action.id);
    setError(null);
    try {
      await api.decide(action, decision, decision === "reject" ? "Rejected by operator" : undefined);
      await refresh();
      if (selected) setEvents(await api.events(selected.id));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Decision failed");
    } finally {
      setDecisionBusy(null);
    }
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><span>FP</span><div><strong>FlowPilot</strong><small>Agentic operations</small></div></div>
        <nav>
          <button className={activeView === "case" ? "nav-active" : ""} onClick={() => setActiveView("case")}><span>01</span>Command center</button>
          <button className={activeView === "approvals" ? "nav-active" : ""} onClick={() => setActiveView("approvals")}><span>02</span>Approval queue <b>{approvals.length}</b></button>
        </nav>
        <div className="sidebar-section">
          <p>Connected systems</p>
          {integrations.map((integration) => (
            <div className="integration" key={integration.id}>
              <span className={`connection-dot connection-${integration.status}`} />
              <div><strong>{integration.display_name}</strong><small>{integration.status.replaceAll("_", " ")}</small></div>
            </div>
          ))}
        </div>
        <div className="operator-card"><span>MC</span><div><strong>Maya Chen</strong><small>Operations approver</small></div></div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div><span className="eyebrow">Northstar Distribution · Odoo 19</span><h1>{activeView === "case" ? "Operations command center" : "Human approval queue"}</h1></div>
          <button className="button button-ghost" onClick={() => void refresh()}>Refresh data</button>
        </header>

        {error && <div className="error-banner"><strong>FlowPilot could not complete the request.</strong><span>{error}</span></div>}
        {loading ? <div className="loading-panel">Loading the operational evidence graph…</div> : null}

        {!loading && activeView === "case" && dashboard && (
          <>
            <section className="stats-grid">
              <Stat label="At-risk value" value={currency(dashboard.at_risk_value, dashboard.currency)} detail="Across active exceptions" />
              <Stat label="Open cases" value={`${dashboard.open_cases}`} detail={`${dashboard.critical_cases} critical`} />
              <Stat label="Pending approvals" value={`${dashboard.pending_approvals}`} detail="No mutation runs without approval" />
              <Stat label="Agent cost" value={currency(usage?.cost_usd ?? 0)} detail={`${usage?.agent_runs ?? 0} completed investigations`} />
            </section>

            <section className="console-grid">
              <CaseList cases={cases} selectedId={selected?.id ?? null} onSelect={(item) => { setSelected(item); setAgentResult(null); }} />
              <section className="panel case-detail-panel">
                {selected ? (
                  <>
                    <div className="case-hero">
                      <div><div className="case-badges"><Badge tone={selected.severity === "high" ? "warn" : "neutral"}>{selected.severity}</Badge><Badge>{selected.status.replaceAll("_", " ")}</Badge></div><h2>{selected.title}</h2><p>{selected.summary}</p></div>
                      <div className="risk-value"><span>Value at risk</span><strong>{currency(selected.at_risk_value, selected.currency)}</strong><small>{selected.external_ref}</small></div>
                    </div>

                    <div className="detail-tabs"><button className="tab-active">Investigation</button><span>{events.length} timeline events</span></div>
                    <form className="agent-composer" onSubmit={submitAgent}>
                      <label htmlFor="agent-message">Ask the operations agent</label>
                      <textarea id="agent-message" value={message} onChange={(event) => setMessage(event.target.value)} rows={3} />
                      <div><span>Read-only Odoo MCP · tenant RAG · exact-payload approvals</span><button className="button button-primary" disabled={agentBusy}>{agentBusy ? agentPhase ?? "Investigating…" : "Run durable investigation"}</button></div>
                    </form>
                    {agentResult && <AgentResult result={agentResult} />}
                    {selectedApprovals.length > 0 && <div className="inline-approval-callout"><div><strong>{selectedApprovals.length} action proposal pending</strong><span>The payload is immutable after approval.</span></div><button className="button button-secondary" onClick={() => setActiveView("approvals")}>Review proposal</button></div>}
                    <section className="timeline-section"><div className="panel-heading"><div><span className="eyebrow">Durable event log</span><h3>Case timeline</h3></div></div><Timeline events={events} /></section>
                  </>
                ) : <p>No cases found.</p>}
              </section>
            </section>
          </>
        )}

        {!loading && activeView === "approvals" && (
          <section className="approvals-layout">
            <div className="approvals-intro"><span className="eyebrow">Control plane</span><h2>Approve the operation, not the prose</h2><p>Every decision is bound to the tenant, case, tool, target, complete payload, and expiration. A worker revalidates the signature before touching Odoo.</p></div>
            {approvals.length ? approvals.map((action) => <ApprovalCard key={action.id} action={action} busy={decisionBusy === action.id} onDecision={decide} />) : <div className="empty-state"><strong>No decisions are waiting.</strong><p>New action proposals appear here after an investigation.</p></div>}
          </section>
        )}
      </div>
    </main>
  );
}
