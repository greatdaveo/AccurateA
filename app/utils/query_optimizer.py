"""
Query Optimization Utilities
Helpers for efficient database queries.
"""
from functools import wraps
from time import time
from app.utils.logger import logger


def log_query_time(func):
    """
    Decorator to log query execution time

    Usage:
    @log_query_time
    def my_query_function():
        ...
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time()
        result = func(*args, **kwargs)
        elapsed = time() - start

        if elapsed > 1.0:  # Log slow queries (> 1 second)
            logger.warning(f"Slow query in {func.__name__}: {elapsed:.2f}s")
        else:
            logger.debug(f"Query {func.__name__}: {elapsed:.3f}s")

        return result

    return wrapper


def batch_query(items, batch_size=100):
    """
    Process items in batches to avoid memory issues

    Usage:
    for batch in batch_query(large_list, batch_size=50):
        process(batch)
    """
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]