# AgentScope Knowledge Base

基于 **AgentScope 2.0** 的知识库 RAG 系统：JWT 登录、管理员文档管理、DeepSeek 风格聊天（含历史会话与 Agent 工具调用）。

## 技术栈

- **AgentScope**：LLM（OpenAIChatModel）、Embedding（Ollama）、向量库（QdrantStore）、Agent + Toolkit + 工具权限
- **LLM**：商汤 SenseNova `deepseek-v4-flash`（`https://token.sensenova.cn/v1`）
- **Embedding**：Ollama `nomic-embed-text`（768 维）
- **Agent 工具**：`get_weather`（`ToolBase` + `PermissionEngine` 角色 allow 规则 + HITL 闭环）
- **检索**：Qdrant dense+sparse 原生混合（payload 隔离）+ 可选 LLM Rerank；MySQL `document_chunks` 双写备份
- **文档分块**：默认语义分块（Ollama embedding 合并相邻句/条，单块目标 **512–1024 token**）；超长回退固定 token 切分
- **后端**：FastAPI + MySQL + Redis + Qdrant
- **前端**：React + Vite + Tailwind
- **Python**：3.14

## 配置说明（本地 / Docker 双模式）

| 文件                 | 用途                                         | 是否提交 git    |
| -------------------- | -------------------------------------------- | --------------- |
| `.env`               | API Key、模型名、默认账号密码等**共用配置**  | 否（gitignore） |
| `.env.local`         | **本地开发**连接（127.0.0.1、3307 等）       | 否（gitignore） |
| `.env.example`       | `.env` 模板                                  | 是              |
| `.env.local.example` | `.env.local` 模板                            | 是              |
| `docker-compose.yml` | Docker 部署时 **environment 注入**容器内地址 | 是              |

**原则：**

- 本地调试：`.env` + `.env.local`（后者覆盖连接项）
- Docker 部署：只需 `.env`（密钥与账号）；backend 容器内连接由 compose 的 `environment` 固定，**不读 `.env.local`**

## 默认账号

| 角色   | 用户名 | 权限                     |
| ------ | ------ | ------------------------ |
| 管理员 | admin  | 聊天 + `/admin` 文档管理 |
| 用户   | user   | 仅聊天                   |

账号密码在 `.env` 的 `ADMIN_*` / `USER_*` 中配置（勿写入文档）；backend 启动时会同步写入/更新 MySQL `users` 表。

---

## 一、本地开发（推荐调试流程）

```bash
cd agentscope-knowledgebase

# 1. 初始化（生成 .env + .env.local，启动中间件）
chmod +x scripts/setup-local.sh scripts/pull-ollama-model.sh
./scripts/setup-local.sh

# 2. 编辑 .env 填入 OPENAI_API_KEY（可选 OPENWEATHER_API_KEY）

# 3. 拉 embedding 模型
./scripts/pull-ollama-model.sh

# 4. 终端 A - Backend（需 Python 3.14，推荐 pyenv）
cd backend
pyenv local 3.14.6
python -m venv .venv && source .venv/bin/activate
PIP_PREFER_BINARY=1 pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 5. 终端 B - Frontend
cd frontend && npm install && npm run dev
# http://localhost:5173
```

验证：

```bash
curl http://127.0.0.1:8000/api/health
# {"status":"ok"}
```

### 本地连接一览（写在 `.env.local`）

| 服务     | 地址              |
| -------- | ----------------- |
| MySQL    | `127.0.0.1:3307`  |
| Redis    | `127.0.0.1:6379`  |
| Qdrant   | `127.0.0.1:6333`  |
| Ollama   | `127.0.0.1:11434` |
| 上传目录 | 项目根 `uploads/` |

### 复用 langgraph-rag-standards 中间件

若本机已运行 `langgraph-rag-standards` 的 Docker 中间件（`rag-mysql` / `rag-qdrant` 等），**不必再起**本项目的 `docker-compose.infra.yml`，只需 `.env.local` 指向 `127.0.0.1` 相同端口即可（MySQL/Qdrant/Ollama 配置兼容）。

### Qdrant 向量库查看

浏览器访问 http://127.0.0.1:6333/dashboard#/collections

---

## 二、Docker 全量部署（调试完成后）

```bash
# 1. 确保 .env 已配置 OPENAI_API_KEY（不需要 .env.local）
cp .env.example .env   # 若尚未创建

# 2. 一键部署
chmod +x scripts/deploy-docker.sh scripts/pull-ollama-model.sh
./scripts/deploy-docker.sh

# 或手动
docker compose up -d --build
./scripts/pull-ollama-model.sh
```

访问：

- 前端：http://localhost
- API：http://localhost:8000/api/health

Docker 内 backend 自动使用：

