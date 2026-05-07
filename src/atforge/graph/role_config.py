"""Role configuration loader for A2 multi-agent nodes.

Provides default configs for explorer/exploiter/critic and loads overrides
from atforge.yaml when it exists. atforge.yaml is auto-discovered at the
repo root (working directory). All fields are optional in YAML — omitted
fields fall back to code defaults.

YAML structure:
  roles:
    explorer:
      temperature: 0.9
      max_iterations: 4
      llm_priority: [gemini, groq]
      model: null
      system_prompt: |
        Custom explorer prompt here.
    exploiter:
      ...
    critic:
      ...
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from atforge.evolution.research_prompts import (
    CRITIC_SYSTEM_PROMPT,
    EXPLOITER_SYSTEM_PROMPT,
    EXPLORER_SYSTEM_PROMPT,
)
from atforge.graph.deps import AgentRoleConfig

_ROLE_DEFAULTS: dict[str, dict[str, Any]] = {
    "explorer": {
        "temperature": 0.9,
        "max_iterations": 4,
        "system_prompt": EXPLORER_SYSTEM_PROMPT,
        "llm_priority": (),
        "model": None,
    },
    "exploiter": {
        "temperature": 0.4,
        "max_iterations": 4,
        "system_prompt": EXPLOITER_SYSTEM_PROMPT,
        "llm_priority": (),
        "model": None,
    },
    "critic": {
        "temperature": 0.3,
        "max_iterations": 3,
        "system_prompt": CRITIC_SYSTEM_PROMPT,
        "llm_priority": (),
        "model": None,
    },
}


def default_role_configs() -> dict[str, AgentRoleConfig]:
    """Return hardcoded defaults for all three A2 agent roles."""
    return {role: AgentRoleConfig(role=role, **params) for role, params in _ROLE_DEFAULTS.items()}


def load_role_configs(config_path: Path | None = None) -> dict[str, AgentRoleConfig]:
    """Load role configs from YAML, falling back to defaults for absent/missing fields.

    Args:
        config_path: Path to YAML file. Defaults to ``atforge.yaml`` in the
            current working directory. Missing file → pure defaults returned.
    """
    if config_path is None:
        config_path = Path("atforge.yaml")

    configs = default_role_configs()

    if not config_path.exists():
        return configs

    import yaml

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    roles_data: dict[str, dict[str, Any]] = data.get("roles", {})
    for role_name, overrides in roles_data.items():
        if not overrides:
            continue
        base = _ROLE_DEFAULTS.get(role_name, {}).copy()
        base.update({k: v for k, v in overrides.items() if v is not None or k == "model"})

        # Normalize llm_priority to tuple
        raw_priority = base.get("llm_priority", ())
        if isinstance(raw_priority, list):
            base["llm_priority"] = tuple(raw_priority)

        configs[role_name] = AgentRoleConfig(role=role_name, **base)

    return configs
