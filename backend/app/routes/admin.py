from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User, UserRole
from app.models.trade_request import TradeRequest, TradeStatus
from app.models.activity_log import ActivityLog
from app.schemas.user import UserCreate, UserOut
from app.schemas.trade_request import TradeRequestOut
from app.dependencies import get_admin_user
from typing import List

router = APIRouter()

@router.get("/clients", response_model=List[UserOut])
async def get_clients(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    return db.query(User).filter(User.role == UserRole.client).all()

@router.post("/clients", response_model=UserOut)
async def create_client(
    user: UserCreate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    from app.routes.auth import get_password_hash
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already taken")
    hashed_password = get_password_hash(user.password)
    db_user = User(
        email=user.email,
        username=user.username,
        hashed_password=hashed_password,
        role=UserRole.client
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.delete("/clients/{user_id}", response_model=dict)
async def delete_client(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.client).first()
    if not user:
        raise HTTPException(status_code=404, detail="Client not found")
    db.delete(user)
    db.commit()
    return {"message": "Client deleted"}

@router.get("/trade-requests", response_model=List[TradeRequestOut])
async def get_trade_requests(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    return db.query(TradeRequest).all()

@router.put("/trade-requests/{trade_id}/status", response_model=TradeRequestOut)
async def update_trade_status(
    trade_id: int,
    status: TradeStatus,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    trade = db.query(TradeRequest).filter(TradeRequest.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade request not found")
    trade.status = status
    db.commit()
    db.refresh(trade)
    return trade

@router.get("/activity-logs", response_model=List[dict])
async def get_activity_logs(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    logs = db.query(ActivityLog).all()
    return [{"id": log.id, "user_id": log.user_id, "action": log.action, "timestamp": log.timestamp} for log in logs]