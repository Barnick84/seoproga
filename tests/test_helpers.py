import pytest

from utils.helpers import clean_url, extract_domain, safe_divide


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.example.com/path", "example.com"),
        ("http://example.com", "example.com"),
        ("example.com", "example.com"),
        ("www.example.com", "example.com"),
        ("https://WWW.Example.COM/", "example.com"),
        ("mywww.com", "mywww.com"),
        ("https://user:pass@www.example.com/", "example.com"),
        ("", ""),
        ("https://example.com:8080/x", "example.com:8080"),
    ],
)
def test_extract_domain(url, expected):
    assert extract_domain(url) == expected


def test_extract_domain_punycode_decoded():
    d = extract_domain("https://xn--80ak.xn--p1ai/")
    assert d != ""
    assert "xn--" not in d


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.example.com/path/", "example.com/path"),
        ("https://example.com", "example.com"),
        ("not a url", "not a url"),
        ("", ""),
    ],
)
def test_clean_url(url, expected):
    assert clean_url(url) == expected


def test_clean_url_punycode_decoded():
    u = clean_url("https://xn--80ak.xn--p1ai/page")
    assert "xn--" not in u
    assert u.endswith("/page")


def test_safe_divide_normal():
    assert safe_divide(10, 2) == 5.0


def test_safe_divide_by_zero():
    assert safe_divide(10, 0) == 0.0
    assert safe_divide(10, 0, default=-1.0) == -1.0
