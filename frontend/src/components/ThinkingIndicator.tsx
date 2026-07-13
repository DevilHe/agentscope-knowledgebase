import { Spin } from "antd";

type ThinkingIndicatorProps = {
  label?: string;
};

export default function ThinkingIndicator({ label = "正在思考中..." }: ThinkingIndicatorProps) {
  return (
    <div className="flex items-center gap-2 py-1 text-sm text-neutral-500">
      <Spin size="small" />
      <span>{label}</span>
    </div>
  );
}
