from . import Pip2SysDep
from . import DependencyType
def main():
    converter = Pip2SysDep()
    print(converter.convert("numpy", [DependencyType.BUILD_ESSENTIALS, DependencyType.DEV_HEADERS]))

if __name__ == "__main__":
    main()
