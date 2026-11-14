import pytest
from src.scores import clamp


def test_clamps_below_and_above_bounds() -> None:
    assert clamp(-1) == 0
    assert clamp(101) == 100


def test_clamps_custom_bounds() -> None:
    assert clamp(1, 3, 7) == 3
    assert clamp(9, 3, 7) == 7


def test_invalid_bounds_raise() -> None:
    with pytest.raises(ValueError):
        clamp(5, 10, 1)


def test_value_inside_custom_bounds_is_preserved() -> None:
    assert clamp(5, 3, 7) == 5
