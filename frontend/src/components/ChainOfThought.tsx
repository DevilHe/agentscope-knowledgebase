import {
  BulbOutlined,
  CaretRightOutlined,
  CheckOutlined,
  CloseOutlined,
  CloudOutlined,
  EditOutlined,
  GlobalOutlined,
  LoadingOutlined,
  PartitionOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { useMemo, useState } from "react";
import type { CotStep, CotTrace } from "../types";

type ChainOfThoughtProps = {
  trace: CotTrace;
  streaming?: boolean;
};

const PHASE_ORDER: Record<string, number> = {
  analyze: 0,
  plan: 1,
  execute: 2,
  generate: 3,
};

function sortSteps(steps: CotStep[]) {
  return steps
    .map((step, index) => ({ step, index }))
    .sort((a, b) => {
      const pa = PHASE_ORDER[a.step.phase || a.step.kind] ?? 99;
      const pb = PHASE_ORDER[b.step.phase || b.step.kind] ?? 99;
      if (pa !== pb) return pa - pb;
      return a.index - b.index;
    })
    .map((item) => item.step);
}

const DONE_ICON_STYLE = { color: "#22c55e" };

function PhaseIcon({ step, traceFinished }: { step: CotStep; traceFinished: boolean }) {
  // 思考结束后仍允许「生成回答」保持 running，直到流结束
  const status =
    step.status === "running"
      ? "running"
      : step.status === "error"
        ? "error"
        : traceFinished || step.status === "done"
          ? "done"
          : step.status;

  if (status === "running") {
    return <LoadingOutlined spin className="mt-0.5 shrink-0 text-[15px] text-blue-500" />;
  }
  if (status === "error") {
    return <CloseOutlined className="mt-0.5 shrink-0 text-[15px] text-red-500" />;
  }
  if (status === "done") {
    return <CheckOutlined className="mt-0.5 shrink-0 text-[15px]" style={DONE_ICON_STYLE} />;
  }

  const muted = "mt-0.5 shrink-0 text-[15px] text-neutral-400";
  if (step.phase === "analyze" || step.icon === "analyze") {
    return <BulbOutlined className={muted} />;
  }
  if (step.phase === "plan" || step.icon === "spark") {
    return <PartitionOutlined className={muted} />;
  }
  if (step.icon === "search") return <SearchOutlined className={muted} />;
  if (step.icon === "globe") return <GlobalOutlined className={muted} />;
  if (step.icon === "weather") return <CloudOutlined className={muted} />;
  if (step.phase === "generate" || step.icon === "generate") {
    return <EditOutlined className={muted} />;
  }
  return <span className="mt-2 block h-1.5 w-1.5 shrink-0 rounded-full bg-neutral-400" />;
}

function formatDuration(ms?: number) {
  if (!ms || ms < 1000) return "1 秒";
  const sec = ms / 1000;
  if (sec < 10) return `${sec.toFixed(1)} 秒`;
  return `${Math.round(sec)} 秒`;
}

export default function ChainOfThought({ trace, streaming = false }: ChainOfThoughtProps) {
  const [expanded, setExpanded] = useState(true);
  const orderedSteps = useMemo(() => sortSteps(trace.steps), [trace.steps]);
  const isActive = !trace.finished && streaming;

  const title = useMemo(() => {
    if (isActive) return "思考中";
    if (trace.finished) return `已思考 (用时 ${formatDuration(trace.durationMs)})`;
    return "思考过程";
  }, [isActive, trace.finished, trace.durationMs]);

  if (!orderedSteps.length) return null;

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full cursor-pointer select-none items-center gap-1.5 py-1 text-left text-sm text-neutral-600"
      >
        {isActive ? (
          <LoadingOutlined spin className="pointer-events-none shrink-0 text-blue-500" />
        ) : (
          <CheckOutlined className="pointer-events-none shrink-0 text-[15px]" style={DONE_ICON_STYLE} />
        )}
        <span className="pointer-events-none font-medium">{title}</span>
        <CaretRightOutlined
          className={`pointer-events-none shrink-0 text-xs text-neutral-400 transition-transform ${expanded ? "rotate-90" : ""}`}
        />
        <span className="min-w-0 flex-1" aria-hidden />
      </button>

      {expanded && (
        <div className="mt-1.5 space-y-2 py-0.5">
          {orderedSteps.map((step) => (
            <div key={step.id} className="flex items-start gap-2.5 text-sm leading-relaxed" style={{ color: "#999" }}>
              <PhaseIcon step={step} traceFinished={trace.finished} />
              <p className="!mb-0 min-w-0 flex-1 whitespace-pre-wrap">{step.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
