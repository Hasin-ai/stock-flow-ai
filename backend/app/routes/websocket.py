from fastapi import APIRouter, WebSocket, Depends
from app.dependencies import get_client_user
from app.models.user import User
from app.services.websocket_service import WebSocketService

router = APIRouter()

websocket_service = WebSocketService()

@router.websocket("/stock-updates")
async def websocket_endpoint(websocket: WebSocket, current_user: User = Depends(get_client_user)):
    await websocket_service.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle client messages if needed
            await websocket_service.broadcast(data)
    except Exception:
        websocket_service.disconnect(websocket)