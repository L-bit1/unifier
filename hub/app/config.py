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
