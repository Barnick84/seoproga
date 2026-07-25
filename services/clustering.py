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
    skip_cache_miss: bool = False,
) -> List[Dict]:
    threshold = threshold or Config.SIMILARITY_THRESHOLD
    clusters = initial_clusters or []
    skipped = 0

    next_id = 1
    if clusters:
        next_id = max(c.get("id", 0) for c in clusters) + 1

    for keyword in keywords:
        serp = client.fetch_serp(keyword, use_cache=True)
        if not serp:
            if skip_cache_miss:
                skipped += 1
                continue
            serp = client.fetch_serp(keyword, use_cache=False)
        if not serp:
            skipped += 1
            continue

        assigned = False
        best_cluster = None
        max_sim = 0.0
        
        for cluster in clusters:
            sim = serp_similarity(serp, cluster["serp_representative"])
            if sim >= threshold and sim > max_sim:
                max_sim = sim
                best_cluster = cluster
                
        if best_cluster:
            best_cluster["keywords"].append(keyword)
            best_cluster["serp_representative"] = merge_serps(
                [serp, best_cluster["serp_representative"]]
            )
            assigned = True
        
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

    if skipped:
        print(
            f"⚠️ Кластеризация: {skipped}/{len(keywords)} ключей пропущено (пустой SERP)"
        )

    clusters.sort(key=lambda x: len(x["keywords"]), reverse=True)
    return clusters
