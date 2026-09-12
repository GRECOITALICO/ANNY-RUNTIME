"""Security scrubber for telemetry metadata.

Ensures that no secrets, tokens, or credentials leak into the telemetry stream.
This is a critical security boundary before data is written to telemetry.jsonl.
"""

import re
from typing import Any, Dict, List, Union


# Regex pattern to match sensitive keys (case-insensitive)
_SENSITIVE_KEY_PATTERN = re.compile(
    r".*(token|key|password|secret|credential|auth|pat).*$", re.IGNORECASE
)

# Placeholder replacement string
_REDACTED_STR = "[REDACTED]"


def _is_sensitive_key(key: str) -> bool:
    """Check if a dictionary key looks sensitive."""
    return bool(_SENSITIVE_KEY_PATTERN.match(key))


def scrub_metadata(data: Any) -> Any:
    """Recursively scrub sensitive information from telemetry metadata.
    
    Any dictionary key matching the sensitive pattern will have its value
    replaced with '[REDACTED]'.
    """
    if isinstance(data, dict):
        scrubbed_dict = {}
        for k, v in data.items():
            k_str = str(k)
            if _is_sensitive_key(k_str):
                scrubbed_dict[k_str] = _REDACTED_STR
            else:
                scrubbed_dict[k_str] = scrub_metadata(v)
        return scrubbed_dict
    elif isinstance(data, list):
        return [scrub_metadata(item) for item in data]
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    else:
        # Cast unknown types to string just to be safe
        return str(data)
