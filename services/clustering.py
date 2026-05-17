# services/clustering.py
from typing import List, Dict
from collections import defaultdict
from config import Config
from services.xmlriver_client import XmlriverClient


def serp_similarity(urls_a: List[str], urls_b: List[str]) -> float:
    if not urls_a or not urls_b:
        return 0.0

    set_a, set_b = set(urls_a), set(urls_b)
    intersection = set_a & set_b
    union = set_a | set_b

    base_sim = len(intersection) / len(union) if union else 0

    weighted = 0
    max_w = len(urls_a)
    for i, url in enumerate(urls_a):
        if url in urls_b:
            weighted += (max_w - i) / max_w

    max_possible = sum((max_w - i) / max_w for i in range(len(urls_a)))
    weighted_sim = weighted / max_possible if max_possible else 0.0

    return 0.7 * base_sim + 0.3 * weighted_sim


def merge_serps(serps_list: List[List[str]]) -> List[str]:
    scores = defaultdict(float)
    for serps in serps_list:
        for pos, url in enumerate(serps):
            scores[url] += 1 / (pos + 1)
    return sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:30]


def cluster_keywords(
    keywords: List[str],
    client: XmlriverClient,
    threshold: float | None = None,
    initial_clusters: List[Dict] = None,
) -> List[Dict]:
    threshold = threshold or Config.SIMILARITY_THRESHOLD
    clusters = initial_clusters or []

    # Find the starting ID for new clusters
    next_id = 1
    if clusters:
        next_id = max(c.get("id", 0) for c in clusters) + 1

    for i, keyword in enumerate(keywords, 1):
        serp = client.fetch_serp(keyword)
        if not serp:
            continue

        assigned = False
        for cluster in clusters:
            sim = serp_similarity(serp, cluster["serp_representative"])
            if sim >= threshold:
                cluster["keywords"].append(keyword)
                cluster["serp_representative"] = merge_serps(
                    [
                        client.fetch_serp(kw, use_cache=True)
                        for kw in cluster["keywords"]
                    ]
                )
                assigned = True
                break

        if not assigned:
            clusters.append(
                {
                    "id": next_id,
                    "name": keyword,
                    "keywords": [keyword],
                    "serp_representative": serp.copy(),
                    "size": 1,
                }
            )
            next_id += 1

    clusters.sort(key=lambda x: len(x["keywords"]), reverse=True)
    return clusters
