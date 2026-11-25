"""The SCons configuration of the reaction_diffusion engine module."""

from typing import Any


def can_build(env: Any, platform: str) -> bool:
    return True


def configure(env: Any) -> None:
    pass
