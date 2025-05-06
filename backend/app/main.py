from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, stock_query, pdf, cart, trade, admin, websocket
from app.database import engine, Base
from app.config import settings
from qdrant_client import QdrantClient
from qdrant_client.http import models

app = FastAPI(title="Stock Trading Web Application")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development, restrict for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables for SQLAlchemy
Base.metadata.create_all(bind=engine)

# Initialize Qdrant collections
qdrant_client = QdrantClient(url=settings.qdrant_url)
try:
    qdrant_client.get_collection("stocks")
except Exception:
    qdrant_client.create_collection(
        collection_name="stocks",
        vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE),
    )
try:
    qdrant_client.delete_collection("documents")
except Exception:
    pass

# Create documents collection with 1536 dimensions for Gemini embeddings
qdrant_client.create_collection(
    collection_name="documents",
    vectors_config=models.VectorParams(size=1536, distance=models.Distance.COSINE),
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(stock_query.router, prefix="/api/stock", tags=["Stock Queries"])
app.include_router(pdf.router, prefix="/api/pdf", tags=["PDF Operations"])
app.include_router(cart.router, prefix="/api/cart", tags=["Stock Cart"])
app.include_router(trade.router, prefix="/api/trade", tags=["Trade Requests"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin Operations"])

# WebSocket router is already prefixed with /ws in the router definition
# Just mount it in two ways:
# 1. Mount with /api prefix for REST API endpoints
app.include_router(websocket.router, prefix="/api", tags=["WebSocket API"])
# 2. Mount without additional prefix for WebSocket endpoint
app.include_router(websocket.router, tags=["WebSocket Endpoints"])

@app.on_event("startup")
async def startup_event():
    # Initialize any startup tasks
    pass

@app.get("/")
async def root():
    return {"message": "Stock Trading Web Application API"}