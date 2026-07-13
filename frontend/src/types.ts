export interface SourceDoc {
  content: string;
  source: string;
  score: number;
  channel?: string;
  doc_id?: string;
  point_id?: string;
  chunk_index?: number;
  total_chunks?: number;
  page?: number | null;
  key?: string;
}

export interface CotStep {
  id: string;
  phase?: "analyze" | "plan" | "execute" | "generate";
  kind: "analyze" | "plan" | "execute" | "generate" | "reasoning" | "tool" | "generating";
  text: string;
  tool?: string;
  icon?: string;
  detail?: string | null;
  status?: "running" | "done" | "error";
}

export interface CotTrace {
  steps: CotStep[];
  durationMs?: number;
  finished: boolean;
  startedAt?: number;
}

export interface ToolStep {
  tool_call_id: string;
  tool: string;
  label: string;
  phase: "start" | "end";
  status?: string;
}

export interface ChatItem {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceDoc[];
  show_sources?: boolean;
  streaming?: boolean;
  cot?: CotTrace;
}

export interface SessionItem {
  id: string;
  title: string;
  created_at?: string;
  updated_at?: string;
}

export interface DocumentItem {
  id: string;
  filename: string;
  knowledge_base: string;
  department_id?: string | null;
  department_name?: string | null;
  visibility?: string;
  visibility_label?: string;
  chunk_count: number;
  status: string;
  error_message?: string | null;
  version?: number;
  content_hash?: string | null;
  parent_id?: string | null;
  is_latest?: boolean;
  created_at?: string;
}

export interface DepartmentItem {
  id: string;
  name: string;
  slug: string;
}

export interface KnowledgeBaseItem {
  id: string;
  slug: string;
  name: string;
  department_id?: string | null;
  department_name?: string | null;
}

export interface MeProfile {
  id: string;
  username: string;
  role: "admin" | "user";
  is_active: boolean;
  departments: DepartmentItem[];
  knowledge_bases: KnowledgeBaseItem[];
}

export interface AuthUser {
  id: string;
  username: string;
  role: "admin" | "user";
}
