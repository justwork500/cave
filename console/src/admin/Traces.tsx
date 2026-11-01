import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Step, Trace } from "../api/types";
import { ErrorBar, when } from "./Page";

const RESULT: Record<Step["result"], string> = {
  ok: "Done", skipped: "Skipped", failed: "Failed", stopped: "Stopped", what_if: "What if",
};
const OUTCOME: Record<Trace["outcome"], string> = {
  finished: "Finished", stopped: "Stopped", failed: "Failed", cancelled: "Cancelled",
  conditions_not_met: "Conditions not met",
};

/** One run, step by step. "restricted" details are shown as the API sends them. */
export function TraceView({ trace }: { trace: Trace }) {
  return (
    <div className="trace">
      <p>
        <strong>{OUTCOME[trace.outcome]}</strong>
        {trace.error && <span className="trace-error"> {trace.error}</span>}
      </p>
      <ol>
        {trace.steps.map((s, i) => (
          <li key={i} className={`step ${s.result}`}>
            <span className={`chip result-${s.result}`}>{RESULT[s.result]}</span>
            <code className="step-path">{s.path}</code>
            <span>{s.detail}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

interface Row {
  id: number;
  started_at: string;
  finished_at: string | null;
  trace: Trace;
}

export function Traces({ kinds, id }: { kinds: string; id: string }) {
  const runs = useQuery({
    queryKey: ["traces", kinds, id],
    queryFn: () => api.get<Row[]>(`/${kinds}/${encodeURIComponent(id)}/traces`),
  });
  return (
    <div className="stack">
      <ErrorBar error={runs.error} />
      {runs.data?.length === 0 && <p className="muted">No runs yet. Use Run, or try it in the Test Center first.</p>}
      {runs.data?.map((r) => (
        <details key={r.id} className="run">
          <summary>
            {when(r.started_at)}: {OUTCOME[r.trace.outcome] ?? "Running"}
          </summary>
          <TraceView trace={r.trace} />
        </details>
      ))}
    </div>
  );
}
