from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User, UserRole, ApprovalStatus
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

@router.get("/pending-registrations", response_model=List[UserOut])
async def get_pending_registrations(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    return db.query(User).filter(
        User.role == UserRole.client,
        User.approval_status == ApprovalStatus.pending
    ).all()

@router.post("/approve-client/{user_id}", response_model=UserOut)
async def approve_client(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        User.id == user_id,
        User.role == UserRole.client,
        User.approval_status == ApprovalStatus.pending
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Pending user registration not found")
    
    user.approval_status = ApprovalStatus.approved
    
    # Log the approval action
    log = ActivityLog(
        user_id=current_user.id,
        action=f"Approved client registration for user {user.email}"
    )
    db.add(log)
    
    db.commit()
    db.refresh(user)
    return user

@router.post("/reject-client/{user_id}", response_model=UserOut)
async def reject_client(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        User.id == user_id,
        User.role == UserRole.client,
        User.approval_status == ApprovalStatus.pending
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Pending user registration not found")
    
    user.approval_status = ApprovalStatus.rejected
    
    # Log the rejection action
    log = ActivityLog(
        user_id=current_user.id,
        action=f"Rejected client registration for user {user.email}"
    )
    db.add(log)
    
    db.commit()
    db.refresh(user)
    return user

@router.post("/clients", response_model=UserOut)
async def create_client(
    user: UserCreate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    try:
        from app.routes.auth import get_password_hash
        db_user = db.query(User).filter(User.email == user.email).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        db_user = db.query(User).filter(User.username == user.username).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Username already taken")
        hashed_password = get_password_hash(user.password)
        
        # Admin-created clients are automatically approved
        db_user = User(
            email=user.email,
            username=user.username,
            hashed_password=hashed_password,
            role=UserRole.client,
            approval_status=ApprovalStatus.approved
        )
        
        db.add(db_user)
        
        # Log the client creation action
        log = ActivityLog(
            user_id=current_user.id,
            action=f"Created new client account for {user.email}"
        )
        db.add(log)
        
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception as e:
        db.rollback()
        print(f"Admin client creation error: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred creating the client")

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