import { encryptPassword } from "../utils/passwordCrypto";

const TOKEN_KEY = "askb_token";
const REFRESH_KEY = "askb_refresh";
const USER_KEY = "askb_user";
const authStorage = sessionStorage;

/** 接口请求超时（毫秒） */
export const API_TIMEOUT_MS = 600_000;

export async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs: number = API_TIMEOUT_MS
): Promise<Response> {
  const timeoutController = new AbortController();
  const externalSignal = init.signal;
  let timedOut = false;

  const timer = window.setTimeout(() => {
    timedOut = true;
    timeoutController.abort();
  }, timeoutMs);

  let signal: AbortSignal = timeoutController.signal;
  let removeBridge: (() => void) | undefined;

  if (externalSignal) {
    if (typeof AbortSignal !== "undefined" && "any" in AbortSignal) {
      signal = AbortSignal.any([timeoutController.signal, externalSignal]);
    } else {
      const bridge = new AbortController();
      const onAbort = () => bridge.abort();
      if (timeoutController.signal.aborted || externalSignal.aborted) {
        bridge.abort();
      } else {
        timeoutController.signal.addEventListener("abort", onAbort);
        externalSignal.addEventListener("abort", onAbort);
        removeBridge = () => {
          timeoutController.signal.removeEventListener("abort", onAbort);
          externalSignal.removeEventListener("abort", onAbort);
        };
      }
      signal = bridge.signal;
    }
  }

  try {
    // 拿到响应头后取消「建连超时」；SSE body 仍受外部 signal 约束
    const res = await fetch(input, { ...init, signal });
    window.clearTimeout(timer);
    return res;
  } catch (error) {
    window.clearTimeout(timer);
    removeBridge?.();
    if (timedOut && !(externalSignal?.aborted)) {
      throw new Error("请求超时，请稍后重试");
    }
    throw error;
  }
}

function clearLegacyAuthStorage() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_KEY);
}

export type StoredUser = { username: string; role: string; department_names?: string[] };
export type CaptchaInfo = { captcha_id: string; image: string };
export type AuditLogItem = {
  id: string;
  user_id: string | null;
  username: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  detail: Record<string, unknown> | null;
  ip_address: string | null;
  os: string | null;
  browser: string | null;
  device: string | null;
  status: string;
  created_at: string | null;
};
export type UserItem = {
  id: string;
  username: string;
  role: string;
  is_active: boolean;
  failed_login_attempts: number;
  locked_until: string | null;
  created_at: string | null;
  department_ids?: string[];
  department_names?: string[];
};

export function getToken(): string | null {
  return authStorage.getItem(TOKEN_KEY);
}

function getRefreshToken(): string | null {
  return authStorage.getItem(REFRESH_KEY);
}

export function setAuth(
  accessToken: string,
  user: StoredUser,
  refreshToken?: string
) {
  clearLegacyAuthStorage();
  authStorage.setItem(TOKEN_KEY, accessToken);
  authStorage.setItem(USER_KEY, JSON.stringify(user));
  if (refreshToken) authStorage.setItem(REFRESH_KEY, refreshToken);
}

export function getStoredUser(): StoredUser | null {
  const raw = authStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredUser;
  } catch {
    clearAuth();
    return null;
  }
}

export function updateStoredUser(patch: Partial<StoredUser>) {
  const user = getStoredUser();
  if (!user) return;
  authStorage.setItem(USER_KEY, JSON.stringify({ ...user, ...patch }));
}

export function clearAuth() {
  clearLegacyAuthStorage();
  authStorage.removeItem(TOKEN_KEY);
  authStorage.removeItem(REFRESH_KEY);
  authStorage.removeItem(USER_KEY);
}

async function parseError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const data = JSON.parse(text);
    if (typeof data.detail === "string") return data.detail;
    return text || `HTTP ${res.status}`;
  } catch {
    return text || `HTTP ${res.status}`;
  }
}

let refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const res = await fetchWithTimeout("/api/auth/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) return false;
        const data = await res.json();
        setAuth(
          data.access_token,
          {
            username: data.username,
            role: data.role,
            department_names: data.department_names || [],
          },
          data.refresh_token
        );
        return true;
      } catch {
        return false;
      } finally {
        refreshPromise = null;
      }
    })();
  }
  return refreshPromise;
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const doFetch = async () => {
    const headers = new Headers(init.headers);
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    return fetchWithTimeout(path, { ...init, headers });
  };

  let res = await doFetch();
  if (res.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) res = await doFetch();
  }

  if (res.status === 401) {
    clearAuth();
    window.location.href = "/login";
    throw new Error("未登录");
  }
  if (!res.ok) throw new Error(await parseError(res));
  if (res.status === 204) return null;
  return res.json();
}

function dedupeRequest<T>(store: { current: Promise<T> | null }, fn: () => Promise<T>): Promise<T> {
  if (!store.current) {
    store.current = fn().finally(() => {
      store.current = null;
    });
  }
  return store.current;
}

const sessionsRequest: { current: Promise<unknown> | null } = { current: null };

