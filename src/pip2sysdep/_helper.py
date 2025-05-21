"""Helper functions for pip2sysdep."""

import platform
import os
from typing import Tuple

def _get_current_os_info() -> Tuple[str, str]:
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