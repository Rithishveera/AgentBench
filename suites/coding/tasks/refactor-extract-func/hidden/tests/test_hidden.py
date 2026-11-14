from src.word_stats import _normalize_words, count_words, unique_word_count


def test_both_counters_use_normalized_words() -> None:
    text = "Hello, HELLO! don't stop..."
    assert count_words(text) == 5
    assert unique_word_count(text) == 4


def test_unicode_casefolding_and_punctuation() -> None:
    assert _normalize_words("Straße STRASSE — 東京!") == [
        "strasse",
        "strasse",
        "東京",
    ]


def test_symbol_only_tokens_are_ignored() -> None:
    assert count_words("!!! ... --") == 0


def test_empty_input() -> None:
    assert unique_word_count("") == 0
