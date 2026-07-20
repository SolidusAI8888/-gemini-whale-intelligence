from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WhaleProfile:
    name: str
    category: str
    influence: float = 1.0


class WhaleRegistry:
    """Central actor registry with safe defaults for unknown public filers."""

    def __init__(self) -> None:
        self._profiles: dict[str, WhaleProfile] = {}

    @staticmethod
    def _key(name: str) -> str:
        return " ".join((name or "").strip().lower().split())

    def register(self, profile: WhaleProfile) -> None:
        self._profiles[self._key(profile.name)] = profile

    def get(self, name: str, category: str = "Unknown") -> WhaleProfile:
        return self._profiles.get(self._key(name), WhaleProfile(name=name or "Unknown", category=category, influence=1.0))


DEFAULT_REGISTRY = WhaleRegistry()
for _profile in (
    WhaleProfile("Warren Buffett", "Institutional", 1.15),
    WhaleProfile("Bill Ackman", "Institutional", 1.12),
    WhaleProfile("Nancy Pelosi", "Political", 1.10),
    WhaleProfile("Donald Trump", "Political/Executive", 1.10),
):
    DEFAULT_REGISTRY.register(_profile)
