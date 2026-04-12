"""Append-only audit log for financial data write operations."""
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("audit")


def log_write_operation(
    method: str,
    path: str,
    status_code: int,
    user_email: str | None = None,
) -> None:
    """Write a structured audit log entry to stdout.

    Cloud Run captures stdout → Cloud Logging, which is append-only by infrastructure.
    Log format: JSON with timestamp (ISO 8601 UTC), user_email, method, path, status_code.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_email": user_email,
        "method": method,
        "path": path,
        "status_code": status_code,
    }
    logger.info(json.dumps(entry))
