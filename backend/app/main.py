import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.middleware.tenant import TenantMiddleware
from app.middleware.ratelimit import RateLimitAuthMiddleware
from app.api.search import router as search_router
from app.api.bookings import router as bookings_router
from app.api.conversation import router as conversation_router
from app.api.voice import router as voice_router
from app.api.golf import router as golf_router
from app.api.heygen_chat import router as heygen_chat_router
from app.api.foto import router as foto_router
from app.api.booking_confirmation import router as booking_router
from app.api.conductor import router as conductor_router
from app.api.ideas import router as ideas_router
from app.api.trips import router as trips_router
from app.api.cards import router as cards_router
from app.api.voice_conductor import router as voice_conductor_router
from app.api.payments import router as payments_router
from app.api.chats import router as chats_router
from app.services import chat_store

app = FastAPI(
    title="Sasha Travel API",
    description="AI-powered travel platform backend",
    version="0.1.0"
)

# Base allowlist + any extra origins from ALLOWED_ORIGINS env (comma-separated), so a
# new prod domain can be whitelisted without a code change. A frontend origin missing
# from this list is CORS-blocked → every conductor call fails → the avatar goes silent.
_DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",  # local dev fallback port when 3000 is taken by another app
    "https://sasha-travel.vercel.app",
    "https://discover-vietnam.vercel.app",
    "https://sasha-heygen.vercel.app",
    "https://investor.kanoe.ai",
    "https://demo.kanoe.ai",
]
_EXTRA_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

# Starlette applies the LAST-added middleware OUTERMOST. We want CORS outermost so that even
# rejected requests (429/401 from the rate limiter) come back with CORS headers — otherwise
# the browser reports a misleading CORS error instead of the real status. Order of execution
# per request: CORS → Tenant → RateLimit/Auth → route handler.
app.add_middleware(RateLimitAuthMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEFAULT_ORIGINS + _EXTRA_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router)
app.include_router(bookings_router)
app.include_router(conversation_router)
app.include_router(voice_router)
app.include_router(golf_router, prefix="/api/agents", tags=["golf"])
app.include_router(heygen_chat_router, prefix="/api/heygen", tags=["heygen"])
app.include_router(foto_router, prefix="/api", tags=["foto"])
app.include_router(booking_router, prefix="/api/agents", tags=["booking"])
app.include_router(conductor_router, prefix="/api/agents", tags=["conductor"])
app.include_router(ideas_router, prefix="/api/agents", tags=["ideas"])
app.include_router(cards_router, prefix="/api", tags=["cards"])
app.include_router(voice_conductor_router, prefix="/api", tags=["voice"])
app.include_router(payments_router)  # already prefixed /api/payments
app.include_router(chats_router)     # already prefixed /api/chats
app.include_router(trips_router)     # already prefixed /api/trips


@app.on_event("startup")
async def _init_chat_store() -> None:
    """Create the chat-history tables (and seed the demo user) on boot."""
    try:
        await chat_store.init_db()
    except Exception as e:
        print(f"[startup] chat_store init failed (non-fatal): {e}")

@app.get("/")
async def root():
    return {"message": "Sasha Travel API is running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}
