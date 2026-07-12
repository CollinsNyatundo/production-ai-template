import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings
from app.types import EngineKwargs


# 1. Base Class definition with Async Attributes support
class Base(AsyncAttrs, DeclarativeBase):
    pass


# 2. Database Models matching SQLite schema and expanded for production scalability
class ConversationMessage(Base):
    __tablename__ = "conversation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())


class AgentCheckpoint(Base):
    __tablename__ = "agent_checkpoints"

    session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False)
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    trajectory_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


# 3. Connection selection and async engine selector
# Dynamic connection URLs:
# Default PostgreSQL: postgresql+asyncpg://user:pass@host/db
# Default SQLite fallback: sqlite+aiosqlite:///app.db
db_url = getattr(settings, "database_url", "sqlite+aiosqlite:///app.db")

# Force sqlite to use dynamic async interface if not explicitly configured with asyncpg
if db_url.startswith("sqlite://"):
    db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://")
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

# Configure connection pooling and optimization parameters
engine_kwargs: EngineKwargs = {"echo": False, "pool_pre_ping": True}

if "sqlite" in db_url:
    # Ensure SQLite handles simultaneous multi-threading operations safely
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL specific pooling configs
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_async_engine(db_url, **engine_kwargs)

# Async session sessionmaker factory
async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


# Dependency yield provider for FastAPI routers
async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