```
mysql:3306 / redis:6379 / qdrant:6333 / ollama:11434 / /app/uploads
```

与本地 `.env.local` **互不干扰**。

---

## 三、仅 Docker 中间件（本地跑代码时）

```bash
docker compose -f docker-compose.infra.yml up -d
docker compose -f docker-compose.infra.yml ps -a
```

---

## 四、RAG 评测（仅本地，不在服务器跑）

评测脚本用于衡量检索召回率、关键词覆盖率，以及（可选）生成答案忠实度。**请在本地开发机执行，不要在 2 核 2G 生产服务器上跑**，尤其避免 `full` 模式（每题约 2 次 LLM 调用，成本高、占资源）。

### 关键步骤速览

```text
① 启动本地中间件（MySQL / Qdrant / Ollama）
② 文档管理上传测试文档（升级后旧文档需重新上传，才有 MySQL chunks）
③ cp eval/golden_set.example.json eval/golden_set.json 并按文档填写用例
④ ./scripts/run_eval.sh  →  查看终端输出或 eval/results/latest.json
⑤ （可选）改 .env 检索开关，重复 ④ 对比纯向量 / 混合 / Rerank
```

| 步骤 | 命令 / 操作 | 产出 |
| ---- | ----------- | ---- |
| 准备环境 | `./scripts/setup-local.sh` + 启动 backend | 中间件就绪 |
| 入库文档 | 前端「文档管理」上传 PDF/Word/TXT/MD | Qdrant 向量 + MySQL chunks |
| 编写黄金集 | 编辑 `eval/golden_set.json` | 测试问题 + 期望关键词/来源 |
| 跑检索评测 | `./scripts/run_eval.sh` | `eval/results/latest.json` |
| 看召回率 | 读报告 `summary.recall@k` 或终端 `[Final Pipeline]` | 0～1，越高越好 |
| 对比方案 | 改 `.env` 后重跑，保存多份 json | `baseline_vector.json` 等 |

### 前置条件

1. **本地中间件已启动**（与日常开发相同）：
   - MySQL `127.0.0.1:3307`
   - Qdrant `127.0.0.1:6333`
   - Ollama `127.0.0.1:11434`（已拉取 `nomic-embed-text`）
2. **`.env` + `.env.local` 已配置**（评测脚本读取与 backend 相同的配置，连接走 `.env.local` 的 `127.0.0.1`）
3. **文档已入库到 hybrid collection**：
   - 在 http://localhost:5173 登录 admin →「文档管理」上传测试文档
   - 向量写入 `standards_hybrid`（dense+sparse）；同时双写 MySQL `document_chunks`（不参与检索，便于备份）
   - 若此前仅有旧 dense-only collection，需**重新上传**文档

### 1. 准备黄金集

```bash
cd agentscope-knowledgebase
cp eval/golden_set.example.json eval/golden_set.json
```

编辑 `eval/golden_set.json`，按实际文档填写用例：

| 字段 | 说明 |
| ---- | ---- |
| `question` | 测试问题 |
| `expected_keywords` | 期望出现在检索 chunk 中的关键词（可选） |
| `expected_sources` | 期望命中的文件名子串，如 `"规范.pdf"`（可选） |
| `expected_answer_keywords` | `full` 模式下期望出现在生成答案中的词（可选） |

两者同时填写时，命中条件为 **来源 AND 关键词**；只填其一则按该项判断。

### 2. 仅检索评测（推荐）

不调用 LLM 生成，只评 retrieval 指标（recall@k、MRR、keyword_coverage），并输出 vector / bm25 / rrf / final 各阶段对比：

```bash
chmod +x scripts/run_eval.sh
./scripts/run_eval.sh
```

或手动指定参数：

```bash
cd backend
source .venv/bin/activate
python -m app.eval.runner \
  --dataset ../eval/golden_set.json \
  --output ../eval/results/latest.json \
  --mode retrieval \
  --top-k 4
```

报告写入 `eval/results/<时间戳>.json`，并复制为 `eval/results/latest.json`（目录已 gitignore）。

### 3. 完整评测（检索 + 生成 + 忠实度）

额外评测答案关键词覆盖率、faithfulness（忠实度）、hallucination_rate（幻觉率）。**每题约 2 次 LLM 调用**，仅本地调试时使用：

```bash
EVAL_MODE=full ./scripts/run_eval.sh
```

### 4. 对比「纯向量 vs 混合检索 vs 混合+Rerank」

在 **本地 `.env`** 中临时修改检索开关，分别跑评测后对比 `eval/results/latest.json` 的 `stage_summary` / `summary`：

