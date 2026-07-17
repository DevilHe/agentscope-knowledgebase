from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_ENV_FILES: list[str] = []
_base = _PROJECT_ROOT / ".env"
_local = _PROJECT_ROOT / ".env.local"
if _base.is_file():
    _ENV_FILES.append(str(_base))
if _local.is_file():
    _ENV_FILES.append(str(_local))
if not _ENV_FILES:
    _ENV_FILES = [".env"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=tuple(_ENV_FILES),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM — 商汤 SenseNova Token Plan
    openai_api_key: str = ""
    openai_base_url: str = "https://token.sensenova.cn/v1"
    openai_model: str = "deepseek-v4-flash"

    # OpenWeather（get_weather 工具）
    openweather_api_key: str = ""
    openweather_api_url: str = "https://api.openweathermap.org/data/2.5/weather"

    # Tavily（web_search 工具）
    tavily_api_key: str = ""

    # Ollama Embedding
    ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768

    qdrant_host: str = "127.0.0.1"
    qdrant_port: int = 6333
    qdrant_collection: str = "standards"

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3307
    mysql_user: str = "rag"
    mysql_password: str = "rag123456"
    mysql_database: str = "rag_standards"

    redis_url: str = "redis://127.0.0.1:6379/0"

    upload_dir: str = "uploads"
    knowledge_base: str = "default"
    top_k: int = 4
    score_threshold: float = 0.6
    history_max_messages: int = 20
    # 历史压缩：超过阈值时用 LLM 摘要旧轮次，再拼最近若干条原文
    history_compress_enabled: bool = True
    history_compress_threshold: int = 12
    history_keep_recent: int = 8

    # 混合检索：Qdrant dense+sparse（关闭则仅 dense）；可选 LLM Rerank
    retrieval_hybrid_enabled: bool = True
    # hybrid collection 名 = {qdrant_collection}{suffix}；空则默认 _hybrid
    qdrant_hybrid_collection_suffix: str = "_hybrid"
    retrieval_rrf_k: int = 60
    retrieval_candidate_top_k: int = 12
    retrieval_rerank_enabled: bool = False
    retrieval_rerank_candidates: int = 8

    # 分块：semantic=embedding 语义边界 + 超长回退固定 token；fixed=仅 ApproxTokenChunker
    # 单块目标区间 512–1024 token（下限内置，上限由 CHUNK_TOKEN_SIZE 控制）
    chunk_strategy: str = "semantic"
    chunk_token_size: int = 1024
    chunk_token_overlap: int = 154
    chunk_semantic_similarity_threshold: float = 0.60

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 2
    jwt_refresh_expire_days: int = 7

    # 认证安全
    registration_enabled: bool = False
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    login_rate_limit_per_ip: int = 20
    login_rate_limit_window_seconds: int = 60
    password_min_length: int = 8
    password_max_length: int = 16
    password_allowed_special: str = "!@#$%^&*"
    password_require_upper: bool = True
    password_require_lower: bool = True
    password_require_digit: bool = True
    password_require_special: bool = True

    password_encrypt_key: str = ""

    # 上传安全
    upload_max_size_mb: int = 20

    # 敏感词（逗号分隔）
    sensitive_words: str = "走私,贩毒,爆炸物,制毒,黑客攻击,钓鱼网站,色情"

    # 外部工具每日配额（按用户）
    tool_quota_web_search_daily: int = 50
    tool_quota_weather_daily: int = 30
    tool_quota_llm_daily: int = 200

    # Agent 治理
    agent_max_tool_rounds: int = 8
    agent_reply_timeout_seconds: int = 600
    agent_circuit_breaker_fail_threshold: int = 5
    agent_circuit_breaker_cooldown_seconds: int = 120
    user_token_quota_daily: int = 0  # 0 表示不限
    user_token_estimate_chars_per_token: float = 2.0

    # Prompt 版本与灰度（正文见 app/prompts/prompts.yml → unified_agent.{version}）
    agent_prompt_version: str = "v1"
    agent_prompt_canary_version: str = ""
    agent_prompt_canary_percent: int = 0  # 0-100，按 user_id 哈希分流

    # 模型按场景路由（空则回退 OPENAI_MODEL）
    openai_model_chat: str = ""
    openai_model_rerank: str = ""
    openai_model_fallback: str = ""

    admin_username: str = "admin"
    admin_password: str = ""
    user_username: str = "user"
    user_password: str = "User@123"

    @field_validator(
        "openweather_api_key", "openweather_api_url", "tavily_api_key", mode="before"
    )
    @classmethod
    def _strip_env_quotes(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip().strip("'\"")

    @property
    def resolved_upload_dir(self) -> Path:
        raw = Path(self.upload_dir)
        if raw.is_absolute():
            if raw.parts[:2] == ("/", "app") and not Path("/app").exists():
                return (_PROJECT_ROOT / "uploads").resolve()
            return raw
        return (_PROJECT_ROOT / raw).resolve()

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"


settings = Settings()
