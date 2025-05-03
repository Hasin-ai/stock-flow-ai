from pydantic import BaseModel, Field
from typing import Literal

class StockCartBase(BaseModel):
    symbol: str
    quantity: int = Field(default=1)  # More explicit default using Field
    price: float = Field(default=0.0)
    trade_type: Literal["buy", "sell"] = Field(default="buy")

class StockCartCreate(StockCartBase):
    pass

class StockCartOut(StockCartBase):
    id: int
    user_id: int

    class Config:
        orm_mode = True