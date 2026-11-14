import pytest
from src.chunking import chunked


def test_empty_input_returns_no_chunks() -> None:
    assert chunked([], 3) == []


@pytest.mark.parametrize("size", [0, -1])
def test_nonpositive_sizes_raise(size: int) -> None:
    with pytest.raises(ValueError):
        chunked([1, 2], size)


def test_chunks_preserve_order_and_are_independent() -> None:
    values = [1, 2, 3]
    result = chunked(values, 2)
    result[0][0] = 9
    assert values == [1, 2, 3]
    assert result == [[9, 2], [3]]
