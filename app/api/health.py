"""
Health Check & Performance Monitoring
Public: Basic health check
Admin Only: Detailed diagnostics
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
import psutil
import time
import os
import platform
from datetime import datetime

from app.utils.database import get_db, engine
from app.models.user import User
from app.utils.security import require_admin
from app.utils.logger import logger

router = APIRouter(prefix="/health", tags=["Health"])

# HELPER FUNCTIONS
def safe_cpu_freq():
    """Safely get CPU frequency (not available on all platforms)"""
    try:
        freq = psutil.cpu_freq()
        if freq:
            return round(freq.current, 2)
    except (AttributeError, NotImplementedError, OSError):
        pass
    return None


def safe_disk_io():
    """Safely get disk I/O stats (not available on all platforms)"""
    try:
        disk_io = psutil.disk_io_counters()
        if disk_io:
            return {
                'read_mb': round(disk_io.read_bytes / (1024**2), 2),
                'write_mb': round(disk_io.write_bytes / (1024**2), 2)
            }
    except (AttributeError, NotImplementedError, OSError):
        pass
    return {'read_mb': None, 'write_mb': None}


def safe_network_io():
    """Safely get network I/O stats"""
    try:
        net_io = psutil.net_io_counters()
        if net_io:
            return {
                'sent_mb': round(net_io.bytes_sent / (1024**2), 2),
                'received_mb': round(net_io.bytes_recv / (1024**2), 2),
                'packets_sent': net_io.packets_sent,
                'packets_received': net_io.packets_recv
            }
    except (AttributeError, NotImplementedError, OSError):
        pass
    return {
        'sent_mb': None,
        'received_mb': None,
        'packets_sent': None,
        'packets_received': None
    }


def safe_open_files(process):
    """Safely get open files count"""
    try:
        return len(process.open_files())
    except (AttributeError, NotImplementedError, OSError):
        return None

# PUBLIC ENDPOINTS
@router.get("/")
async def health_check():
    """
    Basic health check - PUBLIC

    Used by monitoring services and load balancers
    """
    return {
        "status": "healthy",
        "service": "accuratea",
        "timestamp": time.time(),
        "version": "1.0.0"
    }

# ADMIN-ONLY ENDPOINTS
@router.get("/detailed")
async def detailed_health(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Detailed health check - ADMIN ONLY

    Comprehensive diagnostics including database, system resources, and environment
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "platform": platform.system(),
        "checks": {}
    }

    # 1. Database Check
    try:
        start = time.time()
        db.execute(text("SELECT 1"))
        elapsed = time.time() - start

        health_status["checks"]["database"] = {
            "status": "healthy",
            "response_time_ms": round(elapsed * 1000, 2),
            "pool_size": engine.pool.size(),
            "checked_out": engine.pool.checkedout(),
            "message": "Database connection successful"
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        logger.error(f"Database health check failed: {e}")

    # 2. System Resources
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        health_status["checks"]["system"] = {
            "status": "healthy" if cpu_percent < 90 and memory.percent < 90 else "warning",
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_available_gb": round(memory.available / (1024**3), 2),
            "disk_percent": disk.percent,
            "disk_free_gb": round(disk.free / (1024**3), 2)
        }

        if cpu_percent > 90 or memory.percent > 90:
            health_status["status"] = "warning"

    except Exception as e:
        health_status["checks"]["system"] = {
            "status": "error",
            "message": str(e)
        }
        logger.error(f"System health check failed: {e}")

    # 3. Environment Check
    health_status["checks"]["environment"] = {
        "status": "healthy",
        "app_env": os.getenv("APP_ENV", "unknown"),
        "debug": os.getenv("DEBUG", "false"),
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "platform_release": platform.release()
    }

    return health_status


@router.get("/db")
async def database_health(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Database health and statistics - ADMIN ONLY

    Detailed database metrics and table statistics
    """
    try:
        # Test connection
        start = time.time()
        db.execute(text("SELECT 1"))
        elapsed = time.time() - start

        # Get database stats
        result = db.execute(text("""
            SELECT 
                COUNT(*) as total_tables,
                pg_size_pretty(pg_database_size(current_database())) as database_size
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)).first()

        # Get connection stats
        connections = db.execute(text("""
            SELECT 
                COUNT(*) as active_connections
            FROM pg_stat_activity 
            WHERE datname = current_database()
        """)).first()

        # Get table row counts
        table_stats = db.execute(text("""
            SELECT 
                schemaname,
                tablename,
                n_live_tup as row_count,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
            FROM pg_stat_user_tables
            ORDER BY n_live_tup DESC
            LIMIT 10
        """)).fetchall()

        return {
            "status": "healthy",
            "response_time_ms": round(elapsed * 1000, 2),
            "pool": {
                "size": engine.pool.size(),
                "checked_out": engine.pool.checkedout(),
                "overflow": engine.pool.overflow(),
                "max_overflow": engine.pool._max_overflow
            },
            "database": {
                "total_tables": result.total_tables,
                "size": result.database_size,
                "active_connections": connections.active_connections
            },
            "top_tables": [
                {
                    "schema": row.schemaname,
                    "table": row.tablename,
                    "rows": row.row_count,
                    "size": row.size
                }
                for row in table_stats
            ]
        }

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system")
async def system_health(
    admin: User = Depends(require_admin)
):
    """
    System resources and performance - ADMIN ONLY

    Detailed CPU, memory, disk, and process metrics
    """
    try:
        # CPU Info
        cpu_count = psutil.cpu_count()
        cpu_percent_total = psutil.cpu_percent(interval=0.5)
        cpu_percent_per_core = psutil.cpu_percent(interval=0.5, percpu=True)
        cpu_freq = safe_cpu_freq()

        # Memory Info
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # Disk Info
        disk = psutil.disk_usage('/')
        disk_io = safe_disk_io()

        # Network Info
        network_io = safe_network_io()

        # Process Info
        process = psutil.Process(os.getpid())
        process_memory = process.memory_info()

        # Boot time
        boot_time = datetime.fromtimestamp(psutil.boot_time())

        return {
            "status": "healthy",
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor() or "Unknown"
            },
            "cpu": {
                "count": cpu_count,
                "physical_cores": psutil.cpu_count(logical=False),
                "logical_cores": psutil.cpu_count(logical=True),
                "percent": round(cpu_percent_total, 2),
                "per_core": [round(p, 2) for p in cpu_percent_per_core],
                "frequency_mhz": cpu_freq
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "percent": memory.percent,
                "free_gb": round(memory.free / (1024**3), 2)
            },
            "swap": {
                "total_gb": round(swap.total / (1024**3), 2),
                "used_gb": round(swap.used / (1024**3), 2),
                "free_gb": round(swap.free / (1024**3), 2),
                "percent": swap.percent
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "percent": disk.percent,
                "read_mb": disk_io['read_mb'],
                "write_mb": disk_io['write_mb']
            },
            "network": {
                "sent_mb": network_io['sent_mb'],
                "received_mb": network_io['received_mb'],
                "packets_sent": network_io['packets_sent'],
                "packets_received": network_io['packets_received']
            },
            "process": {
                "pid": process.pid,
                "memory_mb": round(process_memory.rss / (1024**2), 2),
                "memory_percent": round(process.memory_percent(), 2),
                "cpu_percent": round(process.cpu_percent(interval=0.5), 2),
                "threads": process.num_threads(),
                "created": datetime.fromtimestamp(process.create_time()).isoformat(),
                "open_files": safe_open_files(process),
                "status": process.status()
            },
            "system": {
                "boot_time": boot_time.isoformat(),
                "uptime_seconds": round(time.time() - psutil.boot_time(), 2)
            }
        }

    except Exception as e:
        logger.error(f"System health check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/recent")
async def recent_logs(
    admin: User = Depends(require_admin),
    limit: int = 100
):
    """
    Get recent application logs - ADMIN ONLY

    Returns the last N lines from the application log file
    """
    try:
        log_file = "logs/app.log"

        if not os.path.exists(log_file):
            return {
                "logs": [],
                "message": "No log file found",
                "total_lines": 0,
                "showing": 0
            }

        # Read last N lines efficiently
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            recent = lines[-limit:] if len(lines) > limit else lines

        return {
            "logs": [line.strip() for line in recent],
            "total_lines": len(lines),
            "showing": len(recent),
            "log_file": log_file
        }

    except Exception as e:
        logger.error(f"Failed to read logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def performance_metrics(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Application performance metrics - ADMIN ONLY

    Response times, request counts, error rates
    """
    try:
        # Get transaction counts
        transaction_count = db.execute(text("""
            SELECT COUNT(*) as total FROM transactions
        """)).scalar()

        # Get user counts
        user_count = db.execute(text("""
            SELECT COUNT(*) as total FROM users WHERE deleted_at IS NULL
        """)).scalar()

        # Get recent activity (last 24 hours)
        recent_transactions = db.execute(text("""
            SELECT COUNT(*) as count 
            FROM transactions 
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)).scalar()

        # Get company count
        company_count = db.execute(text("""
            SELECT COUNT(*) as total FROM companies WHERE deleted_at IS NULL
        """)).scalar()

        return {
            "status": "healthy",
            "metrics": {
                "total_transactions": transaction_count or 0,
                "active_users": user_count or 0,
                "total_companies": company_count or 0,
                "transactions_24h": recent_transactions or 0,
                "uptime_seconds": round(time.time() - psutil.boot_time(), 2)
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))