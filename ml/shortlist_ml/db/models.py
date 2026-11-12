from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from shortlist_ml.db.types import UTCDateTime


class Base(DeclarativeBase):
    pass


class User(Base):
    """Single local user (id=1) until Phase 5 accounts; every user-owned table keys on user_id."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("ats", "board_token"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    ats: Mapped[str] = mapped_column(String(32))
    board_token: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class IngestionRun(Base):
    """One row per (company fetch). `run_group` ties together rows from the same `ingest run`."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_group: Mapped[str] = mapped_column(String(36), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # ok | guarded (ingested, but closing was suppressed) | failed | skipped
    status: Mapped[str] = mapped_column(String(16))
    http_status: Mapped[int | None] = mapped_column(Integer)
    fetched: Mapped[int] = mapped_column(Integer, default=0)  # postings in the payload
    new: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)  # edited or reopened
    closed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(
        Integer, default=0
    )  # unparseable postings (or 1 if the fetch failed)
    skipped_by_guard: Mapped[int] = mapped_column(Integer, default=0)  # would-be closes suppressed
    raw_path: Mapped[str | None] = mapped_column(String(500))
    raw_sha256: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)


class Posting(Base):
    __tablename__ = "postings"
    __table_args__ = (
        UniqueConstraint("company_id", "source", "external_id"),
        Index("ix_postings_company_closed", "company_id", "closed_at"),
        Index("ix_postings_dedup", "company_id", "dedup_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    source: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(200))

    # Links point at the company's own pages; Shortlist ranks, it does not replace the source.
    url: Mapped[str] = mapped_column(String(1000))
    apply_url: Mapped[str] = mapped_column(String(1000))

    title: Mapped[str] = mapped_column(String(500))
    description_text: Mapped[str] = mapped_column(Text)
    location_raw: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    is_remote: Mapped[bool | None] = mapped_column(Boolean)

    years_min: Mapped[int | None] = mapped_column(Integer)
    seniority: Mapped[str] = mapped_column(String(16))  # intern|entry|mid|senior|unknown
    is_entry_level: Mapped[bool] = mapped_column(Boolean)
    sponsorship: Mapped[str] = mapped_column(String(16))  # restricted|sponsors|unknown

    # Timestamps. first/last_seen/closed are OUR observation times (UTC) and drive time-based
    # splits; source_* are whatever the ATS reports (may be missing or unreliable).
    source_posted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    source_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # last detected content edit

    content_hash: Mapped[str] = mapped_column(String(64))
    dedup_key: Mapped[str] = mapped_column(String(64))
    # NULL => this posting is the root of its repost group. Otherwise points at the root (the
    # earliest-seen posting with the same dedup_key). Group id = COALESCE(canonical_id, id).
    canonical_id: Mapped[int | None] = mapped_column(ForeignKey("postings.id"), index=True)
