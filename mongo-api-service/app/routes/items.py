from fastapi import APIRouter, HTTPException, status
from bson import ObjectId
from datetime import datetime, timezone

from app.database import get_db
from app.models import ItemCreate, ItemUpdate, ItemResponse
from app.logger import get_logger

router = APIRouter(prefix="/items", tags=["items"])
log = get_logger(__name__)

COLLECTION = "items"


def _to_response(doc: dict) -> ItemResponse:
    return ItemResponse(
        id=str(doc["_id"]),
        name=doc["name"],
        description=doc.get("description"),
        value=doc["value"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(body: ItemCreate):
    now = datetime.now(timezone.utc)
    doc = {**body.model_dump(), "created_at": now, "updated_at": now}
    db = get_db()
    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    log.info(f"Created item {result.inserted_id}")
    return _to_response(doc)


@router.get("/", response_model=list[ItemResponse])
async def list_items(skip: int = 0, limit: int = 20):
    db = get_db()
    cursor = db[COLLECTION].find().skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    log.info(f"Listed {len(docs)} items")
    return [_to_response(d) for d in docs]


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: str):
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid item ID")
    db = get_db()
    doc = await db[COLLECTION].find_one({"_id": ObjectId(item_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Item not found")
    log.info(f"Fetched item {item_id}")
    return _to_response(doc)


@router.put("/{item_id}", response_model=ItemResponse)
async def update_item(item_id: str, body: ItemUpdate):
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid item ID")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = datetime.now(timezone.utc)
    db = get_db()
    result = await db[COLLECTION].find_one_and_update(
        {"_id": ObjectId(item_id)},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Item not found")
    log.info(f"Updated item {item_id}")
    return _to_response(result)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: str):
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid item ID")
    db = get_db()
    result = await db[COLLECTION].delete_one({"_id": ObjectId(item_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    log.info(f"Deleted item {item_id}")
