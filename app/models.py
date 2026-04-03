from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, timezone
from .database import Base


class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    message = Column(String, nullable=False)
    category = Column(String, nullable=False, default="info")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class FetchStatus(Base):
    __tablename__ = "fetch_status"

    id = Column(Integer, primary_key=True)
    last_fetch = Column(DateTime, nullable=True)
    last_error = Column(String, nullable=True)
    total_fetched = Column(Integer, default=0)


class AppConfig(Base):
    __tablename__ = "app_config"

    key   = Column(String, primary_key=True)
    value = Column(String, nullable=True)


class AiRecommendation(Base):
    __tablename__ = "ai_recommendations"

    id          = Column(Integer, primary_key=True, index=True)
    run_id      = Column(Integer, index=True, nullable=False)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    title       = Column(String, nullable=False)
    description = Column(String, nullable=False)
    severity    = Column(String, default="info")   # info | warning | critical
    category    = Column(String, nullable=True)
    status      = Column(String, default="pending")  # pending | accepted | rejected
