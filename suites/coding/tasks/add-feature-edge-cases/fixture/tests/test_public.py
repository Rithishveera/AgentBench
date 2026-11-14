from src.chunking import chunked


def test_chunks_nonempty_list() -> None:
    assert chunked([1, 2, 3], 2) == [[1, 2], [3]]
