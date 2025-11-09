import random
from sys import argv 

def print_hex_sequence(count: int):
    """
    Prints 'count' four-digit hexadecimal numbers separated by '/'.
    Example: '1A3F/09B2/FF00/7C1D'
    """
    values = [f"{random.randint(0, 0xFFFF):04X}" for _ in range(count)]
    print("/".join(values))

# Example usage:
if __name__ == "__main__":
    if len(argv) != 2 :
        raise RuntimeError("Missing position argument instruction length")
    n = int(argv[1])
    print_hex_sequence(n)