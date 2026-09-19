"""配置管理:从 .env 读取密钥与模型设置"""
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# 用绝对路径定位 .env,不要依赖「当前工作目录」——
# 否则换个目录启动(比如在仓库根目录跑 uvicorn)就读不到密钥,
# 而报错信息只会是「Key 未配置」,很难查到原因。
BASE_DIR = Path(__file__).resolve().parents[1]  # backend/
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_PATH, extra="ignore")

    # LLM(OpenAI 兼容协议:DeepSeek / 智谱 / OpenAI 等)
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    # 思考型模型(如 deepseek-v4-pro)默认关掉思考模式以支持结构化输出
    llm_thinking: bool = False

    # 高德开放平台 Web服务 Key
    amap_api_key: str = ""

    # 数据库连接串。默认 SQLite(文件在 backend/data/travel.db,零配置)。
    # 换 MySQL / PostgreSQL 只改这里,并自行装驱动:pip install pymysql / "psycopg[binary]"
    #   mysql+pymysql://user:password@127.0.0.1:3306/travel?charset=utf8mb4
    #   postgresql+psycopg://user:password@127.0.0.1:5432/travel
    database_url: str = "sqlite:///./data/travel.db"

    host: str = "0.0.0.0"
    port: int = 8000

    # 前端来源(开发:Vite 5173;生产部署改这里,逗号分隔)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    def get_cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
