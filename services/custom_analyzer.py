# services/custom_analyzer.py
import requests
from bs4 import BeautifulSoup
import re
import pymorphy3
from collections import Counter
import numpy as np
from typing import List, Dict, Any
import json
from datetime import datetime
import sys


from config import Config
from services.xmlriver_client import XmlriverClient
from utils.helpers import extract_domain

morph = pymorphy3.MorphAnalyzer()

STOP_WORDS = {
        "и", "в", "во", "не", "на", "с", "со", "что", "как", "я", "он", "нас", "они", "все", "она", "так", "его", "но", "да", "ты", "от", "у", "же", "вы", "за", "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из", "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть", "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам", "сказал", "ведь", "там", "потом", "себя", "ничего", "ей", "может", "они", "тут", "где", "есть", "надо", "ней", "для", "мы", "тебя", "их", "чем", "была", "сам", "чтоб", "без", "будто", "чего", "раз", "тоже", "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому", "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти", "мой", "тем", "чтобы", "нее", "сейчас", "были", "куда", "зачем", "всех", "никогда", "можно", "при", "наконец", "свою", "после", "эту", "моя", "через", "эти", "нас", "про", "всего", "тех", "какая", "разве", "через", "хотя", "этой", "перед", "иногда", "лучше", "чуть", "том", "нельзя", "такой", "им", "более", "всегда", "конечно", "всю", "между", "это", "был", "будет", "было", "были", "быть", "в", "весь", "во", "вот", "все", "всей", "вы", "говорить", "да", "для", "до", "еще", "же", "за", "и", "из", "или", "к", "как", "ко", "когда", "кто", "на", "не", "него", "нее", "ней", "нет", "ни", "них", "но", "о", "об", "один", "он", "она", "они", "оно", "от", "откуда", "перед", "по", "под", "после", "потому", "почему", "при", "про", "раз", "с", "свое", "свой", "себя", "сказать", "со", "так", "такой", "там", "те", "тебя", "то", "тогда", "тоже", "только", "том", "тот", "тут", "ты", "у", "уж", "хотеть", "хотя", "чего", "чей", "чем", "что", "чтоб", "чтобы", "чуть", "эти", "это", "этот",
}

