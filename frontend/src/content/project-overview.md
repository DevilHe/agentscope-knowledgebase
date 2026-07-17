# AI 知识库助手

基于 **LangChain + LangGraph** 的企业级知识库 RAG 系统，支持文档问答、联网搜索、天气查询与多轮对话。

---

## 技术栈

| 层级       | 技术                                                                          |
| ---------- | ----------------------------------------------------------------------------- |
| Agent 框架 | LangGraph ReAct（`tools_condition` 按需检索）+ LangChain Tools                |
| 大语言模型 | 商汤 SenseNova `sensenova-6.7-flash-lite/sensenova-u1-fast/deepseek-v4-flash` |
| 向量嵌入   | Ollama `nomic-embed-text`（768 维）                                           |
| 向量数据库 | Qdrant（自研 dense+sparse hybrid，不用 RAGFlow）                              |
| 全文检索   | Qdrant sparse（与 dense 同 collection 混合）                                  |
| 后端       | FastAPI + SQLAlchemy + Redis                                                  |
| 前端       | React 19 + Vite + Ant Design + Tailwind CSS                                   |
| 运行时     | Python 3.14                                                                   |

---

## 核心要点

### 1. 混合检索 + LLM 重排

- **Qdrant 原生混合检索**（dense 语义向量 + sparse 关键词，单 collection 内 RRF）
- 查询强制 **payload 过滤**：`org_id`（租户）+ `knowledge_base` + `doc_id`（ACL）
- MySQL `document_chunks` **双写保留**（备份/调试，不参与检索）
- 可选 **LLM Rerank**：对 Top-N 候选 chunk 打分重排（因服务器 2C2G 限制，暂不支持 cross-encoder）
- `RETRIEVAL_HYBRID_ENABLED=false` 时仅 dense 向量检索

### 2. 自研入库与分块

- **语义分块**（默认 `CHUNK_STRATEGY=semantic`）：Ollama embedding 合并相邻句/条，单块目标 **512–1024 token**；超长回退固定 token 切
- `CHUNK_STRATEGY=fixed` 时仅按 token 大小与 overlap 切分
- 文档 **版本管理**：同文件内容 hash 相同则跳过重复入库

### 3. 可观测的 Agent 工具调用（按需）

- 支持知识库检索、联网搜索、天气查询等工具
- **按需检索**：ReAct 条件边 — LLM 决定是否调用工具；闲聊不强制 RAG
- 角色白名单控制可用工具；`get_weather` 支持一次传入多城 `cities`
- 前端实时展示 **工具调用进度**（SSE 流式透出 tool / cot 事件）

### 4. 引用溯源与可信度

- 回答附带 **引用来源抽屉**，展示文件名、页码、chunk 定位
- `source_trust` 模块：明确拒答 + Token 重叠校验 + 去重
- 关键词高亮，便于核对原文

### 5. 安全、审计与多部门数据隔离

- JWT 登录 + Refresh Token + 验证码防刷
- **组织 / 部门 / 知识库 / 文档级 ACL**（企业多部门场景）
- 角色权限：管理员（全组织）/ 普通用户（按部门授权）
- **审计日志**：记录操作类型、IP、操作系统、浏览器、设备信息
- 密码传输加密、登录失败锁定、会话级 Token 存储

#### 多部门隔离模型

| 层级   | 说明                                 |
| ------ | ------------------------------------ |
| 组织   | 默认企业租户，所有数据归属同一组织   |
| 部门   | 研发部、产品部、人力行政部等         |
| 知识库 | 全公司共享库 + 各部门专属库          |
| 文档   | 可见范围：全公司 / 本部门 / 仅管理员 |

#### 默认预置数据

| 类型     | 名称                                                               |
| -------- | ------------------------------------------------------------------ |
| 全公司库 | `default`（全公司共享库）                                          |
| 部门库   | `rnd-kb`（研发）、`product-kb`（产品）、`hr-kb`（人力行政）        |
| 默认用户 | `admin` 可访问全部；`user` 归属研发部，可访问 `default` + `rnd-kb` |

#### 鉴权要点

- 聊天时服务端校验知识库访问权，**禁止**客户端越权指定 KB
- 向量检索（Qdrant）按 **可访问 doc_id** 过滤
- 文档列表、上传、删除均走 ACL 过滤
- 用户管理支持分配部门，决定可访问的知识库范围

### 6. 完整的对话体验

- 多会话历史管理（今天 / 昨天 / 一周内 / 一月内 / 更早按 `YYYY-MM` 分组）
- Markdown 流式渲染，代码块语法高亮
- 深度思考指示器与停止生成
- **上下文压缩摘要**：历史超过阈值时，旧轮次由 LLM 压成一条摘要，再保留最近若干条原文送入 Agent

