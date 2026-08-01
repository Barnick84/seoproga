"""Shared SERP position-checking helpers used by position-checking scripts."""

import logging
import time

from services.xmlriver_client import XmlriverClient
from utils.helpers import extract_domain

logger = logging.getLogger(__name__)

MAX_PAGES = 10
PAGE_SIZE = 10


def check_target(
    client: XmlriverClient,
    query: str,
    engine: str,
    device: str,
    region: int,
    clean_target_domain: str,
) -> tuple[int, str]:
    """Return (position, url) of the target domain in the SERP, or (0, "")."""
    found_pos = 0
    found_url = ""
    for page in range(MAX_PAGES):
        try:
            serp_urls = client.fetch_serp(
                query,
                engine=engine,
                device=device,
                region=region,
                top_n=PAGE_SIZE,
                page=page,
                use_cache=False,
            )
            if not serp_urls:
                break
            for page_pos, url in enumerate(serp_urls, start=1):
                extracted = extract_domain(url)
                if extracted == clean_target_domain or extracted.endswith(
                    "." + clean_target_domain
                ):
                    found_pos = page * PAGE_SIZE + page_pos
                    found_url = url
                    break
            if found_pos > 0:
                break
            time.sleep(1)
        except Exception as e:
            logger.warning("Error checking %s/%s: %s", engine, device, e)
            break
    return found_pos, found_url
