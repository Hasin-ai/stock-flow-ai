from fastapi import WebSocket, HTTPException
from typing import Dict, Set, List
import json
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.chat_message import ChatMessage

class ConnectionManager:
    def __init__(self):
        # {user_id: WebSocket}
        self.active_connections: Dict[int, WebSocket] = {}
        # {user_id: set(user_ids)} - to track which users have seen updates from other users
        self.user_connections: Dict[int, Set[int]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        
    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.user_connections:
            del self.user_connections[user_id]
    
    async def send_personal_message(self, message: str, user_id: int):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)
    
    def is_connected(self, user_id: int) -> bool:
        return user_id in self.active_connections

class WebSocketService:
    def __init__(self):
        self.connection_manager = ConnectionManager()
        
    async def connect(self, websocket: WebSocket, user: User):
        await self.connection_manager.connect(websocket, user.id)
        
    def disconnect(self, user_id: int):
        self.connection_manager.disconnect(user_id)
        
    async def handle_chat_message(self, data: dict, sender: User, db: Session):
        try:
            receiver_id = int(data.get("receiver_id"))
            content = data.get("content")
            
            # Create and save message to database
            db_message = ChatMessage(
                sender_id=sender.id,
                receiver_id=receiver_id,
                content=content
            )
            db.add(db_message)
            db.commit()
            db.refresh(db_message)
            
            # Prepare message for sending
            message_out = {
                "type": "chat",
                "id": db_message.id,
                "sender_id": db_message.sender_id,
                "receiver_id": db_message.receiver_id,
                "content": db_message.content,
                "timestamp": db_message.timestamp.isoformat(),
                "is_read": db_message.is_read,
                "sender_username": sender.username
            }
            
            # Send to receiver if they're connected
            if self.connection_manager.is_connected(receiver_id):
                await self.connection_manager.send_personal_message(
                    json.dumps(message_out), receiver_id
                )
            
            # Send a confirmation back to the sender
            message_out["received"] = self.connection_manager.is_connected(receiver_id)
            await self.connection_manager.send_personal_message(
                json.dumps(message_out), sender.id
            )
            
            return db_message
        except Exception as e:
            error_msg = {"type": "error", "content": str(e)}
            await self.connection_manager.send_personal_message(
                json.dumps(error_msg), sender.id
            )
            raise HTTPException(status_code=400, detail=str(e))
            
    async def mark_messages_as_read(self, data: dict, user: User, db: Session):
        try:
            sender_id = int(data.get("sender_id"))
            
            # Find all unread messages from this sender to this user
            messages = db.query(ChatMessage).filter(
                ChatMessage.sender_id == sender_id,
                ChatMessage.receiver_id == user.id,
                ChatMessage.is_read == 0
            ).all()
            
            # Mark them as read
            for message in messages:
                message.is_read = 1
            
            db.commit()
            
            # Notify the original sender that messages were read
            if self.connection_manager.is_connected(sender_id):
                notification = {
                    "type": "read_receipt",
                    "reader_id": user.id,
                    "reader_username": user.username
                }
                await self.connection_manager.send_personal_message(
                    json.dumps(notification), sender_id
                )
                
            return {"marked_read": len(messages)}
        except Exception as e:
            error_msg = {"type": "error", "content": str(e)}
            await self.connection_manager.send_personal_message(
                json.dumps(error_msg), user.id
            )
            raise HTTPException(status_code=400, detail=str(e))
            
    async def process_message(self, data_str: str, user: User, db: Session):
        try:
            data = json.loads(data_str)
            message_type = data.get("type", "chat")
            
            if message_type == "chat":
                return await self.handle_chat_message(data, user, db)
            elif message_type == "read":
                return await self.mark_messages_as_read(data, user, db)
            else:
                error_msg = {"type": "error", "content": f"Unknown message type: {message_type}"}
                await self.connection_manager.send_personal_message(
                    json.dumps(error_msg), user.id
                )
        except json.JSONDecodeError:
            error_msg = {"type": "error", "content": "Invalid JSON"}
            await self.connection_manager.send_personal_message(
                json.dumps(error_msg), user.id
            )
        except Exception as e:
            error_msg = {"type": "error", "content": str(e)}
            await self.connection_manager.send_personal_message(
                json.dumps(error_msg), user.id
            )
            
    # Method to get users for a chat (admins for clients, clients for admins)
    def get_chat_partners(self, user: User, db: Session) -> List[dict]:
        if user.role == "admin":
            # Admins see all approved clients
            partners = db.query(User).filter(User.role == "client", User.approval_status == "approved").all()
        else:
            # Clients see all admins
            partners = db.query(User).filter(User.role == "admin").all()
            
        return [{"id": partner.id, "username": partner.username, "role": partner.role} for partner in partners]