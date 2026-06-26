"""Variable interpolation engine for workflow templates.

Supports:
  - Simple: {company} -> variables["company"]
  - Nested: {leads.0.name} -> variables["leads"][0]["name"]
  - Leaves unresolved placeholders as-is.
  - Recursively interpolates dicts and lists.
"""

import re
from typing import Any

_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


def _resolve(path: str, variables: dict) -> Any:
    """Walk a dot-separated path into *variables*, returning the leaf value.

    Raises KeyError or IndexError if the path cannot be resolved.
    """
    parts = path.strip().split(".")
    current: Any = variables
    for part in parts:
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, (list, tuple)):
            current = current[int(part)]
        else:
            raise KeyError(part)
    return current


def interpolate(template: Any, variables: dict) -> Any:
    """Replace ``{var}`` placeholders inside *template* with values from *variables*.

    *template* can be a ``str``, ``dict``, ``list``, or any other type.
    - ``str``:  placeholders are replaced.  If the *entire* string is a single
      placeholder and the resolved value is not a string the raw value is
      returned (preserves ints, lists, dicts, etc.).
    - ``dict`` / ``list``:  recursed into.
    - Everything else is returned unchanged.
    """
    if isinstance(template, str):
        return _interpolate_string(template, variables)
    if isinstance(template, dict):
        return {k: interpolate(v, variables) for k, v in template.items()}
    if isinstance(template, list):
        return [interpolate(item, variables) for item in template]
    return template


def _interpolate_string(template: str, variables: dict) -> Any:
    # Fast path: entire string is one placeholder -> return raw value
    match = _PLACEHOLDER_RE.fullmatch(template)
    if match:
        try:
            return _resolve(match.group(1), variables)
        except (KeyError, IndexError, ValueError, TypeError):
            return template

    # General case: replace each placeholder with its str() representation
    def _replacer(m: re.Match) -> str:
        try:
            value = _resolve(m.group(1), variables)
            return str(value)
        except (KeyError, IndexError, ValueError, TypeError):
            return m.group(0)  # leave placeholder as-is

    return _PLACEHOLDER_RE.sub(_replacer, template)
