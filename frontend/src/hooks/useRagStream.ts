import { useCallback, useEffect, useRef, useState } from "react";
import { fetchWithTimeout, getToken } from "../api/client";
import type { CotStep, CotTrace, SourceDoc, ToolStep } from "../types";
import { buildInitialCotTrace, finalizeCotTrace } from "../utils/cotTrace";

const EMPTY_COT: CotTrace = { steps: [], finished: false };

export type AskResult =
  | {
      status: "done";
      answer: string;
      sources: SourceDoc[];
      showSources: boolean;
      cotTrace: CotTrace;
      sessionId?: string;
    }
  | { status: "error"; message: string; cotTrace: CotTrace; answer: string }
  | { status: "aborted"; answer: string; cotTrace: CotTrace };

type SourcesPayload = {
  show_sources?: boolean;
  items?: SourceDoc[];
};

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

type ActiveTask = {
  controller: AbortController;
  uiGen: number;
  sessionId?: string;
};

export function useRagStream() {
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<SourceDoc[]>([]);
  const [showSources, setShowSources] = useState(false);
  const [toolSteps, setToolSteps] = useState<ToolStep[]>([]);
  const [cotTrace, setCotTrace] = useState<CotTrace>(EMPTY_COT);
  const [loading, setLoading] = useState(false);
  const [intent, setIntent] = useState<"rag" | "general" | null>(null);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const uiGenerationRef = useRef(0);
  const activeTaskRef = useRef<ActiveTask | null>(null);

  /** 切换会话时解除 UI 绑定，后台请求继续执行 */
  const detach = useCallback(() => {
    uiGenerationRef.current += 1;
    setLoading(false);
    setAnswer("");
    setSources([]);
    setShowSources(false);
    setToolSteps([]);
    setCotTrace(EMPTY_COT);
    setIntent(null);
  }, []);

  /** 用户主动点击停止：取消请求 */
  const stop = useCallback(() => {
    activeTaskRef.current?.controller.abort();
    activeTaskRef.current = null;
    uiGenerationRef.current += 1;
    setLoading(false);
    setCotTrace((prev) => (prev.steps.length ? finalizeCotTrace(prev) : prev));
  }, []);

  const stopIfSession = useCallback(
    (targetSessionId: string) => {
      if (activeTaskRef.current?.sessionId === targetSessionId) {
        stop();
      }
    },
    [stop]
  );

  const ask = useCallback(async (question: string, currentSessionId?: string): Promise<AskResult> => {
    activeTaskRef.current?.controller.abort();

    const uiGen = uiGenerationRef.current;
    const controller = new AbortController();
    const streamSessionId = currentSessionId ?? sessionId;
    activeTaskRef.current = { controller, uiGen, sessionId: streamSessionId };
    const signal = controller.signal;

    let currentAnswer = "";
    let currentSources: SourceDoc[] = [];
    let currentShowSources = false;
    let currentCot = buildInitialCotTrace(question);
    let currentSession = streamSessionId;
    let streamError: string | null = null;
    let completed = false;

    setLoading(true);
    setAnswer("");
    setSources([]);
    setShowSources(false);
    setToolSteps([]);
    setCotTrace(currentCot);
    setIntent(null);

    const isUiAttached = () => uiGenerationRef.current === uiGen;

    const syncIfAttached = () => {
      if (!isUiAttached()) return;
      setAnswer(currentAnswer);
      setSources(currentSources);
      setShowSources(currentShowSources);
      setCotTrace(currentCot);
    };

    const finishSnapshot = (): CotTrace =>
      currentCot.steps.length ? finalizeCotTrace(currentCot) : currentCot;

    try {
      const token = getToken();
      const res = await fetchWithTimeout("/api/chat/rag", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          question,
          session_id: streamSessionId,
        }),
        signal,
      });

      if (signal.aborted) {
        return { status: "aborted", answer: currentAnswer, cotTrace: finishSnapshot() };
      }

      if (!res.ok || !res.body) {
        const message = `请求失败: ${res.status}`;
        currentCot = finishSnapshot();
        syncIfAttached();
        return { status: "error", message, cotTrace: currentCot, answer: currentAnswer };
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const handleEvent = (event: string, data: string) => {
        if (event === "intent") {
          const parsed = JSON.parse(data);
          if (parsed.intent === "rag" || parsed.intent === "general") {
            if (isUiAttached()) setIntent(parsed.intent);
          }
        }
        if (event === "sources") {
          const parsed = JSON.parse(data) as SourcesPayload | SourceDoc[];
          if (Array.isArray(parsed)) {
            currentSources = parsed;
            currentShowSources = parsed.length > 0;
          } else {
            currentSources = parsed.items || [];
            currentShowSources = Boolean(parsed.show_sources);
          }
          syncIfAttached();
        }
        if (event === "tool") {
          const parsed = JSON.parse(data) as ToolStep;
          if (isUiAttached()) {
            setToolSteps((prev) => upsertToolStep(prev, parsed));
          }
        }
        if (event === "cot") {
          const parsed = JSON.parse(data) as {
            action: "add" | "update" | "finish" | "remove" | "unfinish";
            step?: CotStep;
            step_id?: string;
            duration_ms?: number;
          };
          if (parsed.action === "remove" && parsed.step_id) {
            currentCot = {
              ...currentCot,
              steps: currentCot.steps.filter((s) => s.id !== parsed.step_id),
            };
          }
          if (parsed.action === "unfinish") {
            currentCot = {
              ...currentCot,
              finished: false,
              durationMs: undefined,
            };
          }
          if (parsed.action === "add" && parsed.step) {
            currentCot = {
              ...currentCot,
              steps: upsertCotStep(currentCot.steps, parsed.step),
            };
          }
          if (parsed.action === "update" && parsed.step) {
            currentCot = {
              ...currentCot,
              steps: upsertCotStep(currentCot.steps, parsed.step),
            };
          }
          if (parsed.action === "finish") {
            currentCot = finalizeCotTrace(currentCot, parsed.duration_ms, { keepGenerateRunning: true });
          }
          syncIfAttached();
        }
        if (event === "token") {
          const { delta } = JSON.parse(data);
          currentAnswer += delta;
          syncIfAttached();
        }
        if (event === "done") {
          const parsed = JSON.parse(data);
          if (parsed.session_id) {
            currentSession = parsed.session_id;
            if (isUiAttached()) setSessionId(parsed.session_id);
          }
          if (typeof parsed.show_sources === "boolean") {
            currentShowSources = parsed.show_sources;
          }
          currentCot = finalizeCotTrace(currentCot);
          completed = true;
          syncIfAttached();
        }
        if (event === "error") {
          const parsed = JSON.parse(data);
          streamError = parsed.message || "请求被拦截";
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

      try {
        while (true) {
          if (signal.aborted) {
            return { status: "aborted", answer: currentAnswer, cotTrace: finishSnapshot() };
          }

          let done = false;
          let value: Uint8Array | undefined;
          try {
            ({ done, value } = await reader.read());
          } catch (error) {
            if (signal.aborted || (error as Error).name === "AbortError") {
              return { status: "aborted", answer: currentAnswer, cotTrace: finishSnapshot() };
            }
            throw error;
          }

          if (value) buffer += decoder.decode(value, { stream: true });
          flushBuffer();

          if (streamError) {
            currentCot = finishSnapshot();
            syncIfAttached();
            return {
              status: "error",
              message: streamError,
              cotTrace: currentCot,
              answer: currentAnswer,
            };
          }

          if (done) break;
        }
      } finally {
        try {
          await reader.cancel();
        } catch {
          /* ignore */
        }
      }

      if (buffer.trim()) {
        const parsed = parseSseBlock(buffer);
        if (parsed) handleEvent(parsed.event, parsed.data);
      }

      if (streamError) {
        currentCot = finishSnapshot();
        syncIfAttached();
        return {
          status: "error",
          message: streamError,
          cotTrace: currentCot,
          answer: currentAnswer,
        };
      }

      currentCot = finalizeCotTrace(currentCot);
      syncIfAttached();

      if (completed) {
        return {
          status: "done",
          answer: currentAnswer,
          sources: currentSources,
          showSources: currentShowSources,
          cotTrace: currentCot,
          sessionId: currentSession,
        };
      }

      return {
        status: "error",
        message: "连接已断开，请重试",
        cotTrace: currentCot,
        answer: currentAnswer,
      };
    } catch (error) {
      if (signal.aborted || (error as Error).name === "AbortError") {
        return { status: "aborted", answer: currentAnswer, cotTrace: finishSnapshot() };
      }
      return {
        status: "error",
        message: (error as Error).message || "请求失败",
        cotTrace: finishSnapshot(),
        answer: currentAnswer,
      };
    } finally {
      if (isUiAttached()) {
        setLoading(false);
        setCotTrace((prev) => (prev.steps.length ? finalizeCotTrace(prev) : prev));
      }
      if (activeTaskRef.current?.controller === controller) {
        activeTaskRef.current = null;
      }
    }
  }, [sessionId]);

  useEffect(() => {
    if (!loading) {
      setCotTrace((prev) => (prev.steps.length ? finalizeCotTrace(prev) : prev));
    }
  }, [loading]);

  const reset = useCallback(() => {
    detach();
    setSessionId(undefined);
  }, [detach]);

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
    detach,
    stopIfSession,
    reset,
    setActiveSession,
  };
}
