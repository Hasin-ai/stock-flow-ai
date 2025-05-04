from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum

class QueryType(str, Enum):
    SINGLE = "single"
    LIST = "list"
    COMPARISON = "comparison"
    GENERAL = "general"

class StockData(BaseModel):
    symbol: str
    name: str
    current_price: float
    change_percent: float
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    volume: Optional[int] = None
    high_52week: Optional[float] = None
    low_52week: Optional[float] = None
    additional_data: Optional[Dict[str, Any]] = None

class StockQuery(BaseModel):
    query: str
    query_type: QueryType = QueryType.GENERAL
    symbols: Optional[List[str]] = None

class StockResponse(BaseModel):
    query: Optional[str] = None
    response: Optional[str] = None
    data: Optional[List[StockData]] = None
    query_type: QueryType