"""
Health Check & Performance Monitoring
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import psutil
import time

from app.utils.database import get_db, engine

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "service": "accuratea",
        "timestamp": time.time()
    }


@router.get("/db")
async def database_health(db: Session = Depends(get_db)):
    """Check database connectivity"""
    try:
        start = time.time()
        db.execute(text("SELECT 1"))
        elapsed = time.time() - start

        return {
            "status": "healthy",
            "response_time_ms": round(elapsed * 1000, 2),
            "pool_size": engine.pool.size(),
            "checked_out": engine.pool.checkedout()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@router.get("/system")
async def system_health():
    """System resource usage"""
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent
    }