| 场景 | `.env` 配置 |
| ---- | ----------- |
| 纯向量 | `RETRIEVAL_HYBRID_ENABLED=false` |
| 混合（BM25 + 向量 + RRF） | `RETRIEVAL_HYBRID_ENABLED=true`<br>`RETRIEVAL_RERANK_ENABLED=false` |
| 混合 + LLM Rerank | `RETRIEVAL_HYBRID_ENABLED=true`<br>`RETRIEVAL_RERANK_ENABLED=true` |

操作示例：

```bash
# 1) 纯向量
# 编辑 .env：RETRIEVAL_HYBRID_ENABLED=false
./scripts/run_eval.sh
cp eval/results/latest.json eval/results/baseline_vector.json

# 2) 混合检索（无 Rerank）
# 编辑 .env：RETRIEVAL_HYBRID_ENABLED=true，RETRIEVAL_RERANK_ENABLED=false
./scripts/run_eval.sh
cp eval/results/latest.json eval/results/hybrid_rrf.json

# 3) 混合 + Rerank
# 编辑 .env：RETRIEVAL_RERANK_ENABLED=true
./scripts/run_eval.sh
cp eval/results/latest.json eval/results/hybrid_rerank.json
```

> **注意**：修改 `.env` 后无需重启 backend 即可跑评测（脚本独立进程读配置）；若同时要验证线上聊天行为，需重启 `uvicorn`。

### 5. 相关配置项（`.env`）

```env
RETRIEVAL_HYBRID_ENABLED=true
RETRIEVAL_RRF_K=60
RETRIEVAL_CANDIDATE_TOP_K=20
RETRIEVAL_RERANK_ENABLED=true
RETRIEVAL_RERANK_CANDIDATES=10
TOP_K=4
```

### 6. 如何看召回率（recall@k）

本项目的「召回率」即指标 **recall@k**（Top-K 命中率），含义是：

> 对每道黄金集问题，在最终检索返回的 **top-k 个 chunk** 中，是否**至少有一个**满足期望条件。

**命中规则**（与 `eval/golden_set.json` 填写方式相关）：

| 黄金集填写 | 判定 |
| ---------- | ---- |
| 只填 `expected_keywords` | 某 chunk **内容**包含其中**任意一个**关键词 |
| 只填 `expected_sources` | 某 chunk **文件名**包含期望子串 |
| 两者都填 | **来源 AND 关键词** 同时满足 |
| 都不填 | 默认算命中 |

**整体召回率** = 命中题数 ÷ 总题数，范围 **0～1**（`0.75` 即 75% 题目召回了相关片段）。

#### 终端输出

```text
[Final Pipeline]
  recall@k: 0.7500        ← 整体召回率，优先看这个
  mrr: 0.6250
  keyword_coverage: 0.5000

[Per Stage]               ← 各检索阶段对比
  vector  recall@k=0.5000
  bm25    recall@k=0.7500
  rrf     recall@k=0.7500
  final   recall@k=0.7500

[Cases]                   ← 单题 PASS/FAIL
  [PASS] example-1: ...
  [FAIL] example-2: ...
```

- **PASS** = 该题 top-k 内找到期望 chunk  
- **FAIL** = 未找到，检查关键词是否与文档实际用词一致，或增大 `--top-k`

#### JSON 报告（`eval/results/latest.json`）

| 字段 | 含义 |
| ---- | ---- |
| `summary.recall@k` | 最终管线整体召回率 |
| `stage_summary.vector.recall@k` | 纯向量阶段 |
| `stage_summary.bm25.recall@k` | BM25 阶段 |
| `stage_summary.rrf.recall@k` | RRF 融合后（Rerank 前） |
| `stage_summary.final.recall@k` | 含 Rerank 的最终结果 |
| `cases[].recall@k` | 单题是否命中（true/false） |
| `cases[].retrieved_sources` | 实际召回的文件名，便于排查 FAIL |

#### 与 keyword_coverage 的区别

| 指标 | 含义 |
| ---- | ---- |
| **recall@k** | 有没有命中相关 chunk（按题 0/1，再平均） |
| **keyword_coverage** | `expected_keywords` 中有多少比例出现在 top-k 合并文本里（可部分命中，如 2 词中命中 1 个 = 0.5） |
| **mrr** | 第一个命中 chunk 的排名倒数（越靠前越高） |

#### 召回率偏低的常见原因

1. 黄金集关键词与文档实际用词不一致（文档写「对称加密」，黄金集写「AES」）
2. 升级前上传的文档未**重新上传**，`document_chunks` 为空导致 BM25 无效
3. `top_k` 过小，相关 chunk 排在第 5 位以后（可 `--top-k 8` 重试）
4. `expected_sources` 文件名与上传时的 `filename` 不一致

#### 对比不同检索方案时看哪里

| 方案 | 重点字段 |
| ---- | -------- |
| 纯向量 | `stage_summary.vector.recall@k` |
| 混合（无 Rerank） | `stage_summary.rrf.recall@k` |
| 混合 + Rerank | `summary.recall@k`（即 final） |

