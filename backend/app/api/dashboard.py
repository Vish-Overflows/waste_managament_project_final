from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func

from app.dependencies import DbSession, require_role
from app.models import HousingCollection, User, WasteEntry, WetProcessingUpdate
from app.schemas import (
    BlockStat,
    CategoryBreakdownPoint,
    DashboardSummary,
    OperatorStat,
    SummaryMetric,
    TrendPoint,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(
    db: DbSession,
    _: Annotated[User, Depends(require_role("admin"))],
) -> DashboardSummary:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    total_collections = db.query(func.count(HousingCollection.id)).scalar() or 0
    collections_today = (
        db.query(func.count(HousingCollection.id))
        .filter(HousingCollection.collection_date == today)
        .scalar()
        or 0
    )
    collections_this_week = (
        db.query(func.count(HousingCollection.id))
        .filter(HousingCollection.collection_date >= week_start)
        .scalar()
        or 0
    )
    staff_collection_records = total_collections
    processed_collections = (
        db.query(func.count(HousingCollection.id))
        .filter(HousingCollection.status == "processed")
        .scalar()
        or 0
    )
    processed_today = float(
        db.query(func.coalesce(func.sum(WasteEntry.quantity), 0))
        .filter(func.date(WasteEntry.created_at) == today.isoformat())
        .scalar()
        or 0
    )
    processed_this_week = float(
        db.query(func.coalesce(func.sum(WasteEntry.quantity), 0))
        .filter(func.date(WasteEntry.created_at) >= week_start.isoformat())
        .scalar()
        or 0
    )
    processed_total = float(db.query(func.coalesce(func.sum(WasteEntry.quantity), 0)).scalar() or 0)
    dry_total = float(
        db.query(func.coalesce(func.sum(WasteEntry.quantity), 0))
        .filter(WasteEntry.waste_category == "Dry Waste")
        .scalar()
        or 0
    )
    wet_total = float(
        db.query(func.coalesce(func.sum(WasteEntry.quantity), 0))
        .filter(WasteEntry.waste_category == "Wet Waste")
        .scalar()
        or 0
    )
    latest_processing = db.query(WetProcessingUpdate).order_by(WetProcessingUpdate.id.desc()).first()
    latest_label = latest_processing.created_at.strftime("%Y-%m-%d %H:%M") if latest_processing else "No update"
    return DashboardSummary(
        metrics=[
            SummaryMetric(label="Collections Recorded", value=int(total_collections)),
            SummaryMetric(label="Collections Today", value=int(collections_today)),
            SummaryMetric(label="Collections This Week", value=int(collections_this_week)),
            SummaryMetric(label="Staff Collection Records", value=int(staff_collection_records)),
            SummaryMetric(label="Collections Processed", value=int(processed_collections)),
            SummaryMetric(label="Waste Processed Today", value=round(processed_today, 2)),
            SummaryMetric(label="Waste Processed This Week", value=round(processed_this_week, 2)),
            SummaryMetric(label="Waste Processed", value=round(processed_total, 2)),
            SummaryMetric(label="Dry Waste", value=round(dry_total, 2)),
            SummaryMetric(label="Wet Waste", value=round(wet_total, 2)),
            SummaryMetric(label="Last Processing Update", value=latest_label),
        ]
    )


@router.get("/trends", response_model=list[TrendPoint])
def trends(
    db: DbSession,
    _: Annotated[User, Depends(require_role("admin"))],
    days: int = Query(default=14, ge=7, le=90),
) -> list[TrendPoint]:
    since = date.today() - timedelta(days=days - 1)
    rows = (
        db.query(
            func.date(WasteEntry.created_at).label("entry_date"),
            func.coalesce(func.sum(WasteEntry.quantity), 0).label("total_weight"),
        )
        .filter(func.date(WasteEntry.created_at) >= since.isoformat())
        .group_by(func.date(WasteEntry.created_at))
        .order_by(func.date(WasteEntry.created_at))
        .all()
    )
    return [TrendPoint(date=str(row.entry_date), total_weight=float(row.total_weight)) for row in rows]


@router.get("/category-breakdown", response_model=list[CategoryBreakdownPoint])
def category_breakdown(
    db: DbSession,
    _: Annotated[User, Depends(require_role("admin"))],
) -> list[CategoryBreakdownPoint]:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    def total_for_window(category: str, start: date | None) -> float:
        query = db.query(func.coalesce(func.sum(WasteEntry.quantity), 0)).filter(
            WasteEntry.waste_category == category
        )
        if start:
            query = query.filter(func.date(WasteEntry.created_at) >= start.isoformat())
        return float(query.scalar() or 0)

    def total_for_day(category: str, target: date) -> float:
        return float(
            db.query(func.coalesce(func.sum(WasteEntry.quantity), 0))
            .filter(
                WasteEntry.waste_category == category,
                func.date(WasteEntry.created_at) == target.isoformat(),
            )
            .scalar()
            or 0
        )

    return [
        CategoryBreakdownPoint(
            label="Today",
            dry_weight=total_for_day("Dry Waste", today),
            wet_weight=total_for_day("Wet Waste", today),
        ),
        CategoryBreakdownPoint(
            label="This Week",
            dry_weight=total_for_window("Dry Waste", week_start),
            wet_weight=total_for_window("Wet Waste", week_start),
        ),
        CategoryBreakdownPoint(
            label="Overall",
            dry_weight=total_for_window("Dry Waste", None),
            wet_weight=total_for_window("Wet Waste", None),
        ),
    ]


@router.get("/blocks", response_model=list[BlockStat])
def blocks(
    db: DbSession,
    _: Annotated[User, Depends(require_role("admin"))],
) -> list[BlockStat]:
    rows = (
        db.query(
            WasteEntry.housing_block,
            func.count(WasteEntry.id).label("collections_count"),
            func.coalesce(func.sum(WasteEntry.quantity), 0).label("processed_weight"),
        )
        .group_by(WasteEntry.housing_block)
        .order_by(func.coalesce(func.sum(WasteEntry.quantity), 0).desc())
        .all()
    )
    return [
        BlockStat(
            housing_block=row.housing_block,
            collections_count=int(row.collections_count),
            processed_weight=float(row.processed_weight),
        )
        for row in rows
    ]


@router.get("/operators", response_model=list[OperatorStat])
def operators(
    db: DbSession,
    _: Annotated[User, Depends(require_role("admin"))],
) -> list[OperatorStat]:
    rows = (
        db.query(
            WasteEntry.employee_id,
            func.count(WasteEntry.id).label("entries_count"),
            func.coalesce(func.sum(WasteEntry.quantity), 0).label("total_weight"),
        )
        .group_by(WasteEntry.employee_id)
        .order_by(func.coalesce(func.sum(WasteEntry.quantity), 0).desc())
        .all()
    )
    return [
        OperatorStat(
            employee_id=row.employee_id,
            entries_count=int(row.entries_count),
            total_weight=float(row.total_weight),
        )
        for row in rows
    ]
