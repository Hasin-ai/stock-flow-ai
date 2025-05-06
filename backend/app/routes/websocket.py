from fastapi import APIRouter, WebSocket, Depends, HTTPException, status
from app.dependencies import get_client_user, get_admin_user, get_current_user, get_token_from_websocket
from app.models.user import User
from app.services.websocket_service import WebSocketService
from app.database import get_db
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.chat_message import ChatMessage
from app.schemas.chat_message import ChatMessageOut, ChatMessageCreate, ChatMessageUpdate
import json

# Explicitly set the prefix to /ws for proper route mounting
router = APIRouter(prefix="/ws")

websocket_service = WebSocketService()

# WebSocket endpoints for both clients and admins
@router.websocket("/chat")
async def chat_websocket(websocket: WebSocket, db: Session = Depends(get_db)):
    try:
        token = await get_token_from_websocket(websocket)
        current_user = await get_current_user(token=token, db=db)
    except Exception as e:
        await websocket.accept()
        await websocket.send_json({
            "error": "Authentication failed",
            "details": str(e)
        })
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    try:
        await websocket_service.connect(websocket, current_user)
        await websocket_service.debug_connection(websocket, token, current_user)
        
        while True:
            data = await websocket.receive_text()
            await websocket_service.process_message(data, current_user, db)
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
    finally:
        websocket_service.disconnect(current_user.id)

# Debug endpoint to test authentication
@router.get("/debug/token", response_model=dict)
async def debug_token(
    current_user: User = Depends(get_current_user),
):
    """Endpoint to check if authentication is working properly"""
    return {
        "auth_status": "success",
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role
    }

# REST API endpoints for chat functionality

# Get available chat partners (for both clients and admins)
@router.get("/chat/partners", response_model=List[dict])
async def get_chat_partners(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return websocket_service.get_chat_partners(current_user, db)

# Get chat history with a specific user
@router.get("/chat/history/{user_id}", response_model=List[ChatMessageOut])
async def get_chat_history(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get all messages between the current user and the specified user
    messages = db.query(ChatMessage).filter(
        ((ChatMessage.sender_id == current_user.id) & (ChatMessage.receiver_id == user_id)) |
        ((ChatMessage.sender_id == user_id) & (ChatMessage.receiver_id == current_user.id))
    ).order_by(ChatMessage.timestamp).all()
    
    # Enhance messages with usernames
    user_cache = {current_user.id: current_user}
    
    # Get the other user if not in cache
    if user_id not in user_cache:
        other_user = db.query(User).filter(User.id == user_id).first()
        if other_user:
            user_cache[user_id] = other_user
    
    result = []
    for msg in messages:
        sender = user_cache.get(msg.sender_id)
        receiver = user_cache.get(msg.receiver_id)
        
        msg_dict = ChatMessageOut(
            id=msg.id,
            sender_id=msg.sender_id,
            receiver_id=msg.receiver_id,
            content=msg.content,
            timestamp=msg.timestamp,
            is_read=msg.is_read,
            sender_username=sender.username if sender else None,
            receiver_username=receiver.username if receiver else None
        )
        result.append(msg_dict)
    
    return result

# Send a message (REST API alternative to WebSocket)
@router.post("/chat/send", response_model=ChatMessageOut)
async def send_message(
    message: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Validate receiver exists
    receiver = db.query(User).filter(User.id == message.receiver_id).first()
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")
    
    # Create the message
    db_message = ChatMessage(
        sender_id=current_user.id,
        receiver_id=message.receiver_id,
        content=message.content
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    
    # Try to send via WebSocket if user is connected
    if websocket_service.connection_manager.is_connected(message.receiver_id):
        message_out = {
            "type": "chat",
            "id": db_message.id,
            "sender_id": db_message.sender_id,
            "receiver_id": db_message.receiver_id,
            "content": db_message.content,
            "timestamp": db_message.timestamp.isoformat(),
            "is_read": db_message.is_read,
            "sender_username": current_user.username
        }
        await websocket_service.connection_manager.send_personal_message(
            json.dumps(message_out), message.receiver_id
        )
    
    return ChatMessageOut(
        id=db_message.id,
        sender_id=db_message.sender_id,
        receiver_id=db_message.receiver_id,
        content=db_message.content,
        timestamp=db_message.timestamp,
        is_read=db_message.is_read,
        sender_username=current_user.username,
        receiver_username=receiver.username
    )

# Mark messages as read
@router.put("/chat/read/{sender_id}", response_model=dict)
async def mark_messages_as_read(
    sender_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Find all unread messages from sender to current user
    messages = db.query(ChatMessage).filter(
        ChatMessage.sender_id == sender_id,
        ChatMessage.receiver_id == current_user.id,
        ChatMessage.is_read == 0
    ).all()
    
    # Mark them as read
    for message in messages:
        message.is_read = 1
    
    db.commit()
    
    # Try to notify sender via WebSocket
    if websocket_service.connection_manager.is_connected(sender_id):
        notification = {
            "type": "read_receipt",
            "reader_id": current_user.id,
            "reader_username": current_user.username
        }
        await websocket_service.connection_manager.send_personal_message(
            json.dumps(notification), sender_id
        )
    
    return {"marked_read": len(messages)}

# Get unread message count
@router.get("/chat/unread/count", response_model=dict)
async def get_unread_message_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    count = db.query(ChatMessage).filter(
        ChatMessage.receiver_id == current_user.id,
        ChatMessage.is_read == 0
    ).count()
    
    return {"unread_count": count}

# Get unread messages grouped by sender
@router.get("/chat/unread", response_model=dict)
async def get_unread_messages(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    unread_messages = db.query(ChatMessage).filter(
        ChatMessage.receiver_id == current_user.id,
        ChatMessage.is_read == 0
    ).all()
    
    # Group by sender
    result = {}
    
    for msg in unread_messages:
        sender_id = msg.sender_id
        
        if sender_id not in result:
            # Get sender info
            sender = db.query(User).filter(User.id == sender_id).first()
            result[sender_id] = {
                "sender_id": sender_id,
                "sender_username": sender.username if sender else "Unknown",
                "messages": [],
                "count": 0
            }
        
        # Add message info
        result[sender_id]["messages"].append({
            "id": msg.id,
            "content": msg.content,
            "timestamp": msg.timestamp.isoformat()
        })
        result[sender_id]["count"] += 1
    
    return {"unread_by_sender": list(result.values())}