class CustomAnalyzer:
    def __init__(self):
        self.xml_client = XmlriverClient()
        self.excluded_domains = set(Config.EXCLUDED_DOMAINS)

    def fetch_competitors(self, keywords: List[str]) -> List[str]:
        """Fetch top competitors from XMLRiver, excluding specified domains."""
        all_urls = []
        # Use only first 3 keywords to avoid too many requests
        for kw in keywords[:3]:
            urls = self.xml_client.fetch_serp(kw)
            all_urls.extend(urls)
        
        unique_urls = list(dict.fromkeys(all_urls))
        filtered_urls = []
        for url in unique_urls:
            domain = extract_domain(url)
            if domain and domain not in self.excluded_domains:
                filtered_urls.append(url)
            if len(filtered_urls) >= 10:
                break
        
        return filtered_urls

    def clean_string(self, text: str) -> str:
        """Helper to clean whitespace and digits from text."""
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\d+', '', text)
        return text.strip()

    def extract_segments(self, html: str) -> Dict[str, str]:
        """Extract separated text and links from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        
        # Remove non-content elements
        for tag in soup.find_all(["noindex", "script", "style", "header", "footer", "nav", "aside"]):
            tag.decompose()
        
        # Try to focus on main content if possible
        main_content = soup.find("main") or soup.find("article")
        content_soup = main_content if main_content else soup
            
        links = []
        for a in content_soup.find_all("a"):
            links.append(a.get_text(separator=" "))
            a.decompose() # Remove links from the text stream
            
        text = content_soup.get_text(separator=" ")
        
        return {
            "text": self.clean_string(text),
            "links": self.clean_string(" ".join(links))
        }

    def extract_meta_and_headers(self, html: str) -> Dict[str, Any]:
        """Extract title, description, and header structure."""
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("title")
        desc = soup.find("meta", attrs={"name": "description"})
        
        headers = {}
        for i in range(1, 7):
            h_tags = [h.get_text(separator=" ").strip() for h in soup.find_all(f"h{i}")]
            if h_tags:
                headers[f"h{i}"] = h_tags
                
        return {
            "title": title.get_text().strip() if title else "",
            "description": desc.get("content", "").strip() if desc else "",
            "headers": headers
        }

    def get_lemmas(self, text: str) -> List[str]:
        """Tokenize and lemmatize text, filtering stop words and non-essential POS."""
        words = re.findall(r'[а-яА-ЯёЁ]+', text.lower())
        lemmas = []
        for word in words:
            if word in STOP_WORDS or len(word) < 3:
                continue
            
            p = morph.parse(word)[0]
            # Exclude prepositions, pronouns, conjunctions, particles, interjections
            if p.tag.POS in ('PREP', 'CONJ', 'PRCL', 'INTJ', 'NPRO'):
                continue
                
            lemmas.append(p.normal_form)
        return lemmas

    def calculate_complexity_metrics(self, lemmas: List[str], text: str) -> Dict[str, Any]:
        """Calculate Zipf, Stuffing, and Wateriness."""
        if not lemmas:
            return {"stuffing": 0, "wateriness": 0, "zipf": 0}
            
        # 1. Stuffing (Тошнота) - frequency of top word
        counts = Counter(lemmas)
        top_word_count = counts.most_common(1)[0][1] if counts else 0
        stuffing = round((top_word_count / len(lemmas)) * 100, 2)
        
        # 2. Wateriness (Водянистость) - non-content words ratio
        # We need the original words for this
        all_words = re.findall(r'[а-яА-ЯёЁ]+', text.lower())
        stop_words_count = sum(1 for w in all_words if w in STOP_WORDS or len(w) < 3)
        wateriness = round((stop_words_count / len(all_words)) * 100, 2) if all_words else 0
        
        # 3. Zipf's Law score
        # Simplified score: how close top 10 follow 1/n
        zipf_score = 100
        if len(counts) >= 10:
            top_10 = [c for w, c in counts.most_common(10)]
            ideal = [top_10[0] / (i + 1) for i in range(10)]
            # Correlation or simple diff
            diffs = [abs(top_10[i] - ideal[i]) / ideal[0] for i in range(10)]
            zipf_score = max(0, int(100 - (sum(diffs) * 10)))
            
        return {
            "stuffing": stuffing,
            "wateriness": wateriness,
            "zipf": zipf_score
        }

    def generate_ngrams(self, lemmas: List[str], n: int) -> Dict[str, int]:
        """Generate bigrams or trigrams and count them."""
        if len(lemmas) < n:
            return {}
        ngrams = [" ".join(lemmas[i:i+n]) for i in range(len(lemmas)-n+1)]
        return dict(Counter(ngrams))

    def get_intent(self, lemmas: List[str]) -> str:
        """Simple intent detection based on commercial/informational markers."""
        comm_markers = {"цена", "купить", "заказать", "стоимость", "интернет-магазин", "прайс", "недорого", "каталог"}
        info_markers = {"как", "почему", "обзор", "что", "инструкция", "совет", "рейтинг", "своими руками"}
        
        comm_score = sum(1 for l in lemmas if l in comm_markers)
        info_score = sum(1 for l in lemmas if l in info_markers)
        
        if comm_score > info_score:
            return "Коммерческий"
        elif info_score > comm_score:
            return "Информационный"
        else:
            return "Смешанный"

    def run_technical_audit(self, html: str, url: str) -> Dict[str, Any]:
        """Perform technical SEO audit."""
        soup = BeautifulSoup(html, "html.parser")
        
        # 1. HTTPS
        is_https = url.startswith("https://")
        
        # 2. Schema.org
        has_schema = bool(soup.find(attrs={"itemtype": True}) or 
                          soup.find(attrs={"itemscope": True}) or 
                          soup.find("script", type="application/ld+json"))
        
        # 3. Headers hierarchy
        h_tags = []
        for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            h_tags.append(tag.name)
        
        hierarchy_ok = True
        if h_tags:
            for i in range(len(h_tags) - 1):
                curr_level = int(h_tags[i][1])
                next_level = int(h_tags[i+1][1])
                if next_level > curr_level + 1:
                    hierarchy_ok = False
                    break
        
        # 4. Alt tags
        images = soup.find_all("img")
        images_with_alt = [img for img in images if img.get("alt")]
        alt_coverage = (len(images_with_alt) / len(images) * 100) if images else 100
        
        # 5. Article/Main tag
        has_article_tag = bool(soup.find("article") or soup.find("main"))
        
        return {
            "https": is_https,
            "schema": has_schema,
            "header_hierarchy": hierarchy_ok,
            "alt_tags": {
                "total": len(images),
                "with_alt": len(images_with_alt),
                "percent": round(alt_coverage, 1)
            },
            "semantic_markup": has_article_tag
        }

    def analyze_content(self, html: str, url: str = "") -> Dict[str, Any]:
        """Perform full content analysis on HTML."""
        segments = self.extract_segments(html)
        meta = self.extract_meta_and_headers(html)
        tech_audit = self.run_technical_audit(html, url)
        
        lemmas_text = self.get_lemmas(segments["text"])
        lemmas_links = self.get_lemmas(segments["links"])
        lemmas_all = lemmas_text + lemmas_links
        
        counts_text = Counter(lemmas_text)
        counts_links = Counter(lemmas_links)
        counts_all = Counter(lemmas_all)
        
        complexity = self.calculate_complexity_metrics(lemmas_all, segments["text"] + " " + segments["links"])
        intent = self.get_intent(lemmas_all)
        
        # N-grams
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
                "links": dict(counts_links)
            },
            "ngrams": {
                "bigrams": bigrams,
                "trigrams": trigrams
            },
            "metrics": {
                "characters_with_spaces": len(segments["text"]) + len(segments["links"]),
                "characters_without_spaces": len((segments["text"] + segments["links"]).replace(" ", "")),
                "words_total": len(lemmas_all),
                "words_unique": len(counts_all),
                **complexity
            }
        }

    def process_analysis(self, target_url: str, keywords: List[str], raw_html: str = None, competitor_urls: List[str] | None = None) -> Dict[str, Any]:
        """Main entry point: find competitors, analyze all, and compare."""
        print(f"[INFO] Starting analysis for {target_url}", file=sys.stderr)
        
        # 1. Target page
        target_data = None
        if raw_html:
            try:
                target_data = self.analyze_content(raw_html, target_url)
            except Exception as e:
                print(f"[ERROR] Error analyzing provided raw_html: {e}", file=sys.stderr)

        if not target_data:
            try:
                # Punycode conversion for Cyrillic domains
                fetch_url = target_url
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(target_url)
                    if parsed.netloc:
                        puny_netloc = parsed.netloc.encode('idna').decode('ascii')
                        fetch_url = target_url.replace(parsed.netloc, puny_netloc)
                except:
                    pass

                print(f"[INFO] Fetching target {fetch_url}", file=sys.stderr)
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
                resp = requests.get(fetch_url, timeout=20, headers=headers)
                resp.raise_for_status()
                # Fix encoding for Cyrillic
                if resp.encoding.lower() == 'iso-8859-1':
                    resp.encoding = resp.apparent_encoding
                target_data = self.analyze_content(resp.text, target_url)
            except Exception as e:
                print(f"[ERROR] Error fetching target {target_url}: {e}", file=sys.stderr)
                # Fallback empty data
                target_data = self.analyze_content("<html></html>", target_url)

        # 2. Competitors
        if competitor_urls is not None:
            comp_urls = competitor_urls
        else:
            comp_urls = self.fetch_competitors(keywords)
        print(f"[INFO] Found {len(comp_urls)} competitors", file=sys.stderr)
        
        comp_results = []
        for url in comp_urls:
            try:
                if not url.startswith('http'):
                    url = 'https://' + url
                print(f"   Analyzing {url}...", file=sys.stderr)
                r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
                r.raise_for_status()
                # Fix encoding for Cyrillic
                if r.encoding.lower() == 'iso-8859-1':
                    r.encoding = r.apparent_encoding
                c_data = self.analyze_content(r.text, url)
                comp_results.append(c_data)
            except Exception as e:
                print(f"   [WARN] Error analyzing {url}: {e}", file=sys.stderr)

        # 3. Keyword Analysis
        target_keyword_lemmas = []
        for kw in keywords:
            target_keyword_lemmas.extend(self.get_lemmas(kw))
        
        # Identify top words among competitors
        all_comp_words = Counter()
        for c in comp_results:
            all_comp_words.update(c["counts"]["all"].keys())
        
        popular_lemmas = [lemma for lemma, count in all_comp_words.items() if count >= 2]
        analysis_lemmas = sorted(list(set(target_keyword_lemmas) | set(popular_lemmas)))
        
        final_keywords = []
        for lemma in analysis_lemmas:
            comp_vals_all = [c["counts"]["all"].get(lemma, 0) for c in comp_results]
            median_all = int(np.median(comp_vals_all)) if comp_vals_all else 0
            target_all = target_data["counts"]["all"].get(lemma, 0)
            
            sites_count = sum(1 for v in comp_vals_all if v > 0)
            pop_score = round((sites_count / len(comp_results)) * 100, 1) if comp_results else 0
            
            final_keywords.append({
                "lemma": lemma,
                "popularity": pop_score,
                "sites_count": sites_count,
                "median": median_all,
                "current": target_all,
                "diff": median_all - target_all
            })

        # 4. N-gram Analysis (Bigrams and Trigrams)
        def process_ngrams(field):
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
                    res.append({
                        "phrase": phrase,
                        "median": median,
                        "current": current,
                        "diff": median - current
                    })
            return sorted(res, key=lambda x: x["median"], reverse=True)[:30]

        final_bigrams = process_ngrams("bigrams")
        final_trigrams = process_ngrams("trigrams")

        # 5. Top 20 popular words density
        top_20_words = all_comp_words.most_common(20)
        top_20_stats = []
        for lemma, _ in top_20_words:
            # Density calculation: (count / total_words) * 100
            comp_densities = [
                (c["counts"]["all"].get(lemma, 0) / c["metrics"]["words_total"] * 100)
                if c["metrics"]["words_total"] > 0 else 0 
                for c in comp_results
            ]
            median_density = round(np.median(comp_densities), 2) if comp_densities else 0
            target_density = round(
                (target_data["counts"]["all"].get(lemma, 0) / target_data["metrics"]["words_total"] * 100)
                if target_data["metrics"]["words_total"] > 0 else 0,
                2
            )
            top_20_stats.append({
                "lemma": lemma,
                "median_density": median_density,
                "target_density": target_density
            })

        # 6. Title and Description Frequent Words
        def get_frequent_meta_words(field):
            meta_lemmas = []
            for c in comp_results:
                text = c["meta"].get(field, "")
                meta_lemmas.extend(self.get_lemmas(text))
            counts = Counter(meta_lemmas)
            return [word for word, count in counts.most_common(15)]

        report = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "target_url": target_url,
                "competitors_count": len(comp_results),
            },
            "text_metrics": {
                "target": target_data["metrics"],
                "competitors_median": {
                    "characters_with_spaces": int(np.median([c["metrics"]["characters_with_spaces"] for c in comp_results])) if comp_results else 0,
                    "characters_without_spaces": int(np.median([c["metrics"]["characters_without_spaces"] for c in comp_results])) if comp_results else 0,
                    "words_total": int(np.median([c["metrics"]["words_total"] for c in comp_results])) if comp_results else 0,
                    "words_unique": int(np.median([c["metrics"]["words_unique"] for c in comp_results])) if comp_results else 0,
                    "stuffing": round(np.median([c["metrics"]["stuffing"] for c in comp_results]), 2) if comp_results else 0,
                    "wateriness": round(np.median([c["metrics"]["wateriness"] for c in comp_results]), 2) if comp_results else 0,
                    "zipf": int(np.median([c["metrics"]["zipf"] for c in comp_results])) if comp_results else 0
                }
            },
            "tech_audit": {
                "target": target_data["tech_audit"],
                "competitors": [c["tech_audit"] for c in comp_results]
            },
            "intent": {
                "target": target_data["intent"],
                "competitors": [c["intent"] for c in comp_results]
            },
            "keywords": final_keywords,
            "bigrams": final_bigrams,
            "trigrams": final_trigrams,
            "top_20_density": top_20_stats,
            "meta_analysis": {
                "title_popular_words": get_frequent_meta_words("title"),
                "description_popular_words": get_frequent_meta_words("description")
            },
            "competitors_details": [
                {
                    "url": c["url"],
                    "metrics": c["metrics"],
                    "meta": c["meta"],
                    "intent": c["intent"],
                    "tech_audit": c["tech_audit"]
                } for c in comp_results
            ],
            "target_meta": target_data["meta"]
        }
        
        return report
        
        return report

if __name__ == "__main__":
    analyzer = CustomAnalyzer()
    res = analyzer.process_analysis("https://piter-trevel.ru/", ["экскурсии в пятигорске"])
    print(json.dumps(res, indent=2, ensure_ascii=False))
