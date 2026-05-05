from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func

from app.dependencies import DbSession, require_role
from app.models import CompostDistribution, HousingCollection, User, WasteEntry, WetProcessingUpdate
from app.schemas import (
    CompostDistributionCreate,
    PaginatedWasteEntries,
    ProcessingTotals,
    WasteEntryRead,
    WetIntakeCreate,
    WasteProcessCreate,
    CompostDistributionRecord,
    WetProcessingCreate,
    WetProcessingRecord,
    WetProcessingStatus,
)
from app.time_utils import campus_today

router = APIRouter(prefix="/processing", tags=["processing"])


def wet_totals(db: DbSession) -> tuple[float, float, float, float]:
    total_wet = float(
        db.query(func.coalesce(func.sum(WasteEntry.quantity), 0))
        .filter(WasteEntry.waste_category == "Wet Waste")
        .scalar()
        or 0
    )
    compost_deposited = float(db.query(func.coalesce(func.sum(WetProcessingUpdate.compost_quantity), 0)).scalar() or 0)
    biogas_deposited = float(db.query(func.coalesce(func.sum(WetProcessingUpdate.biogas_quantity), 0)).scalar() or 0)
    compost_distributed = float(db.query(func.coalesce(func.sum(CompostDistribution.quantity), 0)).scalar() or 0)
    return total_wet, compost_deposited, biogas_deposited, compost_distributed


@router.post("/waste", response_model=WasteEntryRead)
def process_waste(
    payload: WasteProcessCreate,
    db: DbSession,
    user: Annotated[User, Depends(require_role("operator", "admin"))],
) -> WasteEntryRead:
    collection = None
    source_location = payload.source_location
    room_number = "Direct"
    if payload.collection_id:
        collection = db.query(HousingCollection).filter(HousingCollection.id == payload.collection_id).first()
        if not collection:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
        source_location = collection.housing_block
        room_number = collection.room_number
    elif payload.waste_category == "Wet Waste" and not source_location:
        source_location = "Wet Waste Stream"
    elif not source_location:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Source location is required")

    entry = WasteEntry(
        employee_id=user.username,
        waste_category=payload.waste_category,
        waste_subtype=payload.waste_subtype,
        housing_block=source_location,
        room_number=room_number,
        quantity=payload.quantity,
        collection_id=collection.id if collection else None,
    )
    db.add(entry)
    if collection:
        collection.status = "processed"
        collection.processed_at = datetime.now(UTC)
    db.commit()
    db.refresh(entry)
    return WasteEntryRead.model_validate(entry)


@router.post("/wet-intake", response_model=WasteEntryRead)
def process_wet_intake(
    payload: WetIntakeCreate,
    db: DbSession,
    user: Annotated[User, Depends(require_role("operator", "admin"))],
) -> WasteEntryRead:
    compost = float(payload.compost_quantity)
    biogas = float(payload.biogas_quantity)
    if compost == 0 and biogas == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter how much wet waste went to compost or biogas.",
        )
    if compost + biogas > payload.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compost and biogas machine quantities cannot exceed wet waste quantity.",
        )

    total_wet, compost_deposited, biogas_deposited, _ = wet_totals(db)
    remaining_wet = total_wet - compost_deposited - biogas_deposited + float(payload.quantity)
    if compost + biogas > remaining_wet:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compost and biogas machine quantities cannot exceed remaining wet waste.",
        )

    entry = WasteEntry(
        employee_id=user.username,
        waste_category="Wet Waste",
        waste_subtype=payload.waste_subtype,
        housing_block="Wet Waste Stream",
        room_number="Direct",
        quantity=payload.quantity,
        collection_id=None,
    )
    update = WetProcessingUpdate(
        employee_id=user.username,
        compost_quantity=compost,
        biogas_quantity=biogas,
        total_wet_reference=total_wet + float(payload.quantity),
        notes=payload.notes,
    )
    db.add(entry)
    db.add(update)
    db.commit()
    db.refresh(entry)
    return WasteEntryRead.model_validate(entry)


@router.post("/wet")
def update_wet_processing(
    payload: WetProcessingCreate,
    db: DbSession,
    user: Annotated[User, Depends(require_role("operator", "admin"))],
) -> dict[str, str]:
    total_wet, compost_deposited, biogas_deposited, _ = wet_totals(db)
    compost = float(payload.compost_quantity)
    biogas = float(payload.biogas_quantity)
    remaining_wet = total_wet - compost_deposited - biogas_deposited
    if compost == 0 and biogas == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter a compost or biogas quantity.",
        )
    if compost + biogas > remaining_wet:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compost and biogas quantities cannot exceed remaining wet waste processed.",
        )
    update = WetProcessingUpdate(
        employee_id=user.username,
        compost_quantity=compost,
        biogas_quantity=biogas,
        total_wet_reference=total_wet,
        notes=payload.notes,
    )
    db.add(update)
    db.commit()
    return {"message": "Wet processing update saved"}


