"""Shared persistence models for local review and webhook projections."""
from sqlalchemy import String, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase): pass
class StoredOrder(Base):
    __tablename__ = "orders"
    order_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
class ImportRun(Base):
    __tablename__ = "import_runs"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64))
    count: Mapped[str] = mapped_column(String(10))

class StoredPolicy(Base):
    __tablename__ = "review_policy"
    policy_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)

