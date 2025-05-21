import pytest
from pathlib import Path
import os
import builtins
import tomllib

from pip2sysdep import Pip2SysDep, Source, DependencyType

# Test data directory setup
@pytest.fixture
def test_data_dir(tmp_path, monkeypatch):
    """Create a temporary directory with test mapping files and patch Pip2SysDep to use it."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    # TOML mapping as a string (no toml dependency)
    mapping_toml = '''
[__meta__]
__always__ = [
    "python3-pip", "python3-setuptools", "python3-wheel", "python3-venv"
]
__dev__ = [
    "build-essential", "gcc", "g++", "make", "pkg-config", "python3-dev"
]

[numpy]
deps = ["__dev__", "libopenblas-dev", "liblapack-dev", "libopenblas0", "liblapack3"]

["python-ldap"]
deps = ["__dev__", "libldap2-dev", "libsasl2-dev", "libldap-2.5-0", "libsasl2-2"]

[requests]
deps = []
'''

    for distro, version in [("debian", "12"), ("ubuntu", "24.04"), ("fedora", "38")]:
        toml_path = data_dir / f"{distro}-{version}.toml"
        with open(toml_path, "w") as f:
            f.write(mapping_toml)

    # Patch Pip2SysDep to always load from this temp data dir
    def _get_local_content(self):
        mapping_file = data_dir / f"{self.os_distro}-{self.os_version}.toml"
        with open(mapping_file, 'rb') as f:
            return tomllib.load(f)
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
        os_distro="ubuntu",
        os_version="24.04"
    )
    
    # Test package with multiple dependency types
    numpy_deps = converter.convert("numpy")['all']
    expected_numpy = [
        "python3-pip", "python3-setuptools", "python3-wheel", "python3-venv",
        "build-essential", "gcc", "g++", "make", "pkg-config", "python3-dev",
        "libopenblas-dev", "liblapack-dev", "libopenblas0", "liblapack3"
    ]
    assert numpy_deps == expected_numpy
    
    # Test package with only system libraries (requests has no extra deps)
    requests_deps = converter.convert("requests")['all']
    expected_requests = [
        "python3-pip", "python3-setuptools", "python3-wheel", "python3-venv"
    ]
    assert requests_deps == expected_requests
    
    # Test unknown package
    nonexistent_deps = converter.convert("nonexistent")['all']
    assert nonexistent_deps == [
        "python3-pip", "python3-setuptools", "python3-wheel", "python3-venv"
    ]

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
    all_deps = deps['all']
    
    # Check for presence of expected packages
    for pkg in [
        "python3-pip", "python3-setuptools", "python3-wheel", "python3-venv",
        "build-essential", "gcc", "g++", "make", "pkg-config", "python3-dev",
        "libopenblas-dev", "liblapack-dev", "libopenblas0", "liblapack3",
        "libldap2-dev", "libsasl2-dev", "libldap-2.5-0", "libsasl2-2"
    ]:
        assert pkg in all_deps

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
    all_deps = deps['all']
    
    # Get install command
    cmd = converter.get_install_command(deps)
    
    # Command should include all dependencies
    assert cmd.startswith("apt install -y")
    for pkg in all_deps:
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
    all_deps = results[0]['all']
    for pkg in [
        "python3-pip", "python3-setuptools", "python3-wheel", "python3-venv",
        "build-essential", "gcc", "g++", "make", "pkg-config", "python3-dev",
        "libopenblas-dev", "liblapack-dev", "libopenblas0", "liblapack3"
    ]:
        assert pkg in all_deps

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
        deps = converter.convert("numpy")['all']
        for pkg in [
            "python3-pip", "python3-setuptools", "python3-wheel", "python3-venv",
            "build-essential", "gcc", "g++", "make", "pkg-config", "python3-dev",
            "libopenblas-dev", "liblapack-dev", "libopenblas0", "liblapack3"
        ]:
            assert pkg in deps

def test_meta_group_expansion(monkeypatch):
    # Patch _get_local_content to provide a minimal TOML-like dict for testing
    def fake_content(self):
        return {
            "__meta__": {
                "__always__": ["foo", "bar"],
                "__dev__": ["baz", "qux"]
            },
            "somepkg": {"deps": ["__dev__", "libx", "liby"]},
            "otherpkg": {"deps": ["libz"]}
        }
    monkeypatch.setattr(Pip2SysDep, "_get_local_content", fake_content)
    converter = Pip2SysDep(os_distro="testos", os_version="1.0")
    # Package with meta-group expansion
    deps = converter.convert("somepkg")['all']
    assert deps == ["foo", "bar", "baz", "qux", "libx", "liby"]
    # Package with only package-specific deps
    deps2 = converter.convert("otherpkg")['all']
    assert deps2 == ["foo", "bar", "libz"]
    # Unknown package, should get only __always__
    deps3 = converter.convert("nonexistent")['all']
    assert deps3 == ["foo", "bar"]

def test_recursive_meta_group(monkeypatch):
    def fake_content(self):
        return {
            "__meta__": {
                "__always__": ["foo"],
                "__dev__": ["bar", "__build__"],
                "__build__": ["baz"]
            },
            "pkg": {"deps": ["__dev__", "libx"]}
        }
    monkeypatch.setattr(Pip2SysDep, "_get_local_content", fake_content)
    converter = Pip2SysDep(os_distro="testos", os_version="1.0")
    deps = converter.convert("pkg")['all']
    assert deps == ["foo", "bar", "baz", "libx"]

def test_duplicate_removal(monkeypatch):
    def fake_content(self):
        return {
            "__meta__": {
                "__always__": ["foo", "bar"],
                "__dev__": ["bar", "baz"]
            },
            "pkg": {"deps": ["__dev__", "foo", "baz"]}
        }
    monkeypatch.setattr(Pip2SysDep, "_get_local_content", fake_content)
    converter = Pip2SysDep(os_distro="testos", os_version="1.0")
    deps = converter.convert("pkg")['all']
    # Should not have duplicates
    assert deps == ["foo", "bar", "baz"]
