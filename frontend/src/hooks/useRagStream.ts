import { useCallback, useEffect, useRef, useState } from "react";
import { fetchWithTimeout, getToken } from "../api/client";
import type { CotStep, CotTrace, SourceDoc, ToolStep } from "../types";
import { buildInitialCotTrace, finalizeCotTrace } from "../utils/cotTrace";

const EMPTY_COT: CotTrace = { steps: [], finished: false };

type SourcesPayload = {
  show_sources?: boolean;
  items?: SourceDoc[];
};

function applySourcesPayload(
  payload: SourcesPayload | SourceDoc[],
  setSources: (items: SourceDoc[]) => void,
  setShowSources: (show: boolean) => void
) {
  if (Array.isArray(payload)) {
    setSources(payload);
    setShowSources(payload.length > 0);
    return;
  }
  setSources(payload.items || []);
  setShowSources(Boolean(payload.show_sources));
}

function parseSseBlock(block: string): { event: string; data: string } | null {
  if (!block.trim()) return null;
  let event = "message";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trimStart();
  }
  return { event, data };
}

function upsertCotStep(steps: CotStep[], incoming: CotStep): CotStep[] {
  const idx = steps.findIndex((s) => s.id === incoming.id);
  if (idx < 0) return [...steps, incoming];
  const next = [...steps];
  next[idx] = { ...next[idx], ...incoming };
  return next;
}

function upsertToolStep(steps: ToolStep[], incoming: ToolStep): ToolStep[] {
  const idx = steps.findIndex((s) => s.tool_call_id === incoming.tool_call_id);
  if (idx < 0) return [...steps, incoming];
  const next = [...steps];
  next[idx] = { ...next[idx], ...incoming };
  return next;
}

export function useRagStream() {
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<SourceDoc[]>([]);
  const [showSources, setShowSources] = useState(false);
  const [toolSteps, setToolSteps] = useState<ToolStep[]>([]);
  const [cotTrace, setCotTrace] = useState<CotTrace>(EMPTY_COT);
  const [loading, setLoading] = useState(false);
  const [intent, setIntent] = useState<"rag" | "general" | null>(null);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!loading) {
      setCotTrace((prev) => (prev.steps.length ? finalizeCotTrace(prev) : prev));
    }
  }, [loading]);

  const ask = useCallback(async (question: string, currentSessionId?: string) => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    setLoading(true);
    setAnswer("");
    setSources([]);
    setShowSources(false);
    setToolSteps([]);
    setCotTrace(buildInitialCotTrace(question));
    setIntent(null);

    const token = getToken();
    const res = await fetchWithTimeout("/api/chat/rag", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        question,
        session_id: currentSessionId ?? sessionId,
      }),
      signal: abortRef.current.signal,
    });

    if (!res.ok || !res.body) {
      setLoading(false);
      throw new Error(`请求失败: ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const handleEvent = (event: string, data: string) => {
      if (event === "intent") {
        const parsed = JSON.parse(data);
        if (parsed.intent === "rag" || parsed.intent === "general") setIntent(parsed.intent);
      }
      if (event === "sources") {
        applySourcesPayload(JSON.parse(data), setSources, setShowSources);
      }
      if (event === "tool") {
        const parsed = JSON.parse(data) as ToolStep;
        setToolSteps((prev) => upsertToolStep(prev, parsed));
      }
      if (event === "cot") {
        const parsed = JSON.parse(data) as {
          action: "add" | "update" | "finish" | "remove" | "unfinish";
          step?: CotStep;
          step_id?: string;
          duration_ms?: number;
        };
        if (parsed.action === "remove" && parsed.step_id) {
          setCotTrace((prev) => ({
            ...prev,
            steps: prev.steps.filter((s) => s.id !== parsed.step_id),
          }));
        }
        if (parsed.action === "unfinish") {
          setCotTrace((prev) => ({
            ...prev,
            finished: false,
            durationMs: undefined,
          }));
        }
        if (parsed.action === "add" && parsed.step) {
          const step = parsed.step;
          setCotTrace((prev) => ({
            ...prev,
            steps: upsertCotStep(prev.steps, step),
          }));
        }
        if (parsed.action === "update" && parsed.step) {
          const step = parsed.step;
          setCotTrace((prev) => ({
            ...prev,
            steps: upsertCotStep(prev.steps, step),
          }));
        }
        if (parsed.action === "finish") {
          setCotTrace((prev) =>
            finalizeCotTrace(prev, parsed.duration_ms, { keepGenerateRunning: true })
          );
        }
      }
      if (event === "token") {
        const { delta } = JSON.parse(data);
        setAnswer((prev) => prev + delta);
      }
      if (event === "done") {
        const parsed = JSON.parse(data);
        if (parsed.session_id) setSessionId(parsed.session_id);
        if (typeof parsed.show_sources === "boolean") {
          setShowSources(parsed.show_sources);
        }
        setCotTrace((prev) => finalizeCotTrace(prev));
        setLoading(false);
      }
      if (event === "error") {
        const parsed = JSON.parse(data);
        setLoading(false);
        throw new Error(parsed.message || "请求被拦截");
      }
    };

    const flushBuffer = () => {
      buffer = buffer.replace(/\r\n/g, "\n");
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const parsed = parseSseBlock(block);
        if (parsed) handleEvent(parsed.event, parsed.data);
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (value) buffer += decoder.decode(value, { stream: true });
      flushBuffer();
      if (done) break;
    }

    if (buffer.trim()) {
      const parsed = parseSseBlock(buffer);
      if (parsed) handleEvent(parsed.event, parsed.data);
    }
    setCotTrace((prev) => finalizeCotTrace(prev));
    setLoading(false);
  }, [sessionId]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setLoading(false);
  }, []);

  const reset = useCallback(() => {
    stop();
    setAnswer("");
    setSources([]);
    setShowSources(false);
    setToolSteps([]);
    setCotTrace(EMPTY_COT);
    setIntent(null);
    setSessionId(undefined);
  }, [stop]);

  const setActiveSession = useCallback((id: string | undefined) => {
    setSessionId(id);
    setAnswer("");
    setSources([]);
    setShowSources(false);
    setToolSteps([]);
    setCotTrace(EMPTY_COT);
    setIntent(null);
  }, []);

  return {
    answer,
    sources,
    showSources,
    toolSteps,
    cotTrace,
    loading,
    intent,
    sessionId,
    ask,
    stop,
    reset,
    setActiveSession,
  };
}
