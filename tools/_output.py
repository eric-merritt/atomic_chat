"""Standardized tool output format and retry logic."""

import json
import time
import functools


def tool_result(data=None, error: str = "") -> dict:
    """Return a standardized result dict.

    All tools MUST return the output of this function.
    qwen-agent converts dict returns to string automatically.

    Args:
        data: The tool's result payload. Any JSON-serializable value.
        error: Error message. If non-empty, status is "error".

    Returns:
        Dict: {"status": "success"|"error", "data": ..., "error": ""}
    """
    if error:
        return {"status": "error", "data": None, "error": error}
    return {"status": "success", "data": data, "error": ""}


# Status codes that should NOT be retried (client errors — the request itself is wrong)
_NO_RETRY_CODES = {400, 401, 403, 404, 405, 409, 410, 422}


def retry(max_retries=3, delay=2):
    """Retry decorator with exponential backoff and status-code awareness.

    Behavior:
        - Retries on 429 (rate limit) with exponential backoff and Retry-After header support.
        - Retries on 5xx (server errors) with exponential backoff.
        - Does NOT retry on 4xx client errors (400, 401, 403, 404, etc.) — these indicate
          a problem with the request itself, not a transient failure.
        - Retries on network errors (ConnectionError, Timeout, etc.).

    Args:
        max_retries: Maximum number of retry attempts. Default: 3.
        delay: Initial delay in seconds between retries. Doubles each attempt. Default: 2.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            current_delay = delay

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    # Check if the exception has an HTTP status code
                    status_code = _extract_status_code(e)

                    if status_code and status_code in _NO_RETRY_CODES:
                        # Client error — retrying won't help
                        print(f"[{func.__name__}] {status_code} error (not retryable): {e}")
                        raise

                    if status_code == 429:
                        # Rate limited — check for Retry-After header
                        retry_after = _extract_retry_after(e)
                        wait = retry_after if retry_after else current_delay * 2
                        print(f"[{func.__name__}] Rate limited (429). Waiting {wait}s...")
                        time.sleep(wait)
                        current_delay = wait
                        continue

                    # 5xx or network error — retry with exponential backoff
                    print(f"[{func.__name__}] Attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(current_delay)
                        current_delay *= 2

            print(f"[{func.__name__}] Failed after {max_retries} attempts")
            raise last_error
        return wrapper
    return decorator


def _extract_status_code(error: Exception) -> int | None:
    """Extract HTTP status code from various exception types."""
    # requests.exceptions.HTTPError
    if hasattr(error, 'response') and hasattr(error.response, 'status_code'):
        return error.response.status_code
    # urllib.error.HTTPError
    if hasattr(error, 'code'):
        return error.code
    # Selenium WebDriverException doesn't have HTTP codes
    return None


def _extract_retry_after(error: Exception) -> float | None:
    """Extract Retry-After header value from an HTTP error response."""
    # requests.exceptions.HTTPError
    if hasattr(error, 'response') and hasattr(error.response, 'headers'):
        retry_after = error.response.headers.get('Retry-After')
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                return None
    # urllib.error.HTTPError
    if hasattr(error, 'headers'):
        retry_after = error.headers.get('Retry-After')
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                return None
    return None
