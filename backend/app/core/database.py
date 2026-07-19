import logging

from app.core.config import settings
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSIONS = 1536

# Database connection
DATABASE_URL = settings.database_url

# Create engine with connection pooling for better performance
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Validate connections before use
    pool_recycle=300,  # Recycle connections every 5 minutes
    echo=settings.environment == "development",  # SQL logging in dev
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models - using modern SQLAlchemy 2.0 approach
Base = declarative_base()


def get_db():
    """
    Database dependency to get DB session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# For testing purposes - create tables if they don't exist
def create_tables():
    """
    Create database tables
    """
    Base.metadata.create_all(bind=engine)


def ensure_pgvector() -> bool:
    """Enable pgvector-backed search if the database supports it.

    Idempotent: safe to run on every startup. Mirrors alembic migration 005
    for deployments that bootstrap the schema via create_tables() instead of
    running migrations. Returns True when the vector column is available.
    """
    if engine.dialect.name != "postgresql":
        return False

    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(
                text(
                    "ALTER TABLE document_chunks "
                    f"ADD COLUMN IF NOT EXISTS embedding vector({EMBEDDING_DIMENSIONS})"
                )
            )
            conn.execute(
                text(
                    "UPDATE document_chunks "
                    "SET embedding = CAST(embedding_vector::text AS vector) "
                    "WHERE embedding IS NULL AND embedding_vector IS NOT NULL"
                )
            )
        # Index creation is best-effort; search works without it.
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding "
                        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
                    )
                )
        except Exception as e:
            logger.warning(f"Could not create HNSW index (search still works): {e}")
        logger.info("pgvector enabled for document search")
        return True
    except Exception as e:
        logger.info(f"pgvector unavailable, using in-process similarity: {e}")
        return False


# For testing purposes - drop all tables
def drop_tables():
    """
    Drop all database tables
    """
    Base.metadata.drop_all(bind=engine)
