import sys

if sys.version_info < (3, 11):
    raise RuntimeError("pip2sysdep requires Python 3.11 or newer (for tomllib support)")

import enum
import threading
import os
from typing import Dict, List, Optional, Set, Tuple
from string import Template
import tomllib
import platform
import urllib.request
import sys
import subprocess
import re
import tomllib


# Define the different sources pip2sysdep lists can be retrieved from
class SysDepSource(enum.Enum):
    LOCAL = "local" # Searches for a local yaml file in pip2sysdep/data/
    REPO = "repo" # Searches for a yaml file in the online repository
   
class Pip2SysDep:
    """
    Convert pip package requirements to system-level dependencies.
    """

    Source = SysDepSource

    def __init__(self, source: SysDepSource = SysDepSource.LOCAL, os_distro: Optional[str] = None, os_version: Optional[str] = None):
        self.source = source
        self._content = None
        self._content_lock = threading.Lock()

        # If OS info not provided, try to detect it
        if os_distro is None or os_version is None:
            detected_distro, detected_version = self._get_current_os_info()
            self.os_distro = os_distro or detected_distro
            self.os_version = os_version or detected_version
        else:
            self.os_distro = os_distro
            self.os_version = os_version

    def _get_local_content(self) -> Dict:
        """Get content from local files."""
        # Look for TOML mapping in external/pip2sysdep/data/
        external_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
        mapping_file = os.path.join(external_data_dir, f"{self.os_distro}-{self.os_version}.toml")
        if os.path.exists(mapping_file):
            with open(mapping_file, 'rb') as f:
                return tomllib.load(f)
        raise FileNotFoundError(f"Mapping file not found: {mapping_file}")

    def _get_repo_content(self) -> Dict:
        """Get content from remote repository (GitHub)."""
        base_url = "https://raw.githubusercontent.com/autiwire/pip2sysdep/main/data"
        url = f"{base_url}/{self.os_distro}-{self.os_version}.toml"
        try:
            with urllib.request.urlopen(url) as response:
                data = response.read()
                return tomllib.loads(data.decode("utf-8"))
        except Exception as e:
            raise FileNotFoundError(f"Could not fetch mapping file from {url}: {e}")

    def _get_content(self) -> Dict:
        """Get content with thread safety."""
        with self._content_lock:
            if self._content is None:
                if self.source == SysDepSource.LOCAL:
                    self._content = self._get_local_content()
                elif self.source == SysDepSource.REPO:
                    self._content = self._get_repo_content()
        return self._content

    def _get_current_os_info(self) -> Tuple[str, str]:
        """
        Get the current OS distribution and version.
        
        Returns:
            Tuple of (distribution_name, version)
        """
        # Try to get OS info from /etc/os-release first
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release") as f:
                lines = f.readlines()
                info = dict(line.strip().split("=", 1) for line in lines if "=" in line)
                
                # Remove quotes if present
                distro = info.get("ID", "").strip('"')
                version = info.get("VERSION_ID", "").strip('"')
                
                if distro and version:
                    return distro.lower(), version

        # Fallback to platform module
        system = platform.system().lower()
        if system == "linux":
            # Try to detect common distributions
            if os.path.exists("/etc/debian_version"):
                with open("/etc/debian_version") as f:
                    return "debian", f.read().strip()
            elif os.path.exists("/etc/redhat-release"):
                with open("/etc/redhat-release") as f:
                    return "rhel", f.read().split()[6].split('.')[0]
        
        # Default fallback
        return platform.system().lower(), platform.release()

    def _expand_deps(self, mapping, items):
        result = []
        meta = mapping.get('__meta__', {})
        for item in items:
            # Expand meta-groups from __meta__ if present
            if isinstance(item, str) and item.startswith('__') and item.endswith('__'):
                if item in meta and isinstance(meta[item], list):
                    result.extend(self._expand_deps({'__meta__': meta}, meta[item]))
                    continue
            result.append(item)
        return result

    def convert(self, pip_package: str) -> Dict[str, list]:
        content = self._get_content()
        meta = content.get('__meta__', {})
        result = []
        # Always start with __always__ if present
        if '__always__' in meta:
            result.extend(self._expand_deps({'__meta__': meta}, meta['__always__']))
        # Add package-specific deps
        pkg_deps = content.get(pip_package, {}).get('deps', [])
        result.extend(self._expand_deps({'__meta__': meta}, pkg_deps))
        # Remove duplicates while preserving order
        seen = set()
        flat = [x for x in result if not (x in seen or seen.add(x))]
        return {'all': flat}

    def convert_list(self, pip_packages: List[str]) -> Dict[str, list]:
        """
        Convert a list of pip requirements to their system dependencies.

        Args:
            pip_packages (List[str]): List of pip package names to convert

        Returns:
            Dict[str, list]: Dictionary mapping dependency types to sets of unique system packages, and 'all' to a deduped, order-preserving list
        """
        result: Dict[str, set] = {}
        all_flat = []
        seen = set()
        # Process each package
        for pkg in pip_packages:
            pkg_deps = self.convert(pkg)
            for dep_type, deps in pkg_deps.items():
                if dep_type not in result:
                    result[dep_type] = set()
                result[dep_type].update(deps)
                # For 'all', preserve order and dedupe
                for dep in deps:
                    if dep not in seen:
                        all_flat.append(dep)
                        seen.add(dep)
        # Convert all sets to sets except 'all', which is a list
        out = {k: v for k, v in result.items()}
        out['all'] = all_flat
        return out

    def get_install_command(self, dependencies: Dict[str, Set[str]], command: str = 'install') -> str:
        """
        Generate the package manager command for the dependencies.

        Args:
            dependencies (Dict[str, Set[str]]): Dictionary of dependencies by type
            command (str): Which command to use from [__meta__.commands] (e.g. 'install', 'update'). Default is 'install'.

        Returns:
            str: The package manager command
        """
        content = self._get_content()
        meta = content.get("__meta__", {})
        # Prefer [__meta__.commands] table, fallback to old install_command key for backward compatibility
        commands = meta.get('commands', {})
        if command == 'install':
            install_cmd = commands.get('install') or meta.get('install_command', 'apt install -y')
        else:
            install_cmd = commands.get(command)
            if not install_cmd:
                raise ValueError(f"No command '{command}' found in [__meta__.commands]")
        # Interpolate package manager command
        if "${package_manager}" in install_cmd:
            package_manager = meta.get("package_manager", "apt")
            install_cmd = Template(install_cmd).substitute(package_manager=package_manager)
        # Flatten all dependencies into a single list
        all_deps = []
        for deps in dependencies.values():
            all_deps.extend(deps)
        # Join dependencies with spaces
        deps_str = " ".join(sorted(set(all_deps)))
        # Return full command
        return f"{install_cmd} {deps_str}" if deps_str else install_cmd

    def _get_current_os_info(self) -> tuple[Optional[str], Optional[str]]:
        """Get current OS distribution and version."""
        # This is a placeholder - in a real implementation, this would detect the OS
        return "ubuntu", "24.04"

