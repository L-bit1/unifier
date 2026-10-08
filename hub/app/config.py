from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

HUB_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=HUB_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    unifier_host: str = "0.0.0.0"
    unifier_port: int = 8787
    unifier_db: str = "data/unifier.db"
    unifier_device_online_seconds: int = 90
    # 逗号分隔，用于联通性检查判定「是否全员在线」；留空则不做门禁
    unifier_expected_devices: str = ""
    github_token: str | None = None
    # 逗号分隔：扫描本地 Git 项目；留空则仅依赖 GitHub API / Hub 已注册项目
    unifier_workspace_roots: str = ""

    # 飞书自建应用（仅本机 .env，勿提交）
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_default_github_owner: str = ""
    feishu_default_github_repo: str = ""
    feishu_default_implementer_device: str = ""
    feishu_default_implementer_agent: str = "cursor"
    feishu_default_reviewers: str = ""
    feishu_bridge_enabled: bool = False

    # 四项目灵魂栈（Mac Head / 机房 Head）
    custom_ai_url: str = "http://127.0.0.1:8200"
    aether_url: str = "http://127.0.0.1:8100"
    lab_queue_url: str = "http://127.0.0.1:8790"
    custom_ai_session_id: str = "soul-unified"

    # n8n 自动化引擎（NAS 式套件：可选启用，路线 A 遗留）
    n8n_enabled: bool = False
    n8n_url: str = "http://127.0.0.1:5678"
    n8n_webhook_path: str = "unifier-events"
    n8n_api_key: str | None = None

    # 内置工作流引擎（路线 B，默认启用）
    workflows_enabled: bool = True
    workflow_smtp_host: str = ""
    workflow_smtp_port: int = 587
    workflow_smtp_user: str = ""
    workflow_smtp_password: str = ""
    workflow_smtp_from: str = "unifier@localhost"

    # 圆桌对话
    dialogue_round_timeout_seconds: int = 600  # IDE 模式：给人留时间手动 poll
    dialogue_transcript_dir: str = ""  # 空则写 ~/.unifier/dialogue + 试点仓
    dialogue_auto_reply: bool = True  # 网页发题后默认尝试 Hub 代言补齐未发言方
    dialogue_auto_use_soul: bool = True  # 优先调自研灵魂；失败则用规则代言
    dialogue_mask_peers_until_complete: bool = False  # False=随时可见对方发言

    @property
    def n8n_webhook_url(self) -> str:
        if not self.n8n_enabled:
            return ""
        return f"{self.n8n_url.rstrip('/')}/webhook/{self.n8n_webhook_path.lstrip('/')}"

    @property
    def feishu_configured(self) -> bool:
        return bool(self.feishu_app_id and self.feishu_app_secret)

    def workspace_roots_list(self) -> list[Path]:
        roots: list[Path] = []
        for part in self.unifier_workspace_roots.split(","):
            part = part.strip()
            if part:
                roots.append(Path(part).expanduser())
        return roots


settings = Settings()
