"""Security utilities for sandbox containers."""

from typing import List, Dict, Any


def get_security_config() -> Dict[str, Any]:
    """
    Get Docker security configuration.

    Returns:
        Security config dict
    """
    return {
        # Disable privileged mode
        "privileged": False,
        # Read-only root filesystem (except mounted volumes)
        # "read_only": True,  # Commented out for now as it may cause issues
        # Drop all capabilities
        "cap_drop": ["ALL"],
        # Add only necessary capabilities
        "cap_add": [],
        # No new privileges
        "security_opt": ["no-new-privileges"],
        # Resource limits
        "mem_limit": "1g",
        "memswap_limit": "1g",
        "cpu_quota": 50000,  # 50% of one CPU
        # Disable network (can be enabled per container)
        # "network_disabled": True,
    }


def sanitize_command(command: str) -> str:
    """
    Sanitize command to prevent injection attacks.

    Args:
        command: Command string

    Returns:
        Sanitized command

    Note: This is a basic implementation.
    In production, use proper command parsing and validation.
    """
    # Remove dangerous characters and patterns
    dangerous_patterns = [
        ";rm -rf",
        "&&rm -rf",
        "|rm -rf",
        "$(rm -rf",
        "`rm -rf",
    ]

    for pattern in dangerous_patterns:
        if pattern in command.lower():
            raise ValueError(f"Potentially dangerous command detected: {pattern}")

    return command


def validate_file_path(path: str, allowed_base: str = "/workspace") -> bool:
    """
    Validate file path to prevent directory traversal.

    Args:
        path: File path to validate
        allowed_base: Allowed base directory

    Returns:
        True if valid, False otherwise
    """
    # Use posixpath for Linux container paths (not os.path which is platform-dependent)
    # On Windows, os.path.normpath would convert /workspace to \workspace, breaking validation
    import posixpath

    normalized = posixpath.normpath(path)

    # Check if path starts with allowed base
    if not normalized.startswith(allowed_base):
        return False

    # Check for directory traversal
    if ".." in normalized:
        return False

    return True


def get_allowed_files_patterns() -> List[str]:
    """
    Get list of allowed file patterns.

    Returns:
        List of glob patterns
    """
    return [
        "*.py",
        "*.js",
        "*.ts",
        "*.jsx",
        "*.tsx",
        "*.json",
        "*.md",
        "*.txt",
        "*.csv",
        "*.yml",
        "*.yaml",
        "*.html",
        "*.css",
        "*.sql",
        "*.sh",
        "*.bash",
    ]


def is_allowed_file(filename: str) -> bool:
    """
    Check if file type is allowed.

    Args:
        filename: File name

    Returns:
        True if allowed, False otherwise
    """
    import fnmatch

    patterns = get_allowed_files_patterns()
    for pattern in patterns:
        if fnmatch.fnmatch(filename.lower(), pattern):
            return True

    return False
