import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from fixit_api.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

# =========================================================================
# 1. Project / Revision Database Engine (Local SQLite by default / Isolated)
# =========================================================================
db_url = settings.DATABASE_URL
engine_kwargs = {"pool_pre_ping": True}

if "sqlite" in db_url:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    logger.info(f"[Database] Using local SQLite for project workspace storage: {db_url}")
else:
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    logger.info("[Database] Using PostgreSQL for project storage.")

engine = create_engine(db_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency for FixIt workspace, projects, and revisions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================================================================
# 2. Company Auth Database Engine (Always points to production DB for user login)
# =========================================================================
auth_url = settings.AUTH_DATABASE_URL
auth_kwargs = {"pool_pre_ping": True}

if "sqlite" in auth_url:
    auth_kwargs["connect_args"] = {"check_same_thread": False}
else:
    if auth_url.startswith("postgresql://"):
        auth_url = auth_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    auth_kwargs["pool_size"] = 5
    auth_kwargs["max_overflow"] = 10

try:
    auth_engine = create_engine(auth_url, **auth_kwargs)
    AuthSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=auth_engine)
    logger.info("[Database] Connected to Company Production Auth Database for user authentication.")
except Exception as e:
    logger.error(f"[Database] Failed to initialize Auth Engine: {e}")
    auth_engine = engine
    AuthSessionLocal = SessionLocal

def get_auth_db():
    """Dependency for User login and authentication verification."""
    db = AuthSessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Auto-creates tables on project storage engine if not exist."""
    try:
        # Import models to ensure they are registered with Base.metadata
        from fixit_api import models  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("[Database] Workspace tables initialized successfully.")
    except Exception as e:
        logger.error(f"[Database] Table initialization error: {e}")
