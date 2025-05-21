import pytest
from pathlib import Path
import os
import yaml
import builtins

from pip2sysdep import Pip2SysDep, Source, DependencyType

# Test data directory setup
@pytest.fixture
def test_data_dir(tmp_path, monkeypatch):
    """Create a temporary directory with test mapping files and patch Pip2SysDep to use it."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    
    mapping_data = {
        "_meta": {
            "os": "ubuntu",
            "version": "24.04",
            "package_manager": "apt",
            "commands": {
                "install": "${package_manager} install -y"
            }
        },
        "_build_essentials": [
            "build-essential",
            "gcc",
            "g++",
            "make",
            "pkg-config"
        ],
        "_python_dev": [
            "python3-dev",
            "python3-pip",
            "python3-setuptools",
            "python3-wheel",
            "python3-venv"
        ],
        "numpy": {
            "build_essentials": ["build-essential"],
            "dev_headers": ["libopenblas-dev", "liblapack-dev"],
            "system_libs": ["libopenblas0", "liblapack3"]
        },
        "python-ldap": {
            "dev_headers": ["libldap2-dev", "libsasl2-dev"],
            "system_libs": ["libldap-2.5-0", "libsasl2-2"]
        },
        "requests": {
            "system_libs": ["ca-certificates"]
        }
    }
    
    for distro, version in [("debian", "12"), ("ubuntu", "24.04"), ("fedora", "38")]:
        yaml_path = data_dir / f"{distro}-{version}.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(mapping_data, f, sort_keys=False)
    
    # Patch Pip2SysDep to always load from this temp data dir
    def _get_local_content(self):
        mapping_file = data_dir / f"{self.os_distro}-{self.os_version}.yaml"
        with open(mapping_file, 'r') as f:
            return yaml.safe_load(f)
    monkeypatch.setattr("pip2sysdep.Pip2SysDep._get_local_content", _get_local_content)
    return data_dir

@pytest.fixture
def mock_os_info(monkeypatch):
    """Mock the OS info detection."""
    def mock_get_os_info():
        return "ubuntu", "24.04"
    
    monkeypatch.setattr("pip2sysdep._helper._get_current_os_info", mock_get_os_info)

def test_init_with_defaults(mock_os_info):
    """Test initialization with default values."""
    converter = Pip2SysDep()
    assert converter.source == Source.LOCAL
    assert converter.os_distro == "ubuntu"
    assert converter.os_version == "24.04"

def test_init_with_custom_values():
    """Test initialization with custom values."""
    converter = Pip2SysDep(
        source=Source.LOCAL,
        os_distro="debian",
        os_version="12"
    )
    assert converter.source == Source.LOCAL
    assert converter.os_distro == "debian"
    assert converter.os_version == "12"

def test_convert_single_package(test_data_dir, monkeypatch):
    """Test converting a single package."""
    monkeypatch.syspath_prepend(test_data_dir.parent)
    
    converter = Pip2SysDep(
        source=Source.LOCAL,
        os_distro="debian",
        os_version="12"
    )
    
    # Test package with multiple dependency types
    numpy_deps = converter.convert("numpy")
    print("Loaded YAML:", converter._get_content())
    print("numpy_deps:", numpy_deps)
    assert numpy_deps["build_essentials"] == ["build-essential", "gcc", "g++", "make", "pkg-config"]
    assert numpy_deps["dev_headers"] == ["libopenblas-dev", "liblapack-dev"]
    assert numpy_deps["system_libs"] == ["libopenblas0", "liblapack3"]
    
    # Test package with only system libraries
    requests_deps = converter.convert("requests")
    assert requests_deps["system_libs"] == ["ca-certificates"]
    assert requests_deps["build_essentials"] == ["build-essential", "gcc", "g++", "make", "pkg-config"]
    assert requests_deps["python_deps"] == ["python3-dev", "python3-pip", "python3-setuptools", "python3-wheel", "python3-venv"]
    assert "dev_headers" not in requests_deps
    
    # Test unknown package
    nonexistent_deps = converter.convert("nonexistent")
    assert nonexistent_deps["build_essentials"] == ["build-essential", "gcc", "g++", "make", "pkg-config"]
    assert nonexistent_deps["python_deps"] == ["python3-dev", "python3-pip", "python3-setuptools", "python3-wheel", "python3-venv"]
    assert "dev_headers" not in nonexistent_deps
    assert "system_libs" not in nonexistent_deps

def test_convert_with_specific_types(test_data_dir, monkeypatch):
    """Test converting a package with specific dependency types."""
    monkeypatch.syspath_prepend(test_data_dir.parent)
    
    converter = Pip2SysDep(
        source=Source.LOCAL,
        os_distro="debian",
        os_version="12"
    )
    
    # Test getting only system libraries
    numpy_sys_libs = converter.convert("numpy", [DependencyType.SYSTEM_LIBS])
    assert numpy_sys_libs == {"system_libs": ["libopenblas0", "liblapack3"]}
    
    # Test getting build and dev dependencies
    numpy_build_dev = converter.convert("numpy", [DependencyType.BUILD_ESSENTIALS, DependencyType.DEV_HEADERS])
    assert numpy_build_dev["build_essentials"] == ["build-essential", "gcc", "g++", "make", "pkg-config"]
    assert numpy_build_dev["dev_headers"] == ["libopenblas-dev", "liblapack-dev"]
    assert "system_libs" not in numpy_build_dev

def test_convert_package_list(test_data_dir, monkeypatch):
    """Test converting a list of packages."""
    monkeypatch.syspath_prepend(test_data_dir.parent)
    
    converter = Pip2SysDep(
        source=Source.LOCAL,
        os_distro="debian",
        os_version="12"
    )
    
    packages = ["numpy", "python-ldap", "requests"]
    deps = converter.convert_list(packages)
    
    # Check build essentials
    assert deps["build_essentials"] == {"build-essential", "gcc", "g++", "make", "pkg-config"}
    
    # Check dev headers
    assert deps["dev_headers"] == {
        "libopenblas-dev", "liblapack-dev",
        "libldap2-dev", "libsasl2-dev"
    }
    
    # Check system libraries
    assert deps["system_libs"] == {
        "libopenblas0", "liblapack3",
        "libldap-2.5-0", "libsasl2-2",
        "ca-certificates"
    }

def test_get_install_command(test_data_dir, monkeypatch):
    """Test generating install commands."""
    monkeypatch.syspath_prepend(test_data_dir.parent)
    
    converter = Pip2SysDep(
        source=Source.LOCAL,
        os_distro="debian",
        os_version="12"
    )
    
    # Get dependencies
    deps = converter.convert_list(["numpy", "python-ldap"])
    
    # Get install command
    cmd = converter.get_install_command(deps)
    
    # Command should include all dependencies
    assert cmd.startswith("apt install -y")
    for pkg in [
        "build-essential", "gcc", "g++", "make", "pkg-config",
        "libopenblas-dev", "liblapack-dev",
        "libldap2-dev", "libsasl2-dev",
        "libopenblas0", "liblapack3",
        "libldap-2.5-0", "libsasl2-2"
    ]:
        assert pkg in cmd

def test_thread_safety(test_data_dir, monkeypatch):
    """Test thread safety of content loading."""
    monkeypatch.syspath_prepend(test_data_dir.parent)
    
    import threading
    
    converter = Pip2SysDep(
        source=Source.LOCAL,
        os_distro="debian",
        os_version="12"
    )
    results = []
    
    def worker():
        result = converter.convert("numpy")
        results.append(result)
    
    # Create multiple threads
    threads = [threading.Thread(target=worker) for _ in range(5)]
    
    # Start all threads
    for t in threads:
        t.start()
    
    # Wait for all threads to complete
    for t in threads:
        t.join()
    
    # All results should be identical
    assert all(r == results[0] for r in results)
    assert "build_essentials" in results[0]
    assert "dev_headers" in results[0]
    assert "system_libs" in results[0]

def test_error_handling():
    """Test error handling for various scenarios."""
    # Test with invalid OS/version
    with pytest.raises(FileNotFoundError):
        converter = Pip2SysDep(
            source=Source.LOCAL,
            os_distro="nonexistent",
            os_version="999"
        )
        converter.convert("numpy")  # This should fail because the mapping file doesn't exist

def test_different_distros(test_data_dir, monkeypatch):
    """Test that different distributions work correctly."""
    monkeypatch.syspath_prepend(test_data_dir.parent)
    
    # Test with different distributions
    distros = [
        ("debian", "12"),
        ("ubuntu", "24.04"),
        ("fedora", "38")
    ]
    
    for distro, version in distros:
        converter = Pip2SysDep(
            source=Source.LOCAL,
            os_distro=distro,
            os_version=version
        )
        
        # Each distro should handle the conversion
        deps = converter.convert("numpy")
        assert "build_essentials" in deps
        assert "dev_headers" in deps
        assert "system_libs" in deps
