"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Returns service health status. No authentication required."""
    return {"status": "ok"}
