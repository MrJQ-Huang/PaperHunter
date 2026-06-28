from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # LLM 配置
    # anthropic: Anthropic Messages 兼容接口；openai: OpenAI Chat Completions 兼容接口
    llm_api_type: str = "anthropic"
    llm_api_key: str = "tp-placeholder"
    llm_base_url: str = "https://token-plan-cn.xiaomimimo.com/anthropic"
    llm_model: str = "xiaomi/mimo-v2.5-pro"
    cc_switch_config_path: str = ""

    # 学术 API 密钥（可选）
    semantic_scholar_api_key: str = ""
    springer_api_key: str = ""
    elsevier_api_key: str = ""

    # Unpaywall
    unpaywall_email: str = "researcher@example.com"

    # 代理
    proxy_url: str = ""

    # 存储
    download_dir: str = "./papers"
    db_path: str = "./data/papers.db"

    # 限流配置
    arxiv_interval: float = 3.0  # arXiv 请求间隔(秒)
    google_scholar_delay_min: float = 5.0
    google_scholar_delay_max: float = 15.0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# 确保目录存在
Path(settings.download_dir).mkdir(parents=True, exist_ok=True)
Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
