import sys
from . import Pip2SysDep

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m pip2sysdep <pip-package> [<pip-package> ...]", file=sys.stderr)
        sys.exit(1)
    packages = sys.argv[1:]
    converter = Pip2SysDep()
    result = converter.convert_list(packages)
    print(" ".join(result['all']))

if __name__ == "__main__":
    main()
