from pydantic import BaseModel

class StockCartBase(BaseModel):
    symbol: str

class StockCartCreate(StockCartBase):
    pass

class StockCartOut(StockCartBase):
    id: int
    user_id: int

    class Config:
        orm_mode = True