from src.scores import clamp


def test_clamp_with_default_bounds() -> None:
    assert clamp(40) == 40
