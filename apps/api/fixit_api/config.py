import os
from pathlib import Path
from pydantic_settings import BaseSettings

def _find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    # 1. Project root on host usually has docker-compose.yml
    for p in [current, *current.parents]:
        if (p / "docker-compose.yml").exists():
            return p
    # 2. Inside container (/app) or fallback
    for p in [current, *current.parents]:
        if p.name == "app" or (p / "storage").exists():
            return p
    if len(current.parents) >= 1:
        return current.parents[0]
    return current

_ROOT = _find_project_root()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Fixit Image Studio"
    API_PORT: int = int(os.environ.get("API_PORT", os.environ.get("PORT", 8310)))
    
    # Database Configuration
    # 1. Project/Revision Data: Development uses local SQLite, Production can override with PostgreSQL
    DATABASE_URL: str = f"sqlite:///{str((_ROOT / 'storage' / 'fixit.db').resolve())}"

    # 2. Company Auth Database: Points to production PostgreSQL for user authentication
    AUTH_DATABASE_URL: str = "postgresql://inspection:ts2020!!@192.168.209.100:5432/DB_TRIP_TRANS"
    
    # JWT Authentication
    SECRET_KEY: str = "fixit_super_secret_jwt_key_2026_modern_studio"
    TRIP_CLOSER_SECRET_KEY: str = "tripcloser_super_secret_key"
    FALLBACK_TRIP_KEY: str = "tc-prod-secret-2026-05-16-9f3d7a1b6c2e4d8f"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # Strata VLM / OCR & Fallback
    STRATA_VLM_URL: str = "http://192.168.202.24:8080/v1"
    STRATA_VLM_MODEL: str = "qwen3.8-flash-next"
    MSDN_COST_API_URL: str = "http://192.168.209.120:8100/api/costs/recommendation"
    DOC_LLM_MODEL: str = "gpt-6.1-sol"
    LLM_REASONING_EFFORT: str = "medium"
    
    # Storage & Fonts (Absolute resolution to project root)
    STORAGE_DIR: str = str((_ROOT / "storage").resolve())
    FONTS_DIR: str = str((_ROOT / "fonts").resolve())

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        project_root = _ROOT
        if not Path(self.STORAGE_DIR).is_absolute() or not Path(self.STORAGE_DIR).exists():
            cand = project_root / self.STORAGE_DIR.lstrip("./")
            if cand.exists():
                self.STORAGE_DIR = str(cand.resolve())
            else:
                self.STORAGE_DIR = str((project_root / "storage").resolve())
        if not Path(self.FONTS_DIR).is_absolute() or not Path(self.FONTS_DIR).exists():
            cand = project_root / self.FONTS_DIR.lstrip("./")
            if cand.exists():
                self.FONTS_DIR = str(cand.resolve())
            else:
                self.FONTS_DIR = str((project_root / "fonts").resolve())

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