### 7. 本地 RAG 评测体系

- 黄金集驱动的 **recall@k / MRR / keyword_coverage** 指标
- 分阶段对比：vector → bm25 → rrf → final（含 Rerank）
- 可选 full 模式评测生成忠实度与幻觉率

### 8. Agent 治理

- **单用户 Token 配额**：按日估算用量（`USER_TOKEN_QUOTA_DAILY`），与 LLM 调用次数配额并存
- **工具轮次 / 超时**：`AGENT_MAX_TOOL_ROUNDS`、`AGENT_REPLY_TIMEOUT_SECONDS` 限制单轮对话资源消耗
- **熔断保护**：连续失败达阈值后短时拒绝新请求（`AGENT_CIRCUIT_BREAKER_*`）
- **Prompt 版本与灰度**：外置 `app/prompts/prompts.yml`，支持稳定版 + 按用户哈希灰度
- **模型按场景路由**：对话 / Rerank / 降级回退模型可分别配置（`OPENAI_MODEL_CHAT` 等）

---

## 架构概览

```
用户提问
  → FastAPI Chat API（SSE 流式）
    → LangGraph ReAct Agent（条件边按需工具）
      → 工具：知识库检索 / 联网搜索 / 多城天气
      → 混合检索：Qdrant dense+sparse（payload: org_id/kb/doc_id）→ 可选 LLM Rerank
    → 生成回答 + 引用来源
  → React 前端实时渲染
```

---

## 主要功能入口

| 功能     | 说明                                            |
| -------- | ----------------------------------------------- |
| 智能对话 | 基于知识库与工具的 RAG 问答，可按授权切换知识库 |
| 文档管理 | 上传时选择知识库与可见范围，列表按部门 ACL 过滤 |
| 用户管理 | 创建用户、分配部门、启用/禁用、重置密码         |
| 审计日志 | 查看操作记录与客户端环境信息                    |
| 修改密码 | 所有登录用户可自助修改                          |

---

## 检索配置参考

```env
# 是否启用混合检索；false 时仅稠密向量检索
RETRIEVAL_HYBRID_ENABLED=true
# 是否启用 LLM 重排序；true 精度更高但更慢，默认关闭以优先响应速度
RETRIEVAL_RERANK_ENABLED=false
# 混合检索每路召回候选数（Qdrant dense / sparse prefetch）
RETRIEVAL_CANDIDATE_TOP_K=12
# 送入 LLM Rerank 的候选条数上限（仅 RETRIEVAL_RERANK_ENABLED=true 时生效）
RETRIEVAL_RERANK_CANDIDATES=8
# 文档分块（semantic=embedding 语义边界 + 超长 fixed 兜底；fixed=仅固定 token）
# 单块目标 512–1024 token（下限内置，上限=CHUNK_TOKEN_SIZE）
CHUNK_STRATEGY=semantic
CHUNK_TOKEN_SIZE=1024
CHUNK_TOKEN_OVERLAP=154
CHUNK_SEMANTIC_SIMILARITY_THRESHOLD=0.60
# 对话检索最终返回给模型的片段数（引用来源条数上限）
TOP_K=4
```

## Agent 治理配置参考

```env
# 单轮对话工具调用上限
AGENT_MAX_TOOL_ROUNDS=8
# 流式回答总超时（秒）
AGENT_REPLY_TIMEOUT_SECONDS=600
# 熔断：连续失败次数 / 冷却秒数
AGENT_CIRCUIT_BREAKER_FAIL_THRESHOLD=5
AGENT_CIRCUIT_BREAKER_COOLDOWN_SECONDS=120
# 单用户每日 Token 估算配额（0=不限）
USER_TOKEN_QUOTA_DAILY=0
USER_TOKEN_ESTIMATE_CHARS_PER_TOKEN=2.0
# 多轮历史窗口与压缩摘要
HISTORY_MAX_MESSAGES=20
HISTORY_COMPRESS_ENABLED=true
HISTORY_COMPRESS_THRESHOLD=12
HISTORY_KEEP_RECENT=8
# Prompt 稳定版与灰度（文件：backend/app/prompts/prompts.yml）
AGENT_PROMPT_VERSION=v1
AGENT_PROMPT_CANARY_VERSION=v2
AGENT_PROMPT_CANARY_PERCENT=10
# 模型路由（空则使用 OPENAI_MODEL）
OPENAI_MODEL_CHAT=sensenova-6.7-flash-lite
OPENAI_MODEL_RERANK=deepseek-v4-flash
OPENAI_MODEL_FALLBACK=sensenova-u1-fast
```

---

> 更多部署与评测细节请参阅项目根目录 `README.md`，或联系作者：

![联系作者微信](/wechat.jpg)
