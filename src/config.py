from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.minimaxi.com/anthropic/v1"
    planner_model: str = "claude-sonnet-4-6"
    collector_model: str = "claude-haiku-4-5-20251001"
    analyst_model: str = "claude-haiku-4-5-20251001"
    comparator_model: str = "claude-sonnet-4-6"
    writer_model: str = "claude-sonnet-4-6"

    # Search
    tavily_api_key: str = ""

    # App
    log_level: str = "INFO"
    max_search_rounds: int = 3
    data_dir: str = "data"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
