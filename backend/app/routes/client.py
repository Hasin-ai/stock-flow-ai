from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from pydantic import BaseModel
from app.database import get_db
from app.dependencies import get_current_user, get_client_user
from app.models.user import User
from app.models.trade_request import TradeRequest
from app.models.activity_log import ActivityLog
from app.services.alphavantage import fetch_stock_data

router = APIRouter()

class OwnedStockResponse(BaseModel):
    symbol: str
    name: str
    quantity: int
    purchase_price: float
    current_price: float
    market_value: float
    total_cost: float
    profit_loss: float
    profit_loss_percent: float
    last_transaction_date: datetime
    
    class Config:
        orm_mode = True

@router.get("/${userId}?stocks", response_model=List[OwnedStockResponse])
async def get_stocks_by_user_id(
    userId: int = Path(..., description="The ID of the user to fetch stocks for"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all stocks owned by a specific user identified by user_id"""
    
    # Security check: Only allow access if the user is requesting their own data or is an admin
    if current_user.id != userId and current_user.role != "admin":
        raise HTTPException(
            status_code=403, 
            detail="Not authorized to view this user's stock holdings"
        )
    
    # Verify the user exists
    target_user = db.query(User).filter(User.id == userId).first()
    if not target_user:
        raise HTTPException(
            status_code=404,
            detail=f"User with ID {userId} not found"
        )
    
    try:
        # Log this activity
        log_entry = ActivityLog(
            userId=current_user.id,
            action=f"Retrieved stock holdings for user ID {userId}",
            timestamp=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
        
        # Get all approved trade requests for the user
        trades = db.query(TradeRequest).filter(
            TradeRequest.user_id == userId,
            TradeRequest.status == "approved"
        ).all()
        
        # Calculate holdings by aggregating trades
        holdings = {}
        for trade in trades:
            if trade.symbol not in holdings:
                holdings[trade.symbol] = {
                    "quantity": 0,
                    "total_cost": 0.0,
                    "last_transaction_date": trade.request_date
                }
            
            if trade.trade_type == "buy":
                # Add to position
                holdings[trade.symbol]["quantity"] += trade.quantity
                holdings[trade.symbol]["total_cost"] += trade.price * trade.quantity
            elif trade.trade_type == "sell":
                # For sells, reduce quantity and adjust cost basis proportionally
                if holdings[trade.symbol]["quantity"] > 0:
                    # Calculate cost per share
                    cost_per_share = holdings[trade.symbol]["total_cost"] / holdings[trade.symbol]["quantity"]
                    # Reduce quantity
                    holdings[trade.symbol]["quantity"] -= trade.quantity
                    # Reduce cost basis
                    holdings[trade.symbol]["total_cost"] -= cost_per_share * trade.quantity
            
            # Update last transaction date if this trade is more recent
            if trade.request_date > holdings[trade.symbol]["last_transaction_date"]:
                holdings[trade.symbol]["last_transaction_date"] = trade.request_date
        
        # Filter out positions with zero or negative quantity
        holdings = {symbol: data for symbol, data in holdings.items() if data["quantity"] > 0}
        
        if not holdings:
            return []
        
        # Get current prices and build response
        result = []
        for symbol, data in holdings.items():
            try:
                # Fetch current stock data from Alpha Vantage
                stock_data = await fetch_stock_data(symbol)
                current_price = stock_data.current_price
                name = stock_data.name
            except Exception as e:
                # Fallback if API call fails
                current_price = data["total_cost"] / data["quantity"] if data["quantity"] > 0 else 0
                name = f"{symbol} Inc."
            
            # Calculate metrics
            quantity = data["quantity"]
            total_cost = data["total_cost"]
            purchase_price = total_cost / quantity if quantity > 0 else 0
            market_value = quantity * current_price
            profit_loss = market_value - total_cost
            profit_loss_percent = (profit_loss / total_cost) * 100 if total_cost > 0 else 0
            
            result.append(OwnedStockResponse(
                symbol=symbol,
                name=name,
                quantity=quantity,
                purchase_price=purchase_price,
                current_price=current_price,
                market_value=market_value,
                total_cost=total_cost,
                profit_loss=profit_loss,
                profit_loss_percent=profit_loss_percent,
                last_transaction_date=data["last_transaction_date"]
            ))
        
        # Sort by market value (descending)
        result.sort(key=lambda x: x.market_value, reverse=True)
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving stock holdings: {str(e)}"
        )

# Endpoint for clients to get their own stocks
@router.get("/my-stocks", response_model=List[OwnedStockResponse])
async def get_my_stocks(
    current_user: User = Depends(get_client_user),
    db: Session = Depends(get_db)
):
    """Get all stocks owned by the currently authenticated client user"""
    # Reuse the existing endpoint but with the current user's ID
    return await get_stocks_by_user_id(current_user.id, current_user, db)