from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func

from app.dependencies import DbSession, require_role
from app.models import HousingCollection, User, WasteEntry, WetProcessingUpdate
from app.schemas import (
    PaginatedWasteEntries,
    WasteEntryRead,
    WasteProcessCreate,
    WetProcessingCreate,
    WetProcessingRecord,
    WetProcessingStatus,
)

router = APIRouter(prefix="/processing", tags=["processing"])


@router.post("/waste", response_model=WasteEntryRead)
def process_waste(
    payload: WasteProcessCreate,
    db: DbSession,
    user: Annotated[User, Depends(require_role("operator", "admin"))],
) -> WasteEntryRead:
    collection = db.query(HousingCollection).filter(HousingCollection.id == payload.collection_id).first()
    if not collection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    entry = WasteEntry(
        employee_id=user.username,
        waste_category=payload.waste_category,
        waste_subtype=payload.waste_subtype,
        housing_block=collection.housing_block,
        room_number=collection.room_number,
        quantity=payload.quantity,
        collection_id=collection.id,
    )
    db.add(entry)
    collection.status = "processed"
    collection.processed_at = datetime.now(UTC)
    db.commit()
    db.refresh(entry)
    return WasteEntryRead.model_validate(entry)


@router.post("/wet")
def update_wet_processing(
    payload: WetProcessingCreate,
    db: DbSession,
    user: Annotated[User, Depends(require_role("operator", "admin"))],
) -> dict[str, str]:
    total_wet = float(
        db.query(func.coalesce(func.sum(WasteEntry.quantity), 0))
        .filter(WasteEntry.waste_category == "Wet Waste")
        .scalar()
        or 0
    )
    compost = float(payload.compost_quantity)
    if compost > total_wet:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compost quantity cannot exceed total wet waste processed.",
        )
    update = WetProcessingUpdate(
        employee_id=user.username,
        compost_quantity=compost,
        biogas_quantity=round(total_wet - compost, 2),
        total_wet_reference=total_wet,
        notes=payload.notes,
    )
    db.add(update)
    db.commit()
    return {"message": "Wet processing update saved"}


@router.get("/entries", response_model=PaginatedWasteEntries)
def list_processed_entries(
    db: DbSession,
    _: Annotated[User, Depends(require_role("operator", "admin"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    waste_category: str | None = Query(default=None, alias="wasteCategory"),
) -> PaginatedWasteEntries:
    query = db.query(WasteEntry)
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


@router.get("/status", response_model=WetProcessingStatus)
def wet_status(
    db: DbSession,
    _: Annotated[User, Depends(require_role("operator", "admin"))],
) -> WetProcessingStatus:
    total_wet = float(
        db.query(func.coalesce(func.sum(WasteEntry.quantity), 0))
        .filter(WasteEntry.waste_category == "Wet Waste")
        .scalar()
        or 0
    )
    latest = db.query(WetProcessingUpdate).order_by(WetProcessingUpdate.id.desc()).first()
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
    return WetProcessingStatus(total_wet_processed=round(total_wet, 2), latest_update=latest_payload)
