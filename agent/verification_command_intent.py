"""Distinguish executed checks from discovery and selection flags."""

from __future__ import annotations

import shlex


def verification_intent(canonical: str, trailing_args: list[str]) -> tuple[bool, bool]:
    """Return (executes_checks, filtered). Unknown runners keep existing behavior.

    The canonical recipe may itself select a subset. Inspect it as well as the
    appended arguments so a targeted recipe cannot be promoted to a full suite.
    """
    recipe = shlex.split(canonical)
    runners = [index for index, token in enumerate(recipe)
               if token.replace("\\", "/").rsplit("/", 1)[-1] in {"pytest", "pytest.exe", "run_tests.sh"}]
    # `python -m pytest` uses -m to select the module, not a pytest marker.
    tokens = (recipe[runners[-1] + 1:] if runners else recipe) + trailing_args
    options = {arg.split("=", 1)[0] for arg in tokens if arg.startswith("-")}
    if options & {"--help", "--version", "-h"}:
        return False, False
    if not runners:
        return True, False
    if options & {"--collect-only", "--co", "--setup-plan"}:
        return False, False
    selectors = {"-k", "-m", "--deselect", "--ignore", "--ignore-glob", "--lf", "--last-failed", "--testmon"}
    compact_selector = any(arg.startswith(("-k", "-m")) and len(arg) > 2 for arg in tokens)
    return True, bool(options & selectors) or compact_selector
