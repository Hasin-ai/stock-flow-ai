from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.trade_request import TradeRequest
from app.schemas.trade_request import TradeRequestCreate, TradeRequestOut
from app.dependencies import get_client_user
from app.models.user import User
from typing import List

router = APIRouter()

@router.post("/", response_model=TradeRequestOut)
async def create_trade_request(
    trade: TradeRequestCreate,
    current_user: User = Depends(get_client_user),
    db: Session = Depends(get_db)
):
    db_trade = TradeRequest(
        user_id=current_user.id,
        symbol=trade.symbol,
        quantity=trade.quantity,
        price=trade.price,
        trade_type=trade.trade_type,
        status="pending"
    )
    db.add(db_trade)
    db.commit()
    db.refresh(db_trade)
    return db_trade

@router.get("/", response_model=List[TradeRequestOut])
async def get_trade_requests(
    current_user: User = Depends(get_client_user),
    db: Session = Depends(get_db)
):
    return db.query(TradeRequest).filter(TradeRequest.user_id == current_user.id).all()