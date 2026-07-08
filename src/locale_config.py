# locale_config.py
# Shared locale-alias configuration.
#
# Some locales can be "aliased" onto another locale so that their feeds reuse
# the feed already computed for the source locale, instead of running the full
# (and costly) LLM search + summary pipeline again for every language.
#
# Trade-off: an aliased locale serves the SOURCE locale's content verbatim
# (e.g. FR -> EN means French feeds contain English sources and English text).
#
# Configure via the LOCALE_ALIASES env var as a JSON object mapping
# alias -> source, e.g.  {"fr": "en"}. Falls back to DEFAULT_LOCALE_ALIASES.

import json
import os

DEFAULT_LOCALE_ALIASES = {"fr": "en", "es": "en"}


def get_locale_aliases():
    """Return the active alias map ({alias: source}), all lowercase."""
    raw = os.environ.get("LOCALE_ALIASES")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k).lower(): str(v).lower() for k, v in parsed.items()}
        except (json.JSONDecodeError, TypeError):
            pass
    return dict(DEFAULT_LOCALE_ALIASES)


def resolve_source(locale):
    """
    Return the source locale that should actually be computed for `locale`.
    An aliased locale resolves to its source; a non-aliased locale to itself.
    """
    return get_locale_aliases().get(locale.lower(), locale.lower())
