from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.search import router as search_router
from app.api.bookings import router as bookings_router
from app.api.conversation import router as conversation_router
from app.api.voice import router as voice_router
from app.api.golf import router as golf_router

app = FastAPI(
    title="Sasha Travel API",
    description="AI-powered travel platform backend",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://sasha-travel.vercel.app", "https://discover-vietnam.vercel.app", "https://sasha-heygen.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router)
app.include_router(bookings_router)
app.include_router(conversation_router)
app.include_router(voice_router)
app.include_router(golf_router, prefix="/api/agents", tags=["golf"])

@app.get("/")
async def root():
    return {"message": "Sasha Travel API is running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}
