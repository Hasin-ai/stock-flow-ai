from sqlalchemy import Column, Integer, String, Float, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
import enum

class TradeStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    declined = "declined"

class TradeRequest(Base):
    __tablename__ = "trade_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String, nullable=False)
    name = Column(String, nullable=True)  # Stock name
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    trade_type = Column(String, nullable=False)  # "buy" or "sell"
    status = Column(Enum(TradeStatus), nullable=False, default=TradeStatus.pending)

    user = relationship("User", back_populates="trade_requests")