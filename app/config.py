from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    dashscope_api_key: str = ""
    model_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_name: str = "qwen3-vl-plus"
    amap_api_key: str = ""
    bocha_api_key: str = ""
    data_dir: Path = Path(".data")
    model_timeout: int = Field(default=60, ge=1, le=180)
    max_concurrent_runs: int = Field(default=2, ge=1, le=8)
    demo_enabled: bool = True
    cookie_secure: bool = False

    @property
    def database_url(self):
        return f"sqlite:///{self.data_dir.resolve() / 'app.db'}"
