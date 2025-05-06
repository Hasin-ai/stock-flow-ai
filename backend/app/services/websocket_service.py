from fastapi import WebSocket, HTTPException
from typing import Dict, Set, List, Optional, Union
import json
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.chat_message import ChatMessage

class ConnectionManager:
    def __init__(self):
        # Store active connections: {user_id: WebSocket}
        self.active_connections: Dict[int, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, user: User):
        await websocket.accept()
        self.active_connections[user.id] = websocket
    
    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
    
    def is_connected(self, user_id: int) -> bool:
        return user_id in self.active_connections
    
    async def send_personal_message(self, message: str, user_id: int):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)
    
    async def broadcast(self, message: str, exclude_user_id: Optional[int] = None):
        for user_id, connection in self.active_connections.items():
            if exclude_user_id is None or user_id != exclude_user_id:
                await connection.send_text(message)


class WebSocketService:
    def __init__(self):
        self.connection_manager = ConnectionManager()
    
    # Debug connection 
    async def debug_connection(self, websocket: WebSocket, token: str, user: User):
        """Send debug information about the connection"""
        try:
            # Truncate token for security
            truncated_token = token[:10] + "..." if token and len(token) > 10 else None
            
            # Send debug info
            await websocket.send_json({
                "connection_status": "established",
                "user_id": user.id,
                "username": user.username,
                "role": user.role,
                "token_received": bool(token),
                "token_prefix": truncated_token
            })
        except Exception as e:
            print(f"Error sending debug info: {str(e)}")
    
    async def connect(self, websocket: WebSocket, user: User):
        await self.connection_manager.connect(websocket, user)
    
    async def process_message(self, data: str, user: User, db: Session):
        try:
            message_data = json.loads(data)
            
            if message_data.get("type") == "chat":
                # Handle chat message
                receiver_id = message_data.get("receiver_id")
                content = message_data.get("content")
                
                if not receiver_id or not content:
                    return
                
                # Create chat message in the database
                from app.models.chat_message import ChatMessage
                
                db_message = ChatMessage(
                    sender_id=user.id,
                    receiver_id=receiver_id,
                    content=content
                )
                db.add(db_message)
                db.commit()
                db.refresh(db_message)
                
                # Get receiver and sender usernames
                sender = user
                receiver = db.query(User).filter(User.id == receiver_id).first()
                
                # Format the message for sending
                message_out = {
                    "type": "chat",
                    "id": db_message.id,
                    "sender_id": db_message.sender_id,
                    "receiver_id": db_message.receiver_id,
                    "content": db_message.content,
                    "timestamp": db_message.timestamp.isoformat(),
                    "is_read": db_message.is_read,
                    "sender_username": sender.username if sender else None,
                    "receiver_username": receiver.username if receiver else None
                }
                
                # Try to send to the recipient if they're connected
                if self.connection_manager.is_connected(receiver_id):
                    await self.connection_manager.send_personal_message(
                        json.dumps(message_out), receiver_id
                    )
                
                # Send confirmation back to the sender
                await self.connection_manager.send_personal_message(
                    json.dumps(message_out), user.id
                )
                
            elif message_data.get("type") == "read":
                # Handle read receipt
                sender_id = message_data.get("sender_id")
                
                if not sender_id:
                    return
                
                # Mark messages as read in the database
                from app.models.chat_message import ChatMessage
                
                messages = db.query(ChatMessage).filter(
                    ChatMessage.sender_id == sender_id,
                    ChatMessage.receiver_id == user.id,
                    ChatMessage.is_read == 0
                ).all()
                
                for message in messages:
                    message.is_read = 1
                
                db.commit()
                
                # Notify the sender that their messages were read
                if self.connection_manager.is_connected(sender_id):
                    notification = {
                        "type": "read_receipt",
                        "reader_id": user.id,
                        "reader_username": user.username
                    }
                    await self.connection_manager.send_personal_message(
                        json.dumps(notification), sender_id
                    )
        
        except Exception as e:
            print(f"Error processing WebSocket message: {str(e)}")
    
    def disconnect(self, user_id: int):
        self.connection_manager.disconnect(user_id)
    
    def get_chat_partners(self, current_user: User, db: Session) -> List[Dict[str, Union[int, str]]]:
        # For clients, get all admin users
        # For admins, get all client users
        if current_user.role == "admin":
            partners = db.query(User).filter(User.role != "admin").all()
        else:
            partners = db.query(User).filter(User.role == "admin").all()
        
        # Return minimal partner info
        return [
            {
                "id": user.id,
                "username": user.username,
                "role": user.role
            }
            for user in partners
        ]