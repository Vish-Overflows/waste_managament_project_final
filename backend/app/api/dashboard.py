import csv
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func

from app.dependencies import DbSession, require_role
from app.models import CompostDistribution, HousingCollection, User, WasteEntry, WetProcessingUpdate
from app.schemas import (
    BlockStat,
    CategoryBreakdownPoint,
    DashboardSummary,
    OperatorStat,
    SummaryMetric,
    TrendPoint,
)
from app.time_utils import campus_date, campus_today, local_day_start_utc, local_next_day_start_utc

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def write_section(writer, title: str, headers: list[str], rows: list[list[object]]) -> None:
    writer.writerow([title])
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    writer.writerow([])


def to_weight(value: object) -> float:
    return round(float(value or 0), 2)


@router.get("/summary", response_model=DashboardSummary)
def summary(
    db: DbSession,
    _: Annotated[User, Depends(require_role("admin"))],
) -> DashboardSummary:
    today = campus_today()
    week_start = today - timedelta(days=today.weekday())
    today_start = local_day_start_utc(today)
    tomorrow_start = local_next_day_start_utc(today)
    week_start_dt = local_day_start_utc(week_start)
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
        .filter(WasteEntry.created_at >= today_start, WasteEntry.created_at < tomorrow_start)
        .scalar()
        or 0
    )
    processed_this_week = float(
        db.query(func.coalesce(func.sum(WasteEntry.quantity), 0))
        .filter(WasteEntry.created_at >= week_start_dt)
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
    since = campus_today() - timedelta(days=days - 1)
    since_dt = local_day_start_utc(since)
    rows = (
        db.query(WasteEntry.created_at, WasteEntry.quantity)
        .filter(WasteEntry.created_at >= since_dt)
        .order_by(WasteEntry.created_at)
        .all()
    )
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[campus_date(row.created_at).isoformat()] += float(row.quantity or 0)
    return [TrendPoint(date=day, total_weight=round(total, 2)) for day, total in sorted(totals.items())]


@router.get("/category-breakdown", response_model=list[CategoryBreakdownPoint])
def category_breakdown(
    db: DbSession,
    _: Annotated[User, Depends(require_role("admin"))],
) -> list[CategoryBreakdownPoint]:
    today = campus_today()
    week_start = today - timedelta(days=today.weekday())

    def total_for_window(category: str, start: date | None) -> float:
        query = db.query(func.coalesce(func.sum(WasteEntry.quantity), 0)).filter(
            WasteEntry.waste_category == category
        )
        if start:
            query = query.filter(WasteEntry.created_at >= local_day_start_utc(start))
        return float(query.scalar() or 0)

    def total_for_day(category: str, target: date) -> float:
        return float(
            db.query(func.coalesce(func.sum(WasteEntry.quantity), 0))
            .filter(
                WasteEntry.waste_category == category,
                WasteEntry.created_at >= local_day_start_utc(target),
                WasteEntry.created_at < local_next_day_start_utc(target),
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
        .filter(WasteEntry.waste_category == "Dry Waste")
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


@router.get("/export/weekly")
def export_weekly_report(
    db: DbSession,
    _: Annotated[User, Depends(require_role("admin"))],
) -> Response:
    today = campus_today()
    since = today - timedelta(days=6)
    since_dt = local_day_start_utc(since)
    until_dt = local_next_day_start_utc(today)

    collections = (
        db.query(HousingCollection)
        .filter(HousingCollection.created_at >= since_dt, HousingCollection.created_at < until_dt)
        .order_by(HousingCollection.created_at.desc(), HousingCollection.id.desc())
        .all()
    )
    entries = (
        db.query(WasteEntry)
        .filter(WasteEntry.created_at >= since_dt, WasteEntry.created_at < until_dt)
        .order_by(WasteEntry.created_at.desc(), WasteEntry.id.desc())
        .all()
    )
    wet_updates = (
        db.query(WetProcessingUpdate)
        .filter(WetProcessingUpdate.created_at >= since_dt, WetProcessingUpdate.created_at < until_dt)
        .order_by(WetProcessingUpdate.created_at.desc(), WetProcessingUpdate.id.desc())
        .all()
    )
    compost_distributions = (
        db.query(CompostDistribution)
        .filter(CompostDistribution.created_at >= since_dt, CompostDistribution.created_at < until_dt)
        .order_by(CompostDistribution.created_at.desc(), CompostDistribution.id.desc())
        .all()
    )

    daily_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"Dry Waste": 0.0, "Wet Waste": 0.0})
    dry_sources: dict[str, float] = defaultdict(float)
    dry_subtypes: dict[str, float] = defaultdict(float)
    wet_subtypes: dict[str, float] = defaultdict(float)
    category_totals: dict[str, float] = defaultdict(float)

    for entry in entries:
        entry_date = campus_date(entry.created_at).isoformat()
        quantity = to_weight(entry.quantity)
        daily_totals[entry_date][entry.waste_category] += quantity
        category_totals[entry.waste_category] += quantity
        if entry.waste_category == "Dry Waste":
            dry_sources[entry.housing_block] += quantity
            dry_subtypes[entry.waste_subtype] += quantity
        if entry.waste_category == "Wet Waste":
            wet_subtypes[entry.waste_subtype] += quantity

    compost_total = sum(to_weight(update.compost_quantity) for update in wet_updates)
    biogas_total = sum(to_weight(update.biogas_quantity) for update in wet_updates)
    compost_distributed_total = sum(to_weight(item.quantity) for item in compost_distributions)

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Campus Waste Management Weekly Report"])
    writer.writerow(["Period", since.isoformat(), today.isoformat()])
    writer.writerow(["Generated At", datetime.now(UTC).isoformat()])
    writer.writerow([])

    write_section(
        writer,
        "Summary",
        ["Metric", "Value"],
        [
            ["Staff collection records", len(collections)],
            ["Operator entries", len(entries)],
            ["Dry waste total kg", to_weight(category_totals["Dry Waste"])],
            ["Wet waste total kg", to_weight(category_totals["Wet Waste"])],
            ["Total waste kg", to_weight(sum(category_totals.values()))],
            ["Compost logged kg", to_weight(compost_total)],
            ["Biogas logged kg", to_weight(biogas_total)],
            ["Compost distributed kg", to_weight(compost_distributed_total)],
        ],
    )
    write_section(
        writer,
        "Individual Staff Collection Entries",
        ["Collection Date", "Block", "Room", "Staff", "Status", "Recorded At"],
        [
            [
                item.collection_date.isoformat(),
                item.housing_block,
                item.room_number,
                item.employee_id,
                item.status,
                item.created_at.isoformat(),
            ]
            for item in collections
        ],
    )
    write_section(
        writer,
        "Individual Operator Entries",
        ["Processed At", "Operator", "Source", "Category", "Subtype", "Quantity kg"],
        [
            [
                item.created_at.isoformat(),
                item.employee_id,
                item.housing_block,
                item.waste_category,
                item.waste_subtype,
                to_weight(item.quantity),
            ]
            for item in entries
        ],
    )
    write_section(
        writer,
        "Per-Day Waste Totals",
        ["Date", "Dry kg", "Wet kg", "Total kg"],
        [
            [
                day,
                to_weight(values["Dry Waste"]),
                to_weight(values["Wet Waste"]),
                to_weight(values["Dry Waste"] + values["Wet Waste"]),
            ]
            for day, values in sorted(daily_totals.items())
        ],
    )
    write_section(
        writer,
        "Dry Waste Source Patterns",
        ["Source", "Dry kg"],
        [[source, to_weight(total)] for source, total in sorted(dry_sources.items(), key=lambda item: item[1], reverse=True)],
    )
    write_section(
        writer,
        "Dry Subtype Breakdown",
        ["Subtype", "Dry kg"],
        [[subtype, to_weight(total)] for subtype, total in sorted(dry_subtypes.items())],
    )
    write_section(
        writer,
        "Wet Subtype Breakdown",
        ["Subtype", "Wet kg"],
        [[subtype, to_weight(total)] for subtype, total in sorted(wet_subtypes.items())],
    )
    write_section(
        writer,
        "Wet Processing Updates",
        ["Recorded At", "Operator", "Compost kg", "Biogas kg", "Wet Reference kg", "Notes"],
        [
            [
                item.created_at.isoformat(),
                item.employee_id,
                to_weight(item.compost_quantity),
                to_weight(item.biogas_quantity),
                to_weight(item.total_wet_reference),
                item.notes or "",
            ]
            for item in wet_updates
        ],
    )
    write_section(
        writer,
        "Compost Distribution Entries",
        ["Distributed At", "Distribution Date", "Operator", "Recipient", "Quantity kg"],
        [
            [
                item.created_at.isoformat(),
                item.distribution_date.isoformat(),
                item.employee_id,
                item.recipient,
                to_weight(item.quantity),
            ]
            for item in compost_distributions
        ],
    )

    filename = f"campus-waste-weekly-report-{today.isoformat}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