def extract_pkg_name(line):
    # Skip VCS, URLs, editable installs, and local paths
    vcs_prefixes = ('git+', 'http://', 'https://', 'ssh://', '-e', './', '../', '/')
    if line.startswith(vcs_prefixes):
        return None
    # Remove comments and environment markers
    line = line.split('#', 1)[0].split(';', 1)[0].strip()
    if not line:
        return None
    # Remove extras and version specifiers (e.g. foo[bar]==1.2.3)
    pkg = re.split(r'[=<>!~\[ ]', line, 1)[0].strip()
    if pkg:
        return pkg
    return None

def parse_requirements_file(filename):
    pkgs = []
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            pkg = extract_pkg_name(line)
            if pkg:
                pkgs.append(pkg)
    return pkgs

def parse_pyproject_toml(filename):
    pkgs = []
    with open(filename, 'rb') as f:
        data = tomllib.load(f)
    # PEP 621
    project = data.get('project', {})
    if 'dependencies' in project:
        for dep in project['dependencies']:
            pkg = extract_pkg_name(dep)
            if pkg:
                pkgs.append(pkg)
    # Poetry
    poetry_deps = data.get('tool', {}).get('poetry', {}).get('dependencies', {})
    for pkg in poetry_deps:
        if pkg.lower() == 'python':
            continue
        pkgs.append(pkg)
    # PDM
    pdm_deps = data.get('tool', {}).get('pdm', {}).get('dependencies', {})
    for pkg in pdm_deps:
        pkgs.append(pkg)
    return pkgs

