from ._helper import _get_current_os_info

import sys
import urllib.request

if sys.version_info < (3, 11):
    raise RuntimeError("pip2sysdep requires Python 3.11 or newer (for tomllib support)")

import enum
import threading
import os
from typing import Dict, List, Optional, Set
from string import Template
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
            detected_distro, detected_version = _get_current_os_info()
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

    def _expand_deps(self, mapping, items):
        result = []
        meta = mapping.get('__meta__', {})
        for item in items:
            # Debug print
            # print(f"Expanding item: {item}, mapping keys: {list(mapping.keys())}, meta keys: {list(meta.keys())}")
            lookup = item
            # Check for meta-groups in root or __meta__
            if isinstance(item, str):
                if not item.startswith('__') and ('__' + item + '__') in mapping and isinstance(mapping['__' + item + '__'], list):
                    lookup = '__' + item + '__'
                elif not item.startswith('__') and ('__' + item + '__') in meta and isinstance(meta['__' + item + '__'], list):
                    lookup = '__' + item + '__'
                if lookup in mapping and isinstance(mapping[lookup], list):
                    result.extend(self._expand_deps(mapping, mapping[lookup]))
                    continue
                elif lookup in meta and isinstance(meta[lookup], list):
                    result.extend(self._expand_deps(meta, meta[lookup]))
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
