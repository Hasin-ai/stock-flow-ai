from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User, UserRole, ApprovalStatus
from app.schemas.user import UserCreate, UserOut, Token
from app.dependencies import create_access_token
from passlib.context import CryptContext
from datetime import timedelta

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

@router.post("/register", response_model=UserOut)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    try:
        db_user = db.query(User).filter(User.email == user.email).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        db_user = db.query(User).filter(User.username == user.username).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Username already taken")
        
        # Set the approval status to pending for new client registrations
        approval_status = ApprovalStatus.approved if user.role == UserRole.admin else ApprovalStatus.pending
        
        hashed_password = get_password_hash(user.password)
        
        # Create user with explicit values for all fields
        db_user = User(
            email=user.email,
            username=user.username,
            hashed_password=hashed_password,
            role=user.role,
            approval_status=approval_status
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception as e:
        db.rollback()  # Roll back the transaction on error
        # Log the actual error for debugging
        print(f"Registration error: {str(e)}")
        # Return a more generic error to the client
        raise HTTPException(status_code=500, detail="An error occurred during registration")

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if the user is approved (admins are always approved)
    if user.role == UserRole.client and user.approval_status != ApprovalStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your account is {user.approval_status}. Please wait for admin approval."
        )
    
    access_token = create_access_token(
        data={"sub": user.email, "role": user.role.value, "approval_status": user.approval_status.value},
        expires_delta=timedelta(seconds=3600)
    )
    return {"access_token": access_token, "token_type": "bearer"}