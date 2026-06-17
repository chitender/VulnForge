"""Branch name template resolver.

Template variables:
  {image}   — image repository slug (slashes → hyphens)
  {tag}     — image tag
  {date}    — ISO date YYYY-MM-DD (caller supplies)
  {version} — free-text release version (user-supplied)
  {scan_id} — short scan UUID prefix (caller supplies)
"""
from __future__ import annotations


def resolve_branch(template: str, variables: dict[str, str]) -> str:
    """Substitute {key} placeholders in *template* with values from *variables*.

    - Unknown placeholders are left unchanged.
    - The `image` variable has slashes replaced with hyphens before substitution
      so it forms a valid branch-name segment.
    - Raises ValueError for an empty template.
    """
    if not template.strip():
        raise ValueError("Branch template must not be empty")

    result = template
    for key, value in variables.items():
        safe_value = value.replace("/", "-") if key == "image" else value
        result = result.replace(f"{{{key}}}", safe_value)

    return result
