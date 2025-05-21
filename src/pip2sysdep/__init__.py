from ._helper import _get_current_os_info

import enum
import threading
import yaml
import os
from typing import Dict, List, Optional, Set
from string import Template

# Define the different sources pip2sysdep lists can be retrieved from
class Source(enum.Enum):
    LOCAL = "local" # Searches for a local yaml file in pip2sysdep/data/
    REPO = "repo" # Searches for a yaml file in the online repository

class DependencyType(enum.Enum):
    BUILD_ESSENTIALS = "build_essentials"
    DEV_HEADERS = "dev_headers"
    SYSTEM_LIBS = "system_libs"
    PYTHON_DEPS = "python_deps"

class Pip2SysDep:
    """
    Convert pip package requirements to system-level dependencies.
    """
    def __init__(self, source: Source = Source.LOCAL, os_distro: Optional[str] = None, os_version: Optional[str] = None):
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
        # 1. Check external/pip2sysdep/data/
        external_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
        mapping_file = os.path.join(external_data_dir, f"{self.os_distro}-{self.os_version}.yaml")
        if os.path.exists(mapping_file):
            with open(mapping_file, 'r') as f:
                return yaml.safe_load(f)
        # 2. Fallback to package data dir (src/pip2sysdep/data/)
        package_data_dir = os.path.join(os.path.dirname(__file__), "data")
        mapping_file = os.path.join(package_data_dir, f"{self.os_distro}-{self.os_version}.yaml")
        if os.path.exists(mapping_file):
            with open(mapping_file, 'r') as f:
                return yaml.safe_load(f)
        raise FileNotFoundError(f"Mapping file not found in external or package data dirs for {self.os_distro}-{self.os_version}")

    def _get_repo_content(self) -> Dict:
        """Get content from remote repository."""
        raise NotImplementedError("Repository source not yet implemented")

    def _get_content(self) -> Dict:
        """Get content with thread safety."""
        with self._content_lock:
            if self._content is None:
                if self.source == Source.LOCAL:
                    self._content = self._get_local_content()
                elif self.source == Source.REPO:
                    self._content = self._get_repo_content()
        return self._content

    def convert(self, pip_package: str, dependency_types: Optional[List[DependencyType]] = None) -> Dict[str, List[str]]:
        """
        Convert a single pip requirement to its system dependencies.

        Args:
            pip_package (str): The pip package name to convert
            dependency_types (List[DependencyType], optional): List of dependency types to include.
                If None, all dependency types are included.

        Returns:
            Dict[str, List[str]]: Dictionary mapping dependency types to lists of system packages
        """
        content = self._get_content()
        result = {}

        # If no specific types requested, include all
        if dependency_types is None:
            dependency_types = list(DependencyType)

        # Get package mappings
        pkg_deps = content.get(pip_package, {})

        # Always include all items for each dependency type
        for dep_type in dependency_types:
            key = dep_type.value
            items = []
            # Add global (underscore-prefixed) items if present
            if key == "build_essentials" and "_build_essentials" in content:
                items.extend(content["_build_essentials"])
            if key == "python_deps" and "_python_dev" in content:
                items.extend(content["_python_dev"])
            # Add package-specific items if present
            if key in pkg_deps:
                items.extend(pkg_deps[key])
            # Remove duplicates while preserving order
            if items:
                result[key] = list(dict.fromkeys(items))

        return result

    def convert_list(self, pip_packages: List[str], dependency_types: Optional[List[DependencyType]] = None) -> Dict[str, Set[str]]:
        """
        Convert a list of pip requirements to their system dependencies.

        Args:
            pip_packages (List[str]): List of pip package names to convert
            dependency_types (List[DependencyType], optional): List of dependency types to include.
                If None, all dependency types are included.

        Returns:
            Dict[str, Set[str]]: Dictionary mapping dependency types to sets of unique system packages
        """
        result: Dict[str, Set[str]] = {}
        
        # Process each package
        for pkg in pip_packages:
            pkg_deps = self.convert(pkg, dependency_types)
            
            # Merge dependencies by type
            for dep_type, deps in pkg_deps.items():
                if dep_type not in result:
                    result[dep_type] = set()
                result[dep_type].update(deps)
        
        return result

    def get_install_command(self, dependencies: Dict[str, Set[str]]) -> str:
        """
        Generate the package manager install command for the dependencies.

        Args:
            dependencies (Dict[str, Set[str]]): Dictionary of dependencies by type

        Returns:
            str: The package manager install command
        """
        content = self._get_content()
        meta = content.get("_meta", {})
        install_cmd = meta.get("commands", {}).get("install", "apt install -y")
        
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
        return f"{install_cmd} {deps_str}"

    def _get_current_os_info(self) -> tuple[Optional[str], Optional[str]]:
        """Get current OS distribution and version."""
        # This is a placeholder - in a real implementation, this would detect the OS
        return "ubuntu", "24.04"