### 7. 生产服务器说明

2 核 2G Docker 部署**不运行**评测脚本。生产环境保持 `.env` 中检索开关即可；对比实验只在本地 `.env` / `.env.local` 完成，结果文件留在本机 `eval/results/`，勿部署到服务器。

---

## Ollama 模型拉取

```bash
./scripts/pull-ollama-model.sh
# 国内 TLS 超时 → VPN/代理后重试
docker exec askb-ollama ollama list
# 复用 langgraph 中间件时: docker exec rag-ollama ollama list
```

---

## 端口冲突

| 报错          | 处理                                               |
| ------------- | -------------------------------------------------- |
| `3306 in use` | 已映射 **3307**，`.env.local` 用 `MYSQL_PORT=3307` |
| `6379 in use` | 改 infra compose 为 `6380:6379`，`.env.local` 同步 |
| `8000 in use` | 停掉其他项目的 backend 或改 compose 端口映射       |

---

## 手动同步默认账号（SQL）

backend 首次建表后，如需手动重置登录账号：

```bash
docker exec -i askb-mysql mysql -urag -prag123456 rag_standards < docker/mysql/seed_users.sql
```

---

## API

| 方法 | 路径                             | 说明                 |
| ---- | -------------------------------- | -------------------- |
| GET  | `/api/health`                    | 健康检查             |
| POST | `/api/auth/login`                | 登录（需验证码）     |
| POST | `/api/auth/refresh`              | 刷新 access token    |
| POST | `/api/auth/logout`               | 登出并吊销令牌       |
| GET  | `/api/auth/captcha`              | 获取算术验证码       |
| POST | `/api/auth/register`             | 自助注册（可配置）   |
| POST | `/api/auth/change-password`      | 修改密码             |
| GET  | `/api/auth/users`                | 用户列表（admin）    |
| POST | `/api/auth/users`                | 创建用户（admin）    |
| PATCH| `/api/auth/users/{id}`           | 启用/禁用/改角色     |
| POST | `/api/auth/users/{id}/reset-password` | 重置密码（admin） |
| GET  | `/api/auth/me`                   | 当前用户             |
| GET  | `/api/documents`                 | 文档列表（admin）    |
| POST | `/api/documents/upload`          | 上传 PDF/Word/TXT/MD |
| GET  | `/api/documents/tasks/{task_id}` | 入库任务             |
| POST | `/api/chat/rag`                  | RAG 流式 SSE         |
| GET  | `/api/sessions`                  | 历史会话             |

---

## 目录结构

```
agentscope-knowledgebase/
├── .env                 # 共用密钥与默认账号（本地+Docker）
├── .env.local           # 仅本地连接覆盖
├── docker-compose.yml          # 全量部署
├── docker-compose.infra.yml    # 仅中间件
├── docker/mysql/
│   ├── init.sql                # MySQL 库与用户
│   └── seed_users.sql          # 默认 admin/user 账号
├── scripts/setup-local.sh
├── scripts/deploy-docker.sh
├── scripts/run_eval.sh         # RAG 评测（仅本地）
├── eval/
│   ├── golden_set.example.json # 黄金集模板
│   └── results/                # 评测报告（gitignore）
├── backend/
│   └── app/eval/               # 评测模块
└── frontend/
```

## 支持的上传格式

PDF、Word（.docx）、TXT、Markdown

## 文档分块（`.env`）

上传后 pipeline 按下列配置切分并写入 Qdrant + MySQL：

| 策略 | 说明 |
| ---- | ---- |
| `semantic`（默认） | Ollama embedding 判断相邻句/条语义边界，单块目标 **512–1024 token**（下限内置，上限=`CHUNK_TOKEN_SIZE`）；超出上限时回退固定 token 切分 |
| `fixed` | 仅按 `CHUNK_TOKEN_SIZE` / `CHUNK_TOKEN_OVERLAP` 固定切分 |

```env
CHUNK_STRATEGY=semantic
CHUNK_TOKEN_SIZE=1024
CHUNK_TOKEN_OVERLAP=154
CHUNK_SEMANTIC_SIMILARITY_THRESHOLD=0.60
```

> 修改分块策略或参数后，需**重新上传**文档才会生效；已入库 chunk 不会自动重建。

## 说明

- AgentScope **不提供**用户登录，本项目自研 JWT + RBAC
- Word 解析为自研 `DocxParser`（AgentScope 内置无 Word 支持）
- 聊天 SSE 协议与 langgraph-rag-standards 兼容：`intent` / `sources` / `token` / `done`
- 通用对话（`general` 意图）走 AgentScope Agent：`ToolBase.check_permissions` → `PermissionEngine` → `RequireUserConfirmEvent` / 自动放行
