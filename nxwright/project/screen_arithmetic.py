"""The screen's arithmetic: its numbers are 32 bits (int32), and it
divides as C does, cutting toward zero (divide_toward_zero)."""


def int32(value: int) -> int:
    """Returns `value` wrapped to a signed 32-bit number, as the screen keeps
    its numbers."""
    return (value + 2 ** 31) % 2 ** 32 - 2 ** 31


def divide_toward_zero(numerator: int, denominator: int) -> int:
    """Returns `numerator` / `denominator` cut toward zero, as C divides:
    -7 / 2 is -3. Raises ZeroDivisionError when `denominator` is 0."""
    quotient = abs(numerator) // abs(denominator)
    return quotient if (numerator >= 0) == (denominator >= 0) else -quotient
