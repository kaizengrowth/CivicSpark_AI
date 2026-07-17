from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

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

    The pgvector extension must exist before create_all, because model
    columns use the Vector type. Models must be imported so
    Base.metadata knows every table, regardless of caller.
    """
    from sqlalchemy import text

    import app.models  # noqa: F401  (registers all models on Base.metadata)

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)


# For testing purposes - drop all tables
def drop_tables():
    """
    Drop all database tables
    """
    Base.metadata.drop_all(bind=engine)
