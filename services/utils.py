"""
Vostok Web Terminal – Shared Utilities
=======================================
Common helpers used across service modules: retry logic, money conversions,
and timezone constants.
"""

import os
from datetime import timezone, timedelta
from decimal import Decimal
from typing import Optional

# ---------------------------------------------------------------------------
# Timezone: Moscow Time (UTC+3 / GMT+3)
# ---------------------------------------------------------------------------
MSK = timezone(timedelta(hours=3))

# ---------------------------------------------------------------------------
# Retry Logic (shared between market.py and portfolio.py)
# ---------------------------------------------------------------------------
MAX_RETRIES = 4
RETRYABLE_ERROR_MARKERS = (
    "RESOURCE_EXHAUSTED",
    "INTERNAL",
    "UNAVAILABLE",
    "DEADLINE_EXCEEDED",
)


def is_retryable_api_error(exc: Exception) -> bool:
    """Check if an API exception is retryable (rate limit, transient error)."""
    err = str(exc).upper()
    return any(marker in err for marker in RETRYABLE_ERROR_MARKERS)


def retry_wait_seconds(exc: Exception, attempt: int, base: int = 2, cap: int = 20) -> int:
    """Calculate exponential backoff wait time, respecting rate-limit reset headers.

    Tries both async (aio) and sync (gRPC) metadata extractors so the same
    function works for both client types.
    """
    wait = min(cap, base * (2 ** attempt))
    # Try async metadata first (for AsyncClient callers)
    try:
        from t_tech.invest.logging import get_metadata_from_aio_error

        metadata = get_metadata_from_aio_error(exc)
        if metadata and metadata.ratelimit_reset:
            wait = max(wait, int(metadata.ratelimit_reset) + 1)
            return wait
    except Exception:
        pass
    # Try sync gRPC metadata (for Client callers)
    try:
        from t_tech.invest.logging import get_metadata_from_grpc_error

        metadata = get_metadata_from_grpc_error(exc)
        if metadata and metadata.ratelimit_reset:
            wait = max(wait, int(metadata.ratelimit_reset) + 1)
    except Exception:
        pass
    return wait


# ---------------------------------------------------------------------------
# Money / Quantity Conversion Helpers
# ---------------------------------------------------------------------------

def money_to_float(money_obj) -> float:
    """Convert a T-Bank MoneyValue/Quotation to float safely.

    Handles objects with ``.units`` and ``.nano`` attributes.
    Returns 0.0 if the object is None or malformed.
    """
    if money_obj is None:
        return 0.0
    units = getattr(money_obj, "units", None)
    nano = getattr(money_obj, "nano", None)
    if units is None:
        return 0.0
    return float(units) + (float(nano) / 1e9 if nano else 0.0)


def quantity_to_float(qty_obj) -> float:
    """Convert a T-Bank Quotation (quantity) to float, including nano part.

    Unlike the previous code that ignored ``.nano``, this properly
    handles fractional shares.
    """
    if qty_obj is None:
        return 0.0
    units = getattr(qty_obj, "units", None)
    nano = getattr(qty_obj, "nano", None)
    if units is None:
        return 0.0
    return float(units) + (float(nano) / 1e9 if nano else 0.0)


def float_to_quotation(value: float):
    """Convert a float price to a Quotation using Decimal to avoid float artifacts.

    Example: ``99.99`` → ``Quotation(units=99, nano=990000000)``
    """
    from t_tech.invest import Quotation

    d = Decimal(str(value))
    units = int(d)
    nano = int((d - units) * Decimal("1000000000"))
    return Quotation(units=units, nano=nano)


def get_account_id_from_config() -> Optional[str]:
    """Resolve the target account ID from environment or Streamlit secrets.

    Priority:
      1. ``INVEST_ACCOUNT_ID`` environment variable
      2. Streamlit secrets
      3. ``None`` (auto-detect first brokerage account)
    """
    env_id = os.getenv("INVEST_ACCOUNT_ID", "").strip()
    if env_id:
        return env_id

    try:
        import streamlit as st

        secret_id = st.secrets.get("INVEST_ACCOUNT_ID", "").strip()
        if secret_id:
            return secret_id
    except Exception:
        pass

    return None
