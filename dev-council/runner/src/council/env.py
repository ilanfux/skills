"""Environment hydration.

Editors such as Cursor capture their environment variables at launch. A key that
the user persists (e.g. `setx CURSOR_API_KEY ...` or via System Settings) AFTER
the editor started is invisible to processes the editor spawns until the editor
is fully restarted. That makes the CLI report a key as "missing" even though the
user set it. On Windows we can read the persisted value straight from the
registry and repopulate `os.environ`, so the tool self-heals without a restart.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Iterable, List

try:  # Windows-only stdlib module; absent elsewhere.
    import winreg
except ImportError:  # pragma: no cover - non-Windows
    winreg = None  # type: ignore[assignment]

# Credential/config env vars the runner cares about, used as the default set so
# hydration works even before backend config is loaded.
_DEFAULT_CREDENTIAL_VARS = (
    "CURSOR_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "AUTOX_API_KEY",
    "AUTOX_BASE_URL",
)

_REGISTRY_LOCATIONS = (
    ("HKEY_CURRENT_USER", r"Environment"),
    ("HKEY_LOCAL_MACHINE", r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
)


def credential_env_names(backends: Dict[str, dict]) -> List[str]:
    """Env var names referenced by backend configs (api_key_env / base_url_env)."""

    names: List[str] = []
    for spec in (backends or {}).values():
        for field in ("api_key_env", "base_url_env"):
            value = (spec or {}).get(field)
            if value:
                names.append(str(value))
    return names


def hydrate_persistent_env(names: Iterable[str] = ()) -> List[str]:
    """Fill any of `names` (plus the default credential set) that are missing from
    the current process but persisted in the Windows registry. No-op off Windows.
    Returns the list of variable names that were filled."""

    if winreg is None or not sys.platform.startswith("win"):
        return []

    wanted = set(_DEFAULT_CREDENTIAL_VARS) | {n for n in names if n}
    filled: List[str] = []

    for hive_name, subkey in _REGISTRY_LOCATIONS:
        missing = [n for n in wanted if not os.environ.get(n)]
        if not missing:
            break
        hive = getattr(winreg, hive_name)
        try:
            with winreg.OpenKey(hive, subkey) as key:
                for name in missing:
                    try:
                        value, _ = winreg.QueryValueEx(key, name)
                    except FileNotFoundError:
                        continue
                    if value:
                        os.environ[name] = str(value)
                        filled.append(name)
        except OSError:
            continue

    return filled
