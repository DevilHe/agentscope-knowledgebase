import { Drawer, Tooltip, Typography } from "antd";
import type { SourceDoc } from "../types";
import { splitHighlightText } from "../utils/highlight";

const { Text } = Typography;

function channelLabel(channel?: string) {
  if (channel === "rrf") return "混合(RRF)";
  if (channel === "rerank") return "LLM重排";
  if (channel === "vector") return "向量";
  if (channel === "bm25") return "BM25";
  return channel;
}

function PointIdLabel({ pointId }: { pointId: string }) {
  const label = `Point ${pointId}`;
  return (
    <Tooltip title={label}>
      <Text
        className="!text-xs font-mono text-neutral-500"
        copyable={{
          text: pointId,
          tooltips: ["复制 Point ID", "已复制"],
        }}
      >
        Point {pointId.slice(0, 8)}
      </Text>
    </Tooltip>
  );
}

function formatMeta(s: SourceDoc, index: number) {
  const parts: string[] = [`#${index + 1}`, s.source];
  if (s.page != null) parts.push(`第 ${s.page} 页`);
  if (s.chunk_index != null) {
    const total = s.total_chunks ? `/${s.total_chunks}` : "";
    parts.push(`片段 ${s.chunk_index + 1}${total}`);
  }
  parts.push(`相关度 ${s.score.toFixed(3)}`);
  if (s.channel) parts.push(channelLabel(s.channel) ?? s.channel);
  return parts.join(" · ");
}

function HighlightedContent({ content, query }: { content: string; query?: string }) {
  const parts = splitHighlightText(content, query || "");
  return (
    <p className="!mb-0 mt-2 whitespace-pre-wrap text-sm leading-relaxed text-neutral-700">
      {parts.map((part, i) =>
        part.highlight ? (
          <mark key={i} className="rounded bg-[var(--ant-green)] px-0.5 text-neutral-900">
            {part.text}
          </mark>
        ) : (
          <span key={i}>{part.text}</span>
        )
      )}
    </p>
  );
}

export default function SourceDrawer({
  open,
  sources,
  highlightQuery,
  onClose,
}: {
  open: boolean;
  sources: SourceDoc[];
  highlightQuery?: string;
  onClose: () => void;
}) {
  return (
    <Drawer
      title={`引用来源 (${sources.length})`}
      placement="right"
      size={680}
      open={open}
      onClose={onClose}
    >
      {highlightQuery && (
        <Text type="secondary" className="mb-3 block text-xs">
          高亮词来自提问：{highlightQuery}
        </Text>
      )}
      <div className="space-y-3">
        {sources.map((s, i) => (
          <div key={s.point_id || s.key || `${s.doc_id}-${s.chunk_index}-${i}`} className="rounded-lg border border-neutral-200 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Text type="secondary" className="text-xs">
                {formatMeta(s, i)}
              </Text>
              {s.point_id && <PointIdLabel pointId={s.point_id} />}
            </div>
            <HighlightedContent content={s.content} query={highlightQuery} />
          </div>
        ))}
      </div>
    </Drawer>
  );
}
