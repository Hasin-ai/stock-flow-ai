from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
import logging
from app.database import get_db
from app.models.stock_cart import StockCart
from app.models.trade_request import TradeRequest
from app.schemas.stock_cart import StockCartCreate, StockCartOut
from app.schemas.trade_request import TradeRequestOut
from app.dependencies import get_client_user
from app.models.user import User
from typing import List, Optional

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

router = APIRouter()

@router.post("/", response_model=StockCartOut)
async def add_to_cart(
    cart_item: StockCartCreate,
    current_user: User = Depends(get_client_user),
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"Adding to cart: {cart_item}")
        db_cart = StockCart(
            user_id=current_user.id, 
            symbol=cart_item.symbol,
            quantity=cart_item.quantity,
            price=cart_item.price,
            trade_type=cart_item.trade_type
        )
        db.add(db_cart)
        db.commit()
        db.refresh(db_cart)
        return db_cart
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding to cart: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error adding to cart: {str(e)}")

@router.get("/", response_model=List[StockCartOut])
async def get_cart(
    current_user: User = Depends(get_client_user),
    db: Session = Depends(get_db)
):
    try:
        logger.debug(f"Getting cart for user {current_user.id}")
        cart_items = db.query(StockCart).filter(StockCart.user_id == current_user.id).all()
        return cart_items
    except Exception as e:
        logger.error(f"Error retrieving cart: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving cart: {str(e)}")

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

@router.post("/place-orders", response_model=List[TradeRequestOut])
async def place_orders_from_cart(
    cart_ids: Optional[List[int]] = Body(None),  # Optional list of specific cart IDs to process
    current_user: User = Depends(get_client_user),
    db: Session = Depends(get_db)
):
    # Query cart items
    cart_query = db.query(StockCart).filter(StockCart.user_id == current_user.id)
    
    # If specific cart IDs provided, filter by those
    if cart_ids:
        cart_query = cart_query.filter(StockCart.id.in_(cart_ids))
    
    cart_items = cart_query.all()
    
    if not cart_items:
        raise HTTPException(status_code=404, detail="No items in cart to place orders for")
    
    # Create trade requests from cart items
    trade_requests = []
    for item in cart_items:
        trade_request = TradeRequest(
            user_id=current_user.id,
            symbol=item.symbol,
            quantity=item.quantity,
            price=item.price,
            trade_type=item.trade_type,
            status="pending"
        )
        db.add(trade_request)
        trade_requests.append(trade_request)
        
        # Optionally remove from cart after creating trade request
        db.delete(item)
    
    db.commit()
    
    # Refresh all trade requests to get their IDs
    for trade_request in trade_requests:
        db.refresh(trade_request)
    
    return trade_requests