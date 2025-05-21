# pip2sysdep

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/github/license/autiwire/pip2sysdep)
![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/autiwire/pip2sysdep/ci.yml?branch=main)
![Last Commit](https://img.shields.io/github/last-commit/autiwire/pip2sysdep)

**pip2sysdep** is a command-line tool that maps Python package requirements to the system-level packages needed for successful `pip install` in a virtual environment. It helps you quickly determine and install the necessary OS packages for your Python dependencies, supporting both local and online mapping sources.

## Features
- Maps Python packages to system dependencies for various Linux distributions
- Supports both local and online mapping files (TOML format)
- Handles meta-groups and recursive dependency expansion
- Accepts input from command line, requirements.txt, or pyproject.toml
- Flexible output formatting (space or newline separated)
- Can run the system install command directly
- Python 3.11+ (uses `tomllib` from the standard library)

## Installation
Clone this repository and install the dependencies (if any):

```bash
# Clone the repo
 git clone https://github.com/autiwire/pip2sysdep.git
 cd pip2sysdep
# (Optional) Create a virtual environment
 python3 -m venv .venv
 source .venv/bin/activate
# Run as module in venv
 python3 -m pip2sysdep 
# Run as script
 python3 src/pip2sysdep.py
```

## Usage

### Basic usage (online mapping by default)
```bash
python3 -m pip2sysdep numpy requests
```

### Use a local mapping file (auto-detects OS/version)
```bash
python3 -m pip2sysdep --local numpy
```

### Use a specific local mapping TOML file
```bash
python3 -m pip2sysdep --local=external/pip2sysdep/data/ubuntu-24.04.toml numpy
```

### Read packages from requirements.txt
```bash
python3 -m pip2sysdep --txt requirements.txt
```

### Read packages from pyproject.toml
```bash
python3 -m pip2sysdep --toml pyproject.toml
```

### Combine file input and extra packages
```bash
python3 -m pip2sysdep --txt requirements.txt extra-package
```

### Show the parsed Python package names (dry run)
```bash
python3 -m pip2sysdep --txt requirements.txt --show-input
```

### Change output separator
```bash
python3 -m pip2sysdep numpy requests --separator=space
```

### Run the system install command automatically
```bash
python3 -m pip2sysdep numpy requests --install
```

## Example Output

```bash
$ python3 -m pip2sysdep bonsai
git
curl
wget
python3
python3-pip
python3-setuptools
python3-wheel
python3-venv
python3-dev
gcc
g++
make
build-essential
pkg-config
libldap2-dev
libsasl2-dev
```

## Options
- `--help`                Show help message and exit
- `--local[=file]`        Use local mapping files (default: online lookup). If a file is given (with =), use it as the mapping TOML.
- `--install`             Run the system package install command
- `--separator=space|newline`  Output separator for system packages (default: newline)
- `--txt <file>`          Read Python package names from requirements.txt-style file
- `--toml <file>`         Read Python package names from pyproject.toml (PEP 621, Poetry, or PDM)
- `--show-input`          Print the list of Python package names parsed from input and exit

## Mapping Files
- Mapping files are in TOML format and can be stored locally or fetched from the online repository.
- You can customize or extend mapping files for your own environment.

## Contributing
Contributions, bug reports, and feature requests are welcome! Please open an issue or submit a pull request on GitHub.

## License
MIT License. See [LICENSE](LICENSE) for details.

## About

This project is maintained by [AutiWire GmbH](https://autiwire.de).

Copyright (c) 2025 AutiWire GmbH