@router.post("/compost-distributions")
def create_compost_distribution(
    payload: CompostDistributionCreate,
    db: DbSession,
    user: Annotated[User, Depends(require_role("operator", "admin"))],
) -> dict[str, str]:
    _, compost_deposited, _, compost_distributed = wet_totals(db)
    quantity = sum(float(entry.quantity) for entry in payload.entries)
    if quantity + compost_distributed > compost_deposited:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compost distribution cannot exceed compost deposited so far.",
        )

    today = campus_today()
    for entry in payload.entries:
        db.add(
            CompostDistribution(
                employee_id=user.username,
                recipient=entry.recipient,
                quantity=float(entry.quantity),
                distribution_date=today,
            )
        )
    db.commit()
    return {"message": "Compost distribution saved"}


@router.get("/entries", response_model=PaginatedWasteEntries)
def list_processed_entries(
    db: DbSession,
    user: Annotated[User, Depends(require_role("operator", "admin"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    waste_category: str | None = Query(default=None, alias="wasteCategory"),
) -> PaginatedWasteEntries:
    query = db.query(WasteEntry)
    if user.role == "operator":
        query = query.filter(WasteEntry.employee_id == user.username)
    if waste_category:
        query = query.filter(WasteEntry.waste_category == waste_category)
    total = query.count()
    items = (
        query.order_by(WasteEntry.created_at.desc(), WasteEntry.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedWasteEntries(
        items=[WasteEntryRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/totals", response_model=ProcessingTotals)
def processing_totals(
    db: DbSession,
    user: Annotated[User, Depends(require_role("operator", "admin"))],
) -> ProcessingTotals:
    query = db.query(WasteEntry)
    if user.role == "operator":
        query = query.filter(WasteEntry.employee_id == user.username)

    total_weight = float(query.with_entities(func.coalesce(func.sum(WasteEntry.quantity), 0)).scalar() or 0)
    entries_count = int(query.with_entities(func.count(WasteEntry.id)).scalar() or 0)
    dry_weight = float(
        query.with_entities(func.coalesce(func.sum(WasteEntry.quantity), 0))
        .filter(WasteEntry.waste_category == "Dry Waste")
        .scalar()
        or 0
    )
    wet_weight = float(
        query.with_entities(func.coalesce(func.sum(WasteEntry.quantity), 0))
        .filter(WasteEntry.waste_category == "Wet Waste")
        .scalar()
        or 0
    )
    return ProcessingTotals(
        entries_count=entries_count,
        total_weight=round(total_weight, 2),
        dry_weight=round(dry_weight, 2),
        wet_weight=round(wet_weight, 2),
    )


@router.get("/status", response_model=WetProcessingStatus)
def wet_status(
    db: DbSession,
    _: Annotated[User, Depends(require_role("operator", "admin"))],
) -> WetProcessingStatus:
    total_wet, compost_deposited, biogas_deposited, compost_distributed = wet_totals(db)
    latest = db.query(WetProcessingUpdate).order_by(WetProcessingUpdate.id.desc()).first()
    latest_distributions = (
        db.query(CompostDistribution)
        .order_by(CompostDistribution.created_at.desc(), CompostDistribution.id.desc())
        .limit(8)
        .all()
    )
    latest_payload = None
    if latest:
        latest_payload = WetProcessingRecord(
            employee_id=latest.employee_id,
            compost_quantity=float(latest.compost_quantity),
            biogas_quantity=float(latest.biogas_quantity),
            total_wet_reference=float(latest.total_wet_reference),
            notes=latest.notes,
            created_at=latest.created_at.isoformat(),
        )
    return WetProcessingStatus(
        total_wet_processed=round(total_wet, 2),
        compost_deposited=round(compost_deposited, 2),
        biogas_deposited=round(biogas_deposited, 2),
        compost_distributed=round(compost_distributed, 2),
        compost_available=round(compost_deposited - compost_distributed, 2),
        latest_update=latest_payload,
        latest_distributions=[CompostDistributionRecord.model_validate(item) for item in latest_distributions],
    )
