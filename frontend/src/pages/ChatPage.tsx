import {
  DeleteOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import {
  Button,
  Layout,
  Popconfirm,
  Typography,
  message,
} from "antd";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  deleteSession,
  fetchMe,
  fetchSessionMessages,
  fetchSessions,
  getStoredUser,
  updateStoredUser,
} from "../api/client";
import ChainOfThought from "../components/ChainOfThought";
import ChatComposer from "../components/ChatComposer";
import MarkdownView from "../components/MarkdownView";
import SourceDrawer from "../components/SourceDrawer";
import UserAccount from "../components/UserAccount";
import { useRagStream } from "../hooks/useRagStream";
import type { ChatItem, SessionItem, SourceDoc } from "../types";
import { buildWelcomeHint } from "../utils/chatWelcomeExample";
import { buildInitialCotTrace, finalizeCotTrace } from "../utils/cotTrace";

const { Sider, Content } = Layout;
const { Text } = Typography;

function pad2(n: number) {
  return n < 10 ? `0${n}` : String(n);
}

function monthLabel(d: Date) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`;
}

/** 侧边栏会话分组：今天 / 昨天 / 一周内 / 一月内 / 超出则按 YYYY-MM */
function groupSessions(sessions: SessionItem[]) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 7);
  const monthAgo = new Date(today);
  monthAgo.setDate(monthAgo.getDate() - 30);

  const fixed: { label: string; items: SessionItem[] }[] = [
    { label: "今天", items: [] },
    { label: "昨天", items: [] },
    { label: "一周内", items: [] },
    { label: "一月内", items: [] },
  ];
  const monthBuckets = new Map<string, SessionItem[]>();

  for (const s of sessions) {
    const t = s.updated_at ? new Date(s.updated_at) : new Date();
    if (t >= today) {
      fixed[0].items.push(s);
    } else if (t >= yesterday) {
      fixed[1].items.push(s);
    } else if (t >= weekAgo) {
      fixed[2].items.push(s);
    } else if (t >= monthAgo) {
      fixed[3].items.push(s);
    } else {
      const key = monthLabel(t);
      const list = monthBuckets.get(key);
      if (list) list.push(s);
      else monthBuckets.set(key, [s]);
    }
  }

  const monthGroups = [...monthBuckets.entries()]
    .sort((a, b) => (a[0] < b[0] ? 1 : a[0] > b[0] ? -1 : 0))
    .map(([label, items]) => ({ label, items }));

  return [...fixed, ...monthGroups].filter((g) => g.items.length > 0);
}

export default function ChatPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatItem[]>([]);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerSources, setDrawerSources] = useState<SourceDoc[]>([]);
  const [drawerHighlightQuery, setDrawerHighlightQuery] = useState("");
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | undefined>(
    () => searchParams.get("session") || undefined
  );
  const [departmentNames, setDepartmentNames] = useState<string[]>(
    () => getStoredUser()?.department_names || []
  );
  const { answer, sources, showSources, cotTrace, loading, sessionId, ask, stop, detach, stopIfSession, reset, setActiveSession } = useRagStream();
  const scrollRef = useRef<HTMLDivElement>(null);
  const initialSessionRef = useRef(searchParams.get("session"));
  const bootstrappedRef = useRef(false);
  const streamingAssistRef = useRef<string | null>(null);
  const loadingSessionRef = useRef<string | null>(null);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, []);

  const loadSessions = useCallback(async () => {
    const data = await fetchSessions();
    setSessions(data.items || []);
    return data.items || [];
  }, []);

  const loadSessionById = useCallback(
    async (id: string) => {
      if (loading) detach();
      loadingSessionRef.current = id;
      streamingAssistRef.current = null;
      setStreamingId(null);
      setActiveSessionId(id);
      setActiveSession(id);
      setSearchParams({ session: id }, { replace: true });
      try {
        const data = await fetchSessionMessages(id);
        if (loadingSessionRef.current !== id) return;
        setMessages(
          (data.items || []).map((m: ChatItem) => ({
            id: m.id,
            role: m.role as "user" | "assistant",
            content: m.content,
            sources: m.sources,
            show_sources: m.show_sources,
            cot: m.cot,
          }))
        );
      } catch (e) {
        if (loadingSessionRef.current === id) {
          message.error((e as Error).message);
        }
      }
    },
    [detach, setActiveSession, setSearchParams]
  );

  useEffect(() => {
    fetchMe()
      .then((me) => {
        const names = (me.departments || [])
          .map((d: { name?: string }) => d.name)
          .filter(Boolean) as string[];
        setDepartmentNames(names);
        updateStoredUser({ department_names: names });
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;

    let cancelled = false;
    const initialSession = initialSessionRef.current;

    (async () => {
      const items = await loadSessions();
      if (cancelled) return;
      if (initialSession && items.some((s: SessionItem) => s.id === initialSession)) {
        await loadSessionById(initialSession);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [loadSessions, loadSessionById]);

  useEffect(() => {
    if (!streamingId || !loading) return;

    setMessages((prev) =>
      prev.map((m) =>
        m.id === streamingId
          ? { ...m, content: answer, streaming: true, cot: cotTrace }
          : m
      )
    );
  }, [streamingId, loading, answer, cotTrace]);

  // 流结束后强制关掉打字光标，避免 loading 已结束但 message.streaming 仍为 true
  useEffect(() => {
    if (loading) return;
    setStreamingId(null);
    streamingAssistRef.current = null;
    setMessages((prev) => {
      if (!prev.some((m) => m.streaming)) return prev;
      return prev.map((m) =>
        m.streaming
          ? {
              ...m,
              streaming: false,
              cot: m.cot && m.cot.steps.length ? finalizeCotTrace(m.cot) : m.cot,
            }
          : m
      );
    });
  }, [loading]);

  const onStop = useCallback(() => {
    const assistId = streamingAssistRef.current;
    stop();
    if (!assistId) return;
    setMessages((prev) =>
      prev.map((m) =>
        m.id === assistId
          ? {
              ...m,
              streaming: false,
              cot: m.cot && m.cot.steps.length ? finalizeCotTrace(m.cot) : m.cot,
            }
          : m
      )
    );
    streamingAssistRef.current = null;
    setStreamingId(null);
  }, [stop]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, answer, cotTrace, loading, scrollToBottom]);

  const onSelectSession = (id: string) => {
    if (id === activeSessionId) return;
    void loadSessionById(id);
  };

  const onNewChat = () => {
    if (messages.length === 0 && !activeSessionId && !loading) return;
    if (loading) detach();
    loadingSessionRef.current = null;
    streamingAssistRef.current = null;
    setStreamingId(null);
    setActiveSessionId(undefined);
    reset();
    setMessages([]);
    setSearchParams({}, { replace: true });
  };

  const onDeleteSession = async (id: string) => {
    try {
      stopIfSession(id);
      await deleteSession(id);
      if (sessionId === id || activeSessionId === id) {
        streamingAssistRef.current = null;
        setStreamingId(null);
        setActiveSessionId(undefined);
        reset();
        setMessages([]);
        setSearchParams({}, { replace: true });
      }
      await loadSessions();
      message.success("已删除对话");
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const onSend = async () => {
    const q = question.trim();
    if (!q || loading) return;
    const assistId = crypto.randomUUID();
    const initialCot = buildInitialCotTrace(q);
    streamingAssistRef.current = assistId;
    setStreamingId(assistId);
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", content: q },
      {
        id: assistId,
        role: "assistant",
        content: "",
        sources: [],
        show_sources: false,
        streaming: true,
        cot: initialCot,
      },
    ]);
    setQuestion("");
    const originSessionId = activeSessionId;
    const result = await ask(q, activeSessionId);
    const attached = streamingAssistRef.current === assistId;

    if (attached) {
      if (result.status === "error") {
        message.error(result.message);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistId
              ? {
                  ...m,
                  content: result.message,
                  streaming: false,
                  cot: result.cotTrace,
                }
              : m
          )
        );
      } else if (result.status === "done") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistId
              ? {
                  ...m,
                  content: result.answer,
                  sources: result.sources,
                  show_sources: result.showSources,
                  streaming: false,
                  cot: result.cotTrace,
                }
              : m
          )
        );
        if (result.sessionId) {
          setActiveSessionId(result.sessionId);
          loadingSessionRef.current = result.sessionId;
          if (searchParams.get("session") !== result.sessionId) {
            setSearchParams({ session: result.sessionId }, { replace: true });
          }
        }
      } else {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistId
              ? {
                  ...m,
                  content: result.answer || m.content,
                  streaming: false,
                  cot: result.cotTrace,
                }
              : m
          )
        );
      }
      streamingAssistRef.current = null;
      setStreamingId(null);
    } else if (result.status === "error" && originSessionId && activeSessionId === originSessionId) {
      message.error(result.message);
    }

    if (result.status === "done") {
      await loadSessions();
      const doneSessionId = result.sessionId;
      if (!attached && doneSessionId && activeSessionId === doneSessionId) {
        await loadSessionById(doneSessionId);
      }
    }
  };

  const findQuestionForAssistant = useCallback(
    (assistantId: string) => {
      const idx = messages.findIndex((m) => m.id === assistantId);
      if (idx <= 0) return "";
      for (let i = idx - 1; i >= 0; i -= 1) {
        if (messages[i].role === "user") return messages[i].content;
      }
      return "";
    },
    [messages]
  );

  const grouped = useMemo(() => groupSessions(sessions), [sessions]);
  const welcomeHint = useMemo(() => buildWelcomeHint(departmentNames), [departmentNames]);

  return (
    <Layout className="h-screen bg-white">
      <Sider width={260} theme="light" className="!bg-neutral-50 border-r border-neutral-200">
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-center gap-1.5 px-4 pb-1 pt-4">
            <img
              src="/avatar.png"
              alt="AI知识库助手"
              className="h-9 w-9 shrink-0 object-contain"
            />
            <span className="text-sm font-semibold text-neutral-800">AI知识库助手</span>
          </div>
          <div className="p-3 pt-2">
            <Button block icon={<PlusOutlined />} onClick={onNewChat}>
              新对话
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-2">
            {grouped.map((g) => (
              <div key={g.label} className="mb-3">
                <Text type="secondary" className="block px-2 py-1 text-xs">
                  {g.label}
                </Text>
                {g.items.map((s) => (
                  <div
                    key={s.id}
                    className={`group mb-0.5 flex items-center rounded-lg ${
                      activeSessionId === s.id ? "bg-neutral-200" : "hover:bg-neutral-100"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => onSelectSession(s.id)}
                      className="min-w-0 flex-1 cursor-pointer truncate px-3 py-2 text-left text-sm text-neutral-700"
                    >
                      {s.title}
                    </button>
                    <Popconfirm
                      title="确认删除该对话？"
                      okText="删除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                      onConfirm={() => onDeleteSession(s.id)}
                    >
                      <Button
                        type="text"
                        size="small"
                        icon={<DeleteOutlined />}
                        aria-label="删除对话"
                        className="mr-1 opacity-0 transition-opacity group-hover:opacity-100"
                      />
                    </Popconfirm>
                  </div>
                ))}
              </div>
            ))}
          </div>
          <div className="border-t border-neutral-200 p-3">
            <UserAccount />
          </div>
        </div>
      </Sider>

      <Layout className="flex min-h-0 flex-1 flex-col bg-white">
        <Content className="flex min-h-0 flex-1 flex-col">
          {messages.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center px-6 pb-6">
              <div className="mb-8 flex flex-col items-center gap-4 px-4 text-center">
                <div className="flex items-center gap-5">
                  <img
                    src="/avatar.png"
                    alt="AI助手"
                    className="h-28 w-28 shrink-0 object-contain"
                  />
                  <span className="text-2xl font-bold">嗨，我是AI知识库助手</span>
                </div>
                <Text type="secondary" className="max-w-xl text-base leading-relaxed">
                  {welcomeHint}
                </Text>
              </div>
              <div className="w-full max-w-3xl">
                <ChatComposer
                  value={question}
                  loading={loading}
                  onChange={setQuestion}
                  onSend={onSend}
                  onStop={onStop}
                />
              </div>
            </div>
          ) : (
            <>
              <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
                <div className="mx-auto max-w-3xl space-y-6">
                  {messages.map((m) => {
                    const isLiveAssist =
                      m.id === streamingId || m.id === streamingAssistRef.current;
                    const liveContent = isLiveAssist ? answer : m.content;
                    const rawCot = isLiveAssist ? cotTrace : m.cot;
                    const liveCot =
                      rawCot && !loading && rawCot.steps.length > 0
                        ? finalizeCotTrace(rawCot)
                        : rawCot;
                    const showCot = Boolean(liveCot && liveCot.steps.length > 0);

                    return (
                    <div key={m.id} className={m.role === "user" ? "flex justify-end" : ""}>
                      <div
                        className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                          m.role === "user"
                            ? "bg-[#4d6bfe] text-white"
                            : "bg-neutral-100 text-neutral-800"
                        }`}
                      >
                        {m.role === "assistant" ? (
                          <>
                            {showCot && liveCot && (
                              <ChainOfThought
                                trace={liveCot}
                                streaming={loading && !liveCot.finished}
                              />
                            )}
                            {liveContent.trim() ? (
                              <MarkdownView
                                content={liveContent}
                                streaming={Boolean(m.streaming && loading && m.id === streamingId)}
                              />
                            ) : null}
                          </>
                        ) : (
                          <span className="whitespace-pre-wrap">{m.content}</span>
                        )}
                        {m.role === "assistant" && !m.streaming && m.show_sources && m.sources && m.sources.length > 0 && (
                          <Button
                            type="link"
                            size="small"
                            className="!px-0 !text-[#4d6bfe]"
                            onClick={() => {
                              setDrawerSources(m.sources!);
                              setDrawerHighlightQuery(findQuestionForAssistant(m.id));
                              setDrawerOpen(true);
                            }}
                          >
                            查看 {m.sources.length} 条引用
                          </Button>
                        )}
                      </div>
                    </div>
                    );
                  })}
                </div>
              </div>
              <div className="px-6 pb-6 pt-2">
                <div className="mx-auto max-w-3xl">
                  <ChatComposer
                    value={question}
                    loading={loading}
                    onChange={setQuestion}
                    onSend={onSend}
                    onStop={onStop}
                  />
                </div>
              </div>
            </>
          )}
        </Content>
      </Layout>

      <SourceDrawer
        open={drawerOpen}
        sources={drawerSources}
        highlightQuery={drawerHighlightQuery}
        onClose={() => setDrawerOpen(false)}
      />
    </Layout>
  );
}
