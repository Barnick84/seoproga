import pytest
from services.clustering import serp_similarity, merge_serps

def test_serp_similarity_exact_match():
    urls_a = ["https://example.com/1", "https://example.com/2", "https://example.com/3"]
    urls_b = ["https://example.com/1", "https://example.com/2", "https://example.com/3"]
    
    sim = serp_similarity(urls_a, urls_b)
    assert sim == pytest.approx(1.0)

def test_serp_similarity_no_match():
    urls_a = ["https://example.com/1", "https://example.com/2"]
    urls_b = ["https://example.com/3", "https://example.com/4"]
    
    sim = serp_similarity(urls_a, urls_b)
    assert sim == 0.0

def test_serp_similarity_partial_match():
    urls_a = ["https://example.com/1", "https://example.com/2", "https://example.com/3"]
    urls_b = ["https://example.com/2", "https://example.com/4", "https://example.com/5"]
    
    sim = serp_similarity(urls_a, urls_b)
    assert 0.0 < sim < 1.0

def test_merge_serps():
    serps_list = [
        ["https://example.com/1", "https://example.com/2"],
        ["https://example.com/2", "https://example.com/3"],
        ["https://example.com/1", "https://example.com/4"],
    ]
    
    merged = merge_serps(serps_list)
    # url 1 appears at pos 0 (score 1) and pos 0 (score 1) -> total 2.0
    # url 2 appears at pos 1 (score 0.5) and pos 0 (score 1) -> total 1.5
    # url 3 appears at pos 1 (score 0.5) -> total 0.5
    # url 4 appears at pos 1 (score 0.5) -> total 0.5
    
    assert merged[0] == "https://example.com/1"
    assert merged[1] == "https://example.com/2"
    assert "https://example.com/3" in merged[2:]
    assert "https://example.com/4" in merged[2:]
