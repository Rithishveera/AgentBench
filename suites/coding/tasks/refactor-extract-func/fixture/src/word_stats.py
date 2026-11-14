def count_words(text: str) -> int:
    return len([word for word in text.split() if word])


def unique_word_count(text: str) -> int:
    return len({word.lower() for word in text.split() if word})
