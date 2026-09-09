"""Hard exclusions → explicit filter_by fragments.

These are ALWAYS ANDed and ALWAYS passed as the explicit filter_by — never merged
into query text, never left to an LLM. The LLM's generated filter is ANDed on top,
so it can only narrow the result set, never widen it. That is the safety invariant.
"""


def exclusion_fragments(exclude_allergens: list[str], diet_flags: list[str]) -> list[str]:
    frags: list[str] = []
    for allergen in exclude_allergens:
        frags.append(f"allergens:!={allergen.strip().lower()}")
    for flag in diet_flags:
        frags.append(f"diet_flags:={flag.strip().lower()}")
    return frags


def has_hard_exclusions(exclude_allergens: list[str], diet_flags: list[str]) -> bool:
    return bool(exclude_allergens or diet_flags)