HELP_MESSAGE = '''\
Usage: python3 -m pip2sysdep [OPTIONS] <pip-package> [<pip-package> ...]

Options:
  --help                Show this help message and exit
  --local[=file]        Use local mapping files (default: online lookup). If a file is given (with =), use it as the mapping TOML.
  --install             Run the system package install command
  --separator=space|newline
                        Output separator for system packages (default: newline)
  --txt <file>          Read Python package names from requirements.txt-style file
  --toml <file>         Read Python package names from pyproject.toml (PEP 621, Poetry, or PDM)
  --show-input          Print the list of Python package names parsed from input and exit

You can combine --txt/--toml with additional package names on the command line.
Only one of --txt or --toml can be used at a time.
'''

def main():
    args = sys.argv[1:]
    if '--help' in args:
        print(HELP_MESSAGE)
        sys.exit(0)
    use_local = False
    local_file = None
    separator = '\n'  # default
    do_install = False
    show_input = False
    txt_file = None
    toml_file = None
    # Parse --local, --separator, --install, --txt, --toml, --show-input flags
    new_args = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '--local':
            use_local = True
        elif arg.startswith('--local='):
            use_local = True
            local_file = arg.split('=', 1)[1]
        elif arg == '--install':
            do_install = True
        elif arg == '--show-input':
            show_input = True
        elif arg.startswith('--separator='):
            val = arg.split('=', 1)[1].strip().lower()
            if val == 'space':
                separator = ' '
            elif val == 'newline':
                separator = '\n'
            else:
                print("Unknown separator: {} (use 'space' or 'newline')".format(val), file=sys.stderr)
                sys.exit(1)
        elif arg == '--txt' and i + 1 < len(args):
            txt_file = args[i + 1]
            i += 1
        elif arg == '--toml' and i + 1 < len(args):
            toml_file = args[i + 1]
            i += 1
        else:
            new_args.append(arg)
        i += 1
    if txt_file and toml_file:
        print("Cannot use both --txt and --toml at the same time.", file=sys.stderr)
        sys.exit(1)
    pkgs = []
    if txt_file:
        pkgs.extend(parse_requirements_file(txt_file))
    if toml_file:
        pkgs.extend(parse_pyproject_toml(toml_file))
    pkgs.extend(new_args)
    if not pkgs:
        print(HELP_MESSAGE, file=sys.stderr)
        sys.exit(1)
    # Deduplicate while preserving order
    seen = set()
    pkgs = [x for x in pkgs if not (x in seen or seen.add(x))]
    if show_input:
        for pkg in pkgs:
            print(pkg)
        sys.exit(0)
    if use_local and local_file:
        # Patch Pip2SysDep._get_local_content to load from the given file
        def _get_local_content(self):
            with open(local_file, 'rb') as f:
                return tomllib.load(f)
        Pip2SysDep._get_local_content = _get_local_content
    source = Pip2SysDep.Source.LOCAL if use_local else Pip2SysDep.Source.REPO
    converter = Pip2SysDep(source=source)
    result = converter.convert_list(pkgs)
    pkgs_out = result['all']
    if do_install:
        # Get the install command and run it
        cmd = converter.get_install_command({'all': pkgs_out})
        print(f"Running: {cmd}")
        try:
            proc = subprocess.run(cmd, shell=True)
            sys.exit(proc.returncode)
        except Exception as e:
            print(f"Error running install command: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(separator.join(pkgs_out))

if __name__ == "__main__":
    main()
