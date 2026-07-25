import functools
import time
from typing import Callable, Type


class RetryExhausted(Exception):
    pass


def with_retry(
    max_retries: int = 2,
    base_delay: float = 1.0,
    backoff_factor: float = 3.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_retries:
                        delay = base_delay * (backoff_factor**attempt)
                        if on_retry:
                            on_retry(e, attempt + 1)
                        time.sleep(delay)
            raise RetryExhausted(f"After {max_retries + 1} attempts: {last_exc}") from last_exc

        return wrapper

    return decorator
