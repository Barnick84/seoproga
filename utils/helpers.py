# utils/helpers.py
from urllib.parse import urlparse


def extract_domain(url: str) -> str:
    if not url:
        return ""
    if "://" in url:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
    else:
        domain = url.split("/")[0]
    
    domain = domain.replace("www.", "").lower()
    try:
        return domain.encode("idna").decode("ascii")
    except:
        return domain


def clean_url(url: str) -> str:
    if not url or "://" not in url:
        return url or ""
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "").lower()
    try:
        domain = domain.encode("idna").decode("ascii")
    except:
        pass
    return f"{domain}{parsed.path}".lower().rstrip("/")


def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b != 0 else default
