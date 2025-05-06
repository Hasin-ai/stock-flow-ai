from sqlalchemy import Column, Integer, String, Enum, Boolean
from sqlalchemy.orm import relationship
from app.database import Base
import enum

class UserRole(str, enum.Enum):
    client = "client"
    admin = "admin"

class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.client)
    approval_status = Column(Enum(ApprovalStatus), nullable=False, default=ApprovalStatus.pending)
    
    # Add these relationships
    activity_logs = relationship("ActivityLog", back_populates="user")
    trade_requests = relationship("TradeRequest", back_populates="user")
    cart_items = relationship("StockCart", back_populates="user")
    
    # Chat message relationships
    sent_messages = relationship("ChatMessage", foreign_keys="ChatMessage.sender_id", back_populates="sender")
    received_messages = relationship("ChatMessage", foreign_keys="ChatMessage.receiver_id", back_populates="receiver")