import pytest

from services.custom_analyzer import CustomAnalyzer


@pytest.fixture
def analyzer():
    ca = CustomAnalyzer()
    ca.xml_client = None  # disable real API calls
    return ca


def test_get_lemmas_returns_with_pos(analyzer):
    lemmas = analyzer.get_lemmas("быстрая доставка товаров")
    assert len(lemmas) > 0
    for lemma, pos in lemmas:
        assert isinstance(lemma, str)
        assert isinstance(pos, str)


def test_get_lemmas_filters_stop_words(analyzer):
    lemmas = analyzer.get_lemmas("и в на он она это")
    assert len(lemmas) == 0


def test_get_lemmas_flat(analyzer):
    flat = analyzer.get_lemmas_flat("быстрая доставка товаров")
    assert len(flat) > 0
    for item in flat:
        assert isinstance(item, str)


def test_generate_ngrams_without_noun_is_empty(analyzer):
    # ADJ-only bigram should be empty
    lemmas = [("быстрый", "ADJF"), ("очень", "ADVB")]
    ngrams = analyzer.generate_ngrams(lemmas, 2)
    assert ngrams == {}


def test_generate_ngrams_with_noun_present(analyzer):
    # Each bigram appears at least 2x to pass the v >= 2 filter
    lemmas = [
        ("быстрый", "ADJF"),
        ("доставка", "NOUN"),
        ("быстрый", "ADJF"),
        ("доставка", "NOUN"),
        ("товар", "NOUN"),
        ("качество", "NOUN"),
    ]
    ngrams = analyzer.generate_ngrams(lemmas, 2)
    assert len(ngrams) >= 1
    assert "быстрый доставка" in ngrams


def test_generate_ngrams_too_short(analyzer):
    lemmas = [("дом", "NOUN")]
    ngrams = analyzer.generate_ngrams(lemmas, 3)
    assert ngrams == {}


def test_calculate_complexity_metrics_empty(analyzer):
    result = analyzer.calculate_complexity_metrics([], "")
    assert result["stuffing"] == 0


def test_calculate_complexity_metrics(analyzer):
    lemmas = ["тест", "тест", "дом", "квартира", "машина"]
    result = analyzer.calculate_complexity_metrics(lemmas, "тест дом квартира машина")
    assert "academic_stuffing" in result
    assert result["academic_stuffing"] > 0
    assert "wateriness" in result
    assert "zipf" in result
