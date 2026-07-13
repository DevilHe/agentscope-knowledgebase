import { CheckCircleOutlined, LoadingOutlined } from "@ant-design/icons";
import type { ToolStep } from "../types";

type ToolProgressProps = {
  steps: ToolStep[];
  compact?: boolean;
};

function isDone(step: ToolStep) {
  return step.phase === "end" && step.status !== "error";
}

function isError(step: ToolStep) {
  return step.phase === "end" && step.status === "error";
}

export default function ToolProgress({ steps, compact = false }: ToolProgressProps) {
  if (!steps.length) return null;

  return (
    <div className={`${compact ? "mb-2" : "py-1"} space-y-1`}>
      {steps.map((step) => {
        const done = isDone(step);
        const error = isError(step);
        const running = !done && !error;

        return (
          <div
            key={step.tool_call_id}
            className={`flex items-center gap-2 ${compact ? "text-xs" : "text-sm"} text-neutral-500`}
          >
            {done ? (
              <CheckCircleOutlined className="text-green-500" />
            ) : (
              <LoadingOutlined spin className={error ? "text-red-400" : "text-blue-500"} />
            )}
            <span>
              {step.label}
              {running && "中…"}
              {done && "完成"}
              {error && "失败"}
            </span>
          </div>
        );
      })}
    </div>
  );
}
