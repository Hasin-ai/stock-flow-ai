from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ChatMessageBase(BaseModel):
    content: str

class ChatMessageCreate(ChatMessageBase):
    receiver_id: int

class ChatMessageOut(ChatMessageBase):
    id: int
    sender_id: int
    receiver_id: int
    content: str
    timestamp: datetime
    is_read: int
    sender_username: Optional[str] = None
    receiver_username: Optional[str] = None

    class Config:
        orm_mode = True

class ChatMessageUpdate(BaseModel):
    is_read: int = 1