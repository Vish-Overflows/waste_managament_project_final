from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import DbSession, require_role
from app.models import HousingCollection, User
from app.schemas import CollectionCreate, CollectionRead, PaginatedCollections
from app.time_utils import campus_today

router = APIRouter(prefix="/collections", tags=["collections"])


def apply_filters(
    query,
    status: str | None,
    housing_block: str | None,
    date_from: date | None,
    date_to: date | None,
):
    if status:
        query = query.filter(HousingCollection.status == status)
    if housing_block:
        query = query.filter(HousingCollection.housing_block == housing_block)
    if date_from:
        query = query.filter(HousingCollection.collection_date >= date_from)
    if date_to:
        query = query.filter(HousingCollection.collection_date <= date_to)
    return query


@router.post("", response_model=CollectionRead)
def create_collection(
    payload: CollectionCreate,
    db: DbSession,
    user: Annotated[User, Depends(require_role("staff", "admin"))],
) -> CollectionRead:
    collection = HousingCollection(
        employee_id=user.username,
        housing_block=payload.housing_block,
        room_number=payload.room_number,
        collection_date=campus_today(),
        status="collected",
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return CollectionRead.model_validate(collection)


@router.get("/my", response_model=PaginatedCollections)
def my_collections(
    db: DbSession,
    user: Annotated[User, Depends(require_role("staff", "admin"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    housing_block: str | None = Query(default=None, alias="housingBlock"),
    date_from: date | None = Query(default=None, alias="dateFrom"),
    date_to: date | None = Query(default=None, alias="dateTo"),
) -> PaginatedCollections:
    query = db.query(HousingCollection).filter(HousingCollection.employee_id == user.username)
    query = apply_filters(query, status, housing_block, date_from, date_to)
    total = query.count()
    items = (
        query.order_by(HousingCollection.collection_date.desc(), HousingCollection.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedCollections(
        items=[CollectionRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=PaginatedCollections)
def list_collections(
    db: DbSession,
    _: Annotated[User, Depends(require_role("operator", "admin"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    housing_block: str | None = Query(default=None, alias="housingBlock"),
    date_from: date | None = Query(default=None, alias="dateFrom"),
    date_to: date | None = Query(default=None, alias="dateTo"),
) -> PaginatedCollections:
    query = db.query(HousingCollection)
    query = apply_filters(query, status, housing_block, date_from, date_to)
    total = query.count()
    items = (
        query.order_by(HousingCollection.collection_date.desc(), HousingCollection.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedCollections(
        items=[CollectionRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
