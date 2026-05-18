from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.services.websocket_service import manager
from uuid import UUID

router = APIRouter(tags=["WebSockets"])

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: UUID):
    await manager.connect(websocket, user_id)
    try:
        while True:
            # Receive data from client (if needed)
            data = await websocket.receive_text()
            await manager.send_personal_message(f"You wrote: {data}", user_id)
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
        await manager.broadcast(f"User {user_id} left the chat")
