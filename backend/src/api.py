from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.analytics import get_analytics, log_call
import json

app = FastAPI()

# Allow frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/analytics")
async def fetch_analytics():
    """Return analytics data for the dashboard."""
    return get_analytics()

@app.post("/api/webhook")
async def livekit_webhook(event: dict):
    """Receive LiveKit webhook events and log call data."""
    try:
        # This will be called by LiveKit when events happen
        # We'll fill this in Step 3
        print(f"Received webhook: {event}")
        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
EOF