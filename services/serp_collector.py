import logging

from services.xmlriver_client import XmlriverClient

logger = logging.getLogger(__name__)


def prefetch_for_clustering(
    keywords: list[str],
    client: XmlriverClient,
    on_progress=None,
) -> int:
    total = len(keywords)
    fetched = 0

    for i, kw in enumerate(keywords):
        serp = client.fetch_serp(kw, use_cache=True)
        if serp:
            fetched += 1
        if on_progress:
            on_progress(i + 1, total)

    if fetched < total:
        logger.warning(
            "Prefetch: %s/%s ключей в кэше, %s запрошено из API", fetched, total, total - fetched
        )
    else:
        logger.info("Prefetch: все %s ключей в кэше", total)

    return fetched
