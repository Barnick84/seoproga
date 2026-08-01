# utils/helpers.py
import os
from urllib.parse import urlparse


def safe_print(*args, **kwargs):
    """Print that ignores BrokenPipeError without corrupting the process stdout.

    Unlike the previous implementation, this does NOT redirect the global stdout
    to /dev/null on a broken pipe — that corrupts long-running processes (e.g.
    FastAPI/worker) for all subsequent output. Instead it suppresses just this
    write.
    """
    try:
        print(*args, **kwargs)
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        try:
            os.write(devnull, b"\n")
        finally:
            os.close(devnull)


def _strip_www(netloc: str) -> str:
    return netloc[4:] if netloc.startswith("www.") else netloc


def _decode_punycode(domain: str) -> str:
    """Decode punycode labels anywhere in the domain (e.g. xn--80ak.xn--p1ai)."""
    if "xn--" not in domain:
        return domain
    try:
        return ".".join(
            label.encode("ascii").decode("idna") if label.startswith("xn--") else label
            for label in domain.split(".")
        )
    except (UnicodeError, ValueError):
        return domain


def extract_domain(url: str) -> str:
    if not url:
        return ""
    if "://" in url:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
    else:
        domain = url.split("/")[0]

    domain = domain.split("@")[-1].lower()
    domain = _strip_www(domain)
    return _decode_punycode(domain)


def clean_url(url: str) -> str:
    if not url or "://" not in url:
        return url or ""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    domain = _strip_www(domain)
    domain = _decode_punycode(domain)
    return f"{domain}{parsed.path}".lower().rstrip("/")


def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b != 0 else default
