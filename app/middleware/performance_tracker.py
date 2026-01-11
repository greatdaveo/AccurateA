"""
Performance Tracking Middleware

Tracks API response times and request counts
"""
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict, Deque
import threading

from app.utils.logger import logger


class PerformanceTracker:
    """
    Thread-safe performance tracker

    Tracks response times and request counts in memory
    """

    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self.lock = threading.Lock()

        # Response times per endpoint (last N samples)
        self.response_times: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=max_samples)
        )

        # Request counts per endpoint
        self.request_counts: Dict[str, int] = defaultdict(int)

        # Error counts per endpoint
        self.error_counts: Dict[str, int] = defaultdict(int)

        # Status code counts
        self.status_codes: Dict[int, int] = defaultdict(int)

        # Hourly request counts (last 24 hours)
        self.hourly_requests: Deque[tuple] = deque(maxlen=24)
        self._init_hourly_requests()

    def _init_hourly_requests(self):
        """Initialize hourly request tracking"""
        now = datetime.utcnow()
        for i in range(24):
            hour = now - timedelta(hours=23 - i)
            self.hourly_requests.append((hour.replace(minute=0, second=0, microsecond=0), 0))

    def record_request(self, path: str, method: str, duration: float, status_code: int):
        """Record a request"""
        with self.lock:
            endpoint = f"{method} {path}"

            # Record response time
            self.response_times[endpoint].append(duration)

            # Increment request count
            self.request_counts[endpoint] += 1

            # Record errors (4xx and 5xx)
            if status_code >= 400:
                self.error_counts[endpoint] += 1

            # Record status code
            self.status_codes[status_code] += 1

            # Update hourly counts
            self._update_hourly_count()

    def _update_hourly_count(self):
        """Update hourly request count"""
        now = datetime.utcnow()
        current_hour = now.replace(minute=0, second=0, microsecond=0)

        if self.hourly_requests and self.hourly_requests[-1][0] == current_hour:
            # Increment current hour
            hour, count = self.hourly_requests[-1]
            self.hourly_requests[-1] = (hour, count + 1)
        else:
            # New hour
            self.hourly_requests.append((current_hour, 1))

    def get_stats(self) -> dict:
        """Get performance statistics"""
        with self.lock:
            total_requests = sum(self.request_counts.values())
            total_errors = sum(self.error_counts.values())

            # Calculate average response times per endpoint
            avg_response_times = {}
            p95_response_times = {}
            p99_response_times = {}

            for endpoint, times in self.response_times.items():
                if times:
                    sorted_times = sorted(times)
                    avg_response_times[endpoint] = round(sum(times) / len(times) * 1000, 2)

                    # 95th percentile
                    p95_idx = int(len(sorted_times) * 0.95)
                    p95_response_times[endpoint] = round(sorted_times[p95_idx] * 1000, 2) if p95_idx < len(
                        sorted_times) else 0

                    # 99th percentile
                    p99_idx = int(len(sorted_times) * 0.99)
                    p99_response_times[endpoint] = round(sorted_times[p99_idx] * 1000, 2) if p99_idx < len(
                        sorted_times) else 0

            # Overall average response time
            all_times = []
            for times in self.response_times.values():
                all_times.extend(times)

            overall_avg = round(sum(all_times) / len(all_times) * 1000, 2) if all_times else 0

            # Calculate error rate
            error_rate = round((total_errors / total_requests * 100), 2) if total_requests > 0 else 0

            # Top slowest endpoints
            slowest_endpoints = sorted(
                avg_response_times.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]

            # Top busiest endpoints
            busiest_endpoints = sorted(
                self.request_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]

            return {
                "total_requests": total_requests,
                "total_errors": total_errors,
                "error_rate_percent": error_rate,
                "average_response_time_ms": overall_avg,
                "endpoints": {
                    "slowest": [
                        {"endpoint": ep, "avg_ms": ms}
                        for ep, ms in slowest_endpoints
                    ],
                    "busiest": [
                        {"endpoint": ep, "count": count}
                        for ep, count in busiest_endpoints
                    ]
                },
                "response_times": {
                    "average": avg_response_times,
                    "p95": p95_response_times,
                    "p99": p99_response_times
                },
                "status_codes": dict(self.status_codes),
                "hourly_requests": [
                    {
                        "hour": hour.isoformat(),
                        "count": count
                    }
                    for hour, count in list(self.hourly_requests)
                ]
            }


# Global performance tracker
performance_tracker = PerformanceTracker()


class PerformanceMiddleware(BaseHTTPMiddleware):
    """
    Track request performance
    """

    async def dispatch(self, request: Request, call_next):
        # Skip health checks and static files
        if request.url.path in ["/health", "/docs", "/openapi.json"]:
            return await call_next(request)

        # Track request
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time

        # Record metrics
        performance_tracker.record_request(
            path=request.url.path,
            method=request.method,
            duration=duration,
            status_code=response.status_code
        )

        # Add performance header
        response.headers["X-Response-Time"] = f"{duration:.3f}s"

        return response