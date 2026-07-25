import asyncio
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Tuple

import aiohttp
import numpy as np
import requests
from bs4 import BeautifulSoup

from config import Config
from services.xmlriver_client import XmlriverClient
from utils.constants import STOP_WORDS
from utils.helpers import extract_domain

_morph = None


def get_morph():
    global _morph
    if _morph is None:
        import pymorphy3

        _morph = pymorphy3.MorphAnalyzer()
    return _morph


class CustomAnalyzer:
    def __init__(self):
        self.xml_client = XmlriverClient()
        self.excluded_domains = set(Config.EXCLUDED_DOMAINS)
        self.max_workers: int = 5

    def _fetch_serp_positions(self, keywords: List[str]) -> Tuple[List[str], List[float]]:
        """
        Parallel SERP fetch for ALL keywords.
        Returns (urls, avg_positions) tuples aligned 1:1.
        """
        url_scores: Counter = Counter()
        url_positions: Dict[str, List[int]] = {}

        def fetch_one(kw: str):
            try:
                urls = self.xml_client.fetch_serp(kw, use_cache=True)
                return kw, urls
            except Exception:
                return kw, []

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(fetch_one, kw): kw for kw in keywords}
            for future in as_completed(futures):
                _, urls = future.result()
                for pos, url in enumerate(urls):
                    cleaned = extract_domain(url)
                    if cleaned and cleaned not in self.excluded_domains:
                        url_scores[url] += 1
                        if url not in url_positions:
                            url_positions[url] = []
                        url_positions[url].append(pos + 1)

        top_n = Config.CONTENT_ANALYSIS_COMPETITORS
        ranked = sorted(url_scores.items(), key=lambda x: x[1], reverse=True)
        urls: List[str] = []
        avg_positions: List[float] = []
        for url, _ in ranked[:top_n]:
            urls.append(url)
            positions = url_positions.get(url, [10])
            avg_positions.append(sum(positions) / len(positions))
        return urls, avg_positions

    def fetch_competitors(self, keywords: List[str]) -> List[str]:
        urls, _ = self._fetch_serp_positions(keywords)
        return urls

    def clean_string(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\d+", "", text)
        return text.strip()

    def extract_segments(self, html: str) -> Dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(
            ["noindex", "script", "style", "header", "footer", "nav", "aside"]
        ):
            tag.decompose()
        main_content = None
        main_tag = soup.find("main")
        if main_tag and len(main_tag.get_text(strip=True)) > 20:
            main_content = main_tag
        else:
            article_tag = soup.find("article")
            if article_tag and len(article_tag.get_text(strip=True)) > 20:
                main_content = article_tag
        if not main_content:
            main_content = soup.find("main") or soup.find("article")
        content_soup = main_content if main_content else soup
        links = []
        for a in content_soup.find_all("a"):
            links.append(a.get_text(separator=" "))
            a.decompose()
        text = content_soup.get_text(separator=" ")
        return {
            "text": self.clean_string(text),
            "links": self.clean_string(" ".join(links)),
        }

    def extract_meta_and_headers(self, html: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("title")
        desc = soup.find("meta", attrs={"name": "description"})
        desc_content = ""
        if desc:
            content_val = desc.get("content")
            if isinstance(content_val, list):
                desc_content = " ".join(str(v) for v in content_val)
            elif isinstance(content_val, str):
                desc_content = content_val
        headers = {}
        for i in range(1, 7):
            h_tags = [h.get_text(separator=" ").strip() for h in soup.find_all(f"h{i}")]
            if h_tags:
                headers[f"h{i}"] = h_tags
        return {
            "title": title.get_text().strip() if title else "",
            "description": desc_content.strip(),
            "headers": headers,
        }

    def get_lemmas(self, text: str) -> List[Tuple[str, str]]:
        """Tokenize, lemmatize, return list of (lemma, POS) tuples."""
        words = re.findall(r"[а-яА-ЯёЁ]+", text.lower())
        result: List[Tuple[str, str]] = []
        for word in words:
            if word in STOP_WORDS or len(word) < 3:
                continue
            p = get_morph().parse(word)[0]
            if p.tag.POS in ("PREP", "CONJ", "PRCL", "INTJ", "NPRO"):
                continue
            pos = str(p.tag.POS) if p.tag.POS else "UNKN"
            result.append((p.normal_form, pos))
        return result

    def get_lemmas_flat(self, text: str) -> List[str]:
        return [lemma for lemma, _ in self.get_lemmas(text)]

    def calculate_complexity_metrics(self, lemmas_flat: List[str], text: str) -> Dict[str, Any]:
        if not lemmas_flat:
            return {"stuffing": 0, "wateriness": 0, "zipf": 0}
        counts = Counter(lemmas_flat)
        top_word_count = counts.most_common(1)[0][1] if counts else 0
        academic_stuffing = round((top_word_count / len(lemmas_flat)) * 100, 2)
        all_words = re.findall(r"[а-яА-ЯёЁ]+", text.lower())
        stop_words_count = sum(1 for w in all_words if w in STOP_WORDS or len(w) < 3)
        wateriness = round((stop_words_count / len(all_words)) * 100, 2) if all_words else 0
        zipf_score = 100
        if len(counts) >= 10:
            top_10 = [c for w, c in counts.most_common(10)]
            ideal = [top_10[0] / (i + 1) for i in range(10)]
            diffs = [abs(top_10[i] - ideal[i]) / ideal[0] for i in range(10)]
            zipf_score = max(0, int(100 - (sum(diffs) * 10)))
        return {
            "academic_stuffing": academic_stuffing,
            "wateriness": wateriness,
            "zipf": zipf_score,
        }

    def generate_ngrams(self, lemmas_with_pos: List[Tuple[str, str]], n: int) -> Dict[str, int]:
        """
        Generate n-grams, keeping only windows containing at least one NOUN.
        """
        if len(lemmas_with_pos) < n:
            return {}
        ngrams = []
        for i in range(len(lemmas_with_pos) - n + 1):
            window = lemmas_with_pos[i : i + n]
            if any(pos == "NOUN" for _, pos in window):
                ngrams.append(" ".join(lemma for lemma, _ in window))
        return {k: v for k, v in Counter(ngrams).items() if v >= 2}

    def get_intent(self, lemmas_flat: List[str], raw_words: List[str] | None = None) -> str:
        comm_markers = {
            "цена",
            "купить",
            "заказать",
            "стоимость",
            "интернет-магазин",
            "прайс",
            "недорого",
            "каталог",
            "доставка",
            "скидка",
            "продажа",
            "оптом",
            "розница",
            "рассрочка",
            "кредит",
            "акция",
            "скидки",
        }
        info_markers = {
            "как",
            "почему",
            "обзор",
            "что",
            "инструкция",
            "совет",
            "рейтинг",
            "своими руками",
            "что такое",
            "как выбрать",
            "отличие",
            "сравнение",
            "пример",
            "особенности",
            "виды",
            "характеристики",
            "способы",
            "методы",
        }
        combined_tokens = lemmas_flat + (raw_words if raw_words else [])
        combined_lower = [t.lower().strip() for t in combined_tokens]
        comm_score = 0
        info_score = 0
        for token in combined_lower:
            if token in comm_markers:
                comm_score += 1
            if token in info_markers:
                info_score += 1
        if comm_score > info_score:
            return "Коммерческий"
        if info_score > comm_score:
            return "Информационный"
        return "Смешанный"

    def run_technical_audit(self, html: str, url: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        is_https = url.startswith("https://")
        has_schema = bool(
            soup.find(attrs={"itemtype": True})
            or soup.find(attrs={"itemscope": True})
            or soup.find("script", type="application/ld+json")
        )
        h_tags = []
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            h_tags.append(tag.name)
        hierarchy_ok = True
        if h_tags:
            for i in range(len(h_tags) - 1):
                curr_level = int(h_tags[i][1])
                next_level = int(h_tags[i + 1][1])
                if next_level > curr_level + 1:
                    hierarchy_ok = False
                    break
        images = soup.find_all("img")
        images_with_alt = [img for img in images if img.get("alt")]
        alt_coverage = (len(images_with_alt) / len(images) * 100) if images else 100
        has_article_tag = bool(soup.find("article") or soup.find("main"))
        return {
            "https": is_https,
            "schema": has_schema,
            "header_hierarchy": hierarchy_ok,
            "alt_tags": {
                "total": len(images),
                "with_alt": len(images_with_alt),
                "percent": round(alt_coverage, 1),
            },
            "semantic_markup": has_article_tag,
        }

    def analyze_content(self, html: str, url: str = "") -> Dict[str, Any]:
        segments = self.extract_segments(html)
        meta = self.extract_meta_and_headers(html)
        tech_audit = self.run_technical_audit(html, url)

        lemmas_text = self.get_lemmas(segments["text"])
        lemmas_links = self.get_lemmas(segments["links"])
        lemmas_all = lemmas_text + lemmas_links
        lemmas_all_flat = [x for x, _ in lemmas_all]

        counts_text = Counter(x for x, _ in lemmas_text)
        counts_links = Counter(x for x, _ in lemmas_links)
        counts_all = Counter(lemmas_all_flat)

        full_text = segments["text"] + " " + segments["links"]
        all_words = re.findall(r"[а-яА-ЯёЁ]+", full_text.lower())

        complexity = self.calculate_complexity_metrics(lemmas_all_flat, full_text)
        intent = self.get_intent(lemmas_all_flat, all_words)

        bigrams = self.generate_ngrams(lemmas_all, 2)
        trigrams = self.generate_ngrams(lemmas_all, 3)

        return {
            "url": url,
            "meta": meta,
            "tech_audit": tech_audit,
            "intent": intent,
            "counts": {
                "all": dict(counts_all),
                "text": dict(counts_text),
                "links": dict(counts_links),
            },
            "ngrams": {"bigrams": bigrams, "trigrams": trigrams},
            "metrics": {
                "characters_with_spaces": len(segments["text"]) + len(segments["links"]),
                "characters_without_spaces": len(
                    (segments["text"] + segments["links"]).replace(" ", "")
                ),
                "words_total": len(lemmas_all_flat),
                "words_unique": len(counts_all),
                **complexity,
            },
        }

    def _fetch_target_content(self, target_url: str, raw_html: str | None = None) -> Dict[str, Any]:
        target_data = None
        if raw_html:
            try:
                target_data = self.analyze_content(raw_html, target_url)
            except Exception as e:
                print(f"[ERROR] Error analyzing provided raw_html: {e}", file=sys.stderr)
        if not target_data:
            try:
                fetch_url = target_url
                try:
                    from urllib.parse import urlparse

                    parsed = urlparse(target_url)
                    if parsed.netloc:
                        puny_netloc = parsed.netloc.encode("idna").decode("ascii")
                        fetch_url = target_url.replace(parsed.netloc, puny_netloc)
                except Exception:
                    pass
                print(f"[INFO] Fetching target {fetch_url}", file=sys.stderr)
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                }
                resp = requests.get(fetch_url, timeout=20, headers=headers)
                resp.raise_for_status()
                if resp.encoding and resp.encoding.lower() == "iso-8859-1":
                    resp.encoding = resp.apparent_encoding
                target_data = self.analyze_content(resp.text, target_url)
            except Exception as e:
                print(f"[ERROR] Error fetching target {target_url}: {e}", file=sys.stderr)
                target_data = self.analyze_content("<html></html>", target_url)
        return target_data

    def _resolve_competitors(
        self, keywords: List[str], competitor_urls: List[str] | None = None
    ) -> Tuple[List[str], List[float]]:
        if competitor_urls is not None:
            return competitor_urls, [1.0] * len(competitor_urls)
        return self._fetch_serp_positions(keywords)

    def _fetch_competitors_data(self, urls: List[str]) -> List[Dict]:
        async def _fetch_and_analyze(url: str, session: aiohttp.ClientSession) -> Dict | None:
            try:
                if not url.startswith("http"):
                    url = "https://" + url
                print(f"   Analyzing {url}...", file=sys.stderr)
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=15),
                    headers={"User-Agent": "Mozilla/5.0"},
                ) as response:
                    response.raise_for_status()
                    text = await response.text(errors="replace")
                    return self.analyze_content(text, url)
            except Exception as e:
                print(f"   [WARN] Error analyzing {url}: {e}", file=sys.stderr)
                return None

        async def _fetch_all(urls: List[str]) -> List[Dict]:
            connector = aiohttp.TCPConnector(limit=10)
            async with aiohttp.ClientSession(connector=connector) as session:
                tasks = [_fetch_and_analyze(u, session) for u in urls]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                return [r for r in results if isinstance(r, dict)]

        return asyncio.run(_fetch_all(urls))

    @staticmethod
    def _align_competitor_weights(
        comp_urls: List[str],
        competitor_weights: List[float],
        comp_results: List[Dict],
    ) -> List[float]:
        aligned: List[float] = []
        comp_idx = 0
        for i in range(len(comp_urls)):
            if comp_idx < len(comp_results) and comp_results[comp_idx].get("url"):
                aligned.append(competitor_weights[i] if i < len(competitor_weights) else 1.0)
                comp_idx += 1
        return aligned

    def _build_keyword_analysis(
        self,
        target_data: Dict,
        keywords: List[str],
        comp_results: List[Dict],
        aligned_weights: List[float],
    ) -> Tuple[Counter, List[Dict]]:
        target_keyword_lemmas: List[str] = []
        for kw in keywords:
            target_keyword_lemmas.extend(self.get_lemmas_flat(kw))
        all_comp_words = Counter()
        for c in comp_results:
            all_comp_words.update(c["counts"]["all"].keys())
        popular_lemmas = [lemma for lemma, count in all_comp_words.items() if count >= 2]
        analysis_lemmas = sorted(set(target_keyword_lemmas) | set(popular_lemmas))
        total_weight = sum(aligned_weights) if aligned_weights else len(comp_results)
        final_keywords = []
        for lemma in analysis_lemmas:
            comp_vals_all = [c["counts"]["all"].get(lemma, 0) for c in comp_results]
            median_all = int(np.median(comp_vals_all)) if comp_vals_all else 0
            target_all = target_data["counts"]["all"].get(lemma, 0)
            sites_count = sum(1 for v in comp_vals_all if v > 0)
            pop_score = round((sites_count / len(comp_results)) * 100, 1) if comp_results else 0
            weighted_pop = 0.0
            for i, v in enumerate(comp_vals_all):
                if v > 0 and i < len(aligned_weights):
                    weighted_pop += aligned_weights[i]
            weighted_popularity = (
                round((weighted_pop / total_weight) * 100, 1) if aligned_weights else pop_score
            )
            final_keywords.append(
                {
                    "lemma": lemma,
                    "popularity": pop_score,
                    "weighted_popularity": weighted_popularity,
                    "sites_count": sites_count,
                    "median": median_all,
                    "current": target_all,
                    "diff": median_all - target_all,
                }
            )
        return all_comp_words, final_keywords

    @staticmethod
    def _build_ngram_analysis(
        comp_results: List[Dict], target_data: Dict, field: str
    ) -> List[Dict]:
        all_comp = Counter()
        for c in comp_results:
            all_comp.update(c["ngrams"][field].keys())
        popular = [phrase for phrase, count in all_comp.items() if count >= 2]
        res = []
        for phrase in popular:
            vals = [c["ngrams"][field].get(phrase, 0) for c in comp_results]
            median = int(np.median(vals))
            current = target_data["ngrams"][field].get(phrase, 0)
            if median > 0 or current > 0:
                res.append(
                    {
                        "phrase": phrase,
                        "median": median,
                        "current": current,
                        "diff": median - current,
                    }
                )
        return sorted(res, key=lambda x: x["median"], reverse=True)[:30]

    @staticmethod
    def _build_top_20_density(
        all_comp_words: Counter, comp_results: List[Dict], target_data: Dict
    ) -> List[Dict]:
        top_20_words = all_comp_words.most_common(20)
        top_20_stats = []
        for lemma, _ in top_20_words:
            comp_densities = [
                (c["counts"]["all"].get(lemma, 0) / c["metrics"]["words_total"] * 100)
                if c["metrics"]["words_total"] > 0
                else 0
                for c in comp_results
            ]
            median_density = round(np.median(comp_densities), 2) if comp_densities else 0
            target_density = round(
                (
                    target_data["counts"]["all"].get(lemma, 0)
                    / target_data["metrics"]["words_total"]
                    * 100
                )
                if target_data["metrics"]["words_total"] > 0
                else 0,
                2,
            )
            top_20_stats.append(
                {
                    "lemma": lemma,
                    "median_density": median_density,
                    "target_density": target_density,
                }
            )
        return top_20_stats

    def _get_popular_meta_words(self, comp_results: List[Dict], field: str) -> List[str]:
        meta_lemmas: List[str] = []
        for c in comp_results:
            text = c["meta"].get(field, "")
            meta_lemmas.extend(self.get_lemmas_flat(text))
        return [word for word, _ in Counter(meta_lemmas).most_common(15)]

    @staticmethod
    def _build_competitor_median_metrics(comp_results: List[Dict]) -> Dict[str, Any]:
        if not comp_results:
            return {
                "characters_with_spaces": 0,
                "characters_without_spaces": 0,
                "words_total": 0,
                "words_unique": 0,
                "academic_stuffing": 0,
                "wateriness": 0,
                "zipf": 0,
            }
        return {
            "characters_with_spaces": int(
                np.median([c["metrics"]["characters_with_spaces"] for c in comp_results])
            ),
            "characters_without_spaces": int(
                np.median([c["metrics"]["characters_without_spaces"] for c in comp_results])
            ),
            "words_total": int(np.median([c["metrics"]["words_total"] for c in comp_results])),
            "words_unique": int(np.median([c["metrics"]["words_unique"] for c in comp_results])),
            "academic_stuffing": round(
                np.median([c["metrics"]["academic_stuffing"] for c in comp_results]), 2
            ),
            "wateriness": round(np.median([c["metrics"]["wateriness"] for c in comp_results]), 2),
            "zipf": int(np.median([c["metrics"]["zipf"] for c in comp_results])),
        }

    @staticmethod
    def _build_report(
        target_url: str,
        target_data: Dict,
        comp_results: List[Dict],
        final_keywords: List[Dict],
        final_bigrams: List[Dict],
        final_trigrams: List[Dict],
        top_20_stats: List[Dict],
        title_popular: List[str],
        description_popular: List[str],
    ) -> Dict[str, Any]:
        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "target_url": target_url,
                "competitors_count": len(comp_results),
            },
            "text_metrics": {
                "target": target_data["metrics"],
                "competitors_median": CustomAnalyzer._build_competitor_median_metrics(comp_results),
            },
            "tech_audit": {
                "target": target_data["tech_audit"],
                "competitors": [c["tech_audit"] for c in comp_results],
            },
            "intent": {
                "target": target_data["intent"],
                "competitors": [c["intent"] for c in comp_results],
            },
            "keywords": final_keywords,
            "bigrams": final_bigrams,
            "trigrams": final_trigrams,
            "top_20_density": top_20_stats,
            "meta_analysis": {
                "title_popular_words": title_popular,
                "description_popular_words": description_popular,
            },
            "competitors_details": [
                {
                    "url": c["url"],
                    "metrics": c["metrics"],
                    "meta": c["meta"],
                    "intent": c["intent"],
                    "tech_audit": c["tech_audit"],
                }
                for c in comp_results
            ],
            "target_meta": target_data["meta"],
        }

    def process_analysis(
        self,
        target_url: str,
        keywords: List[str],
        raw_html: str | None = None,
        competitor_urls: List[str] | None = None,
    ) -> Dict[str, Any]:
        print(f"[INFO] Starting analysis for {target_url}", file=sys.stderr)

        target_data = self._fetch_target_content(target_url, raw_html)
        comp_urls, competitor_weights = self._resolve_competitors(keywords, competitor_urls)
        print(f"[INFO] Found {len(comp_urls)} competitors", file=sys.stderr)

        comp_results = self._fetch_competitors_data(comp_urls)
        aligned_weights = self._align_competitor_weights(
            comp_urls, competitor_weights, comp_results
        )

        all_comp_words, final_keywords = self._build_keyword_analysis(
            target_data, keywords, comp_results, aligned_weights
        )
        final_bigrams = self._build_ngram_analysis(comp_results, target_data, "bigrams")
        final_trigrams = self._build_ngram_analysis(comp_results, target_data, "trigrams")
        top_20_stats = self._build_top_20_density(all_comp_words, comp_results, target_data)

        title_popular = self._get_popular_meta_words(comp_results, "title")
        description_popular = self._get_popular_meta_words(comp_results, "description")

        return self._build_report(
            target_url,
            target_data,
            comp_results,
            final_keywords,
            final_bigrams,
            final_trigrams,
            top_20_stats,
            title_popular,
            description_popular,
        )


if __name__ == "__main__":
    analyzer = CustomAnalyzer()
    res = analyzer.process_analysis("https://piter-trevel.ru/", ["экскурсии в пятигорске"])
    print(json.dumps(res, indent=2, ensure_ascii=False))
