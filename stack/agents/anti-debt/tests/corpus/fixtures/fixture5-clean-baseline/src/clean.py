# fixture5-clean-baseline
# A clean Python repo that should produce 0 critical/high findings

def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def multiply(a: int, b: int) -> int:
    """Multiply two integers."""
    return a * b


if __name__ == "__main__":
    print(add(2, 3))
    print(multiply(4, 5))
