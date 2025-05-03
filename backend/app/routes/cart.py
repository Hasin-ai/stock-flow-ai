from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.stock_cart import StockCart
from app.schemas.stock_cart import StockCartCreate, StockCartOut
from app.dependencies import get_client_user
from app.models.user import User
from typing import List

router = APIRouter()

@router.post("/", response_model=StockCartOut)
async def add_to_cart(
    cart_item: StockCartCreate,
    current_user: User = Depends(get_client_user),
    db: Session = Depends(get_db)
):
    db_cart = StockCart(user_id=current_user.id, symbol=cart_item.symbol)
    db.add(db_cart)
    db.commit()
    db.refresh(db_cart)
    return db_cart

@router.get("/", response_model=List[StockCartOut])
async def get_cart(
    current_user: User = Depends(get_client_user),
    db: Session = Depends(get_db)
):
    return db.query(StockCart).filter(StockCart.user_id == current_user.id).all()

@router.delete("/{cart_id}", response_model=dict)
async def remove_from_cart(
    cart_id: int,
    current_user: User = Depends(get_client_user),
    db: Session = Depends(get_db)
):
    cart_item = db.query(StockCart).filter(StockCart.id == cart_id, StockCart.user_id == current_user.id).first()
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    db.delete(cart_item)
    db.commit()
    return {"message": "Cart item removed"}