export async function fetchCaptcha(): Promise<CaptchaInfo> {
  // 不走 dedupe：刷新必须拿到新验证码；带时间戳避免中间层缓存旧 captcha_id
  const res = await fetchWithTimeout(`/api/auth/captcha?t=${Date.now()}`, {
    method: "GET",
    headers: {
      "Cache-Control": "no-cache",
      Pragma: "no-cache",
    },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function login(
  username: string,
  password: string,
  captchaId: string,
  captchaAnswer: string
) {
  const encryptedPassword = await encryptPassword(password);
  const res = await fetchWithTimeout("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username,
      password: encryptedPassword,
      captcha_id: captchaId,
      captcha_answer: captchaAnswer,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  setAuth(
    data.access_token,
    {
      username: data.username,
      role: data.role,
      department_names: data.department_names || [],
    },
    data.refresh_token
  );
  return data;
}

export async function fetchPublicDepartments() {
  return fetchWithTimeout("/api/org/departments/public").then(async (res) => {
    if (!res.ok) throw new Error(await parseError(res));
    return res.json() as Promise<{ items: { id: string; name: string; slug: string }[] }>;
  });
}

export async function register(
  username: string,
  password: string,
  captchaId: string,
  captchaAnswer: string,
  departmentId: string
) {
  const encryptedPassword = await encryptPassword(password);
  const res = await fetchWithTimeout("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username,
      password: encryptedPassword,
      captcha_id: captchaId,
      captcha_answer: captchaAnswer,
      department_id: departmentId,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function logout() {
  const refreshToken = getRefreshToken();
  const token = getToken();
  try {
    await fetchWithTimeout("/api/auth/logout", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } catch {
    // ignore logout errors
  } finally {
    clearAuth();
  }
}

export async function changePassword(oldPassword: string, newPassword: string) {
  const [encryptedOld, encryptedNew] = await Promise.all([
    encryptPassword(oldPassword),
    encryptPassword(newPassword),
  ]);
  return apiFetch("/api/auth/change-password", {
    method: "POST",
    body: JSON.stringify({
      old_password: encryptedOld,
      new_password: encryptedNew,
    }),
  });
}

export async function fetchMe() {
  return apiFetch("/api/auth/me");
}

export async function fetchDepartments() {
  return apiFetch("/api/org/departments") as Promise<{ items: { id: string; name: string; slug: string }[] }>;
}

export async function fetchKnowledgeBases() {
  return apiFetch("/api/org/knowledge-bases") as Promise<{
    items: {
      id: string;
      slug: string;
      name: string;
      department_id?: string | null;
      department_name?: string | null;
    }[];
  }>;
}

export async function fetchUsers() {
  return apiFetch("/api/auth/users") as Promise<UserItem[]>;
}

export async function createUser(
  username: string,
  password: string,
  role: string,
  departmentIds: string[] = []
) {
  const encryptedPassword = await encryptPassword(password);
  return apiFetch("/api/auth/users", {
    method: "POST",
    body: JSON.stringify({ username, password: encryptedPassword, role, department_ids: departmentIds }),
  });
}

export async function updateUser(
  userId: string,
  payload: { is_active?: boolean; role?: string; department_ids?: string[] }
) {
  return apiFetch(`/api/auth/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function resetUserPassword(userId: string, newPassword: string) {
  const encryptedPassword = await encryptPassword(newPassword);
  return apiFetch(`/api/auth/users/${userId}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ new_password: encryptedPassword }),
  });
}

export async function fetchSessions() {
  return dedupeRequest(sessionsRequest, () => apiFetch("/api/sessions"));
}

export async function fetchSessionMessages(sessionId: string) {
  return apiFetch(`/api/sessions/${sessionId}/messages`);
}

export async function createSession() {
  return apiFetch("/api/sessions", { method: "POST" });
}

export async function deleteSession(sessionId: string) {
  return apiFetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
}

export async function fetchDocuments() {
  return apiFetch("/api/admin/documents");
}

export async function uploadDocument(
  file: File,
  options?: {
    knowledge_base?: string;
    department_id?: string;
    visibility?: string;
  }
) {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams();
  if (options?.knowledge_base) params.set("knowledge_base", options.knowledge_base);
  if (options?.department_id) params.set("department_id", options.department_id);
  if (options?.visibility) params.set("visibility", options.visibility);
  const qs = params.toString();
  return apiFetch(`/api/admin/documents/upload${qs ? `?${qs}` : ""}`, { method: "POST", body: form });
}

export async function pollTask(taskId: string) {
  return apiFetch(`/api/admin/documents/tasks/${taskId}`);
}

export async function updateDocument(
  docId: string,
  payload: { knowledge_base?: string; visibility?: string }
) {
  return apiFetch(`/api/admin/documents/${docId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteDocument(docId: string) {
  return apiFetch(`/api/admin/documents/${docId}`, { method: "DELETE" });
}

export async function fetchAuditLogs(params: {
  page?: number;
  page_size?: number;
  action?: string;
  username?: string;
  status?: string;
}) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", String(params.page));
  if (params.page_size) query.set("page_size", String(params.page_size));
  if (params.action) query.set("action", params.action);
  if (params.username) query.set("username", params.username);
  if (params.status) query.set("status", params.status);
  const qs = query.toString();
  return apiFetch(`/api/admin/audit-logs${qs ? `?${qs}` : ""}`) as Promise<{
    items: AuditLogItem[];
    total: number;
    page: number;
    page_size: number;
  }>;
}

export async function fetchAuditActions() {
  return apiFetch("/api/admin/audit-logs/actions") as Promise<{
    items: { value: string; label: string }[];
  }>;
}
