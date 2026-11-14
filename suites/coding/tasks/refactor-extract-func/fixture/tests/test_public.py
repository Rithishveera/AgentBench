from src.word_stats import count_words, unique_word_count


def test_basic_counts() -> None:
    assert count_words("red blue red") == 3
    assert unique_word_count("red blue red") == 2
