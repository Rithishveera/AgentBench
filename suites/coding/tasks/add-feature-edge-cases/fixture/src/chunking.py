def chunked(items: list[int], size: int) -> list[list[int]]:
    if size <= 0:
        return [items]
    return [items[index : index + size] for index in range(0, len(items), size)]
