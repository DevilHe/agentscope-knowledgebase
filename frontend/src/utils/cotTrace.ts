import type { CotTrace } from "../types";

function truncate(text: string, limit = 80) {
  const t = text.trim().replace(/\n/g, " ");
  if (t.length <= limit) return t;
  return `${t.slice(0, limit - 3)}...`;
}

export function buildInitialCotTrace(question: string): CotTrace {
  return {
    steps: [
      {
        id: "analyze",
        phase: "analyze",
        kind: "analyze",
        text: `分析问题：${truncate(question)}`,
        icon: "analyze",
        status: "running",
      },
    ],
    finished: false,
    startedAt: Date.now(),
  };
}

export function finalizeCotTrace(
  trace: CotTrace,
  durationMs?: number,
  options?: { keepGenerateRunning?: boolean }
): CotTrace {
  const keepGenerateRunning = Boolean(options?.keepGenerateRunning);
  const steps = trace.steps.map((step) => {
    if (step.status === "error") return step;
    if (
      keepGenerateRunning &&
      step.status === "running" &&
      (step.phase === "generate" || step.kind === "generate")
    ) {
      return step;
    }
    if (step.status === "running" || !step.status) {
      return { ...step, status: "done" as const };
    }
    return step;
  });
  const resolvedDuration =
    durationMs ??
    trace.durationMs ??
    (trace.startedAt ? Math.max(1, Date.now() - trace.startedAt) : undefined);

  if (
    trace.finished &&
    steps.every((s) => s.status === "done" || s.status === "error") &&
    trace.durationMs === resolvedDuration
  ) {
    return trace;
  }

  return {
    ...trace,
    finished: true,
    durationMs: resolvedDuration,
    steps,
  };
}
