from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HousingCollection(Base):
    __tablename__ = "housing_collections"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    employee_id: Mapped[str] = mapped_column(String(120), index=True)
    housing_block: Mapped[str] = mapped_column(String(32), index=True)
    room_number: Mapped[str] = mapped_column(String(32))
    collection_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="collected", index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    waste_entries: Mapped[list["WasteEntry"]] = relationship(back_populates="collection")


class WasteEntry(Base):
    __tablename__ = "waste_entries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    employee_id: Mapped[str] = mapped_column(String(120), index=True)
    waste_category: Mapped[str] = mapped_column(String(32), index=True)
    waste_subtype: Mapped[str] = mapped_column(String(120))
    housing_block: Mapped[str] = mapped_column(String(32), index=True)
    room_number: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[float] = mapped_column(Numeric(10, 2))
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("housing_collections.id"),
        index=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    collection: Mapped["HousingCollection"] = relationship(back_populates="waste_entries")


class WetProcessingUpdate(Base):
    __tablename__ = "wet_processing_updates"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    employee_id: Mapped[str] = mapped_column(String(120), index=True)
    compost_quantity: Mapped[float] = mapped_column(Numeric(10, 2))
    biogas_quantity: Mapped[float] = mapped_column(Numeric(10, 2))
    total_wet_reference: Mapped[float] = mapped_column(Numeric(10, 2))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompostDistribution(Base):
    __tablename__ = "compost_distributions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    employee_id: Mapped[str] = mapped_column(String(120), index=True)
    recipient: Mapped[str] = mapped_column(String(120), index=True)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2))
    distribution_date: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
