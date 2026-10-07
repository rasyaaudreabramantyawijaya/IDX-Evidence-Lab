"""Runtime settings read from the environment, validated once at startup."""
import ipaddress
import os
from dataclasses import dataclass

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5500
DEFAULT_CHAT_PER_MIN = 20
DEFAULT_POST_PER_MIN = 120


@dataclass(frozen=True)
class Settings:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    chat_per_min: int = DEFAULT_CHAT_PER_MIN
    post_per_min: int = DEFAULT_POST_PER_MIN

    @property
    def is_loopback(self) -> bool:
        if self.host == "localhost":
            return True
        try:
            return ipaddress.ip_address(self.host).is_loopback
        except ValueError:
            return False


def _int(env, name: str, default: int, low: int, high: int) -> int:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}, got {value}")
    return value


def load_settings(env=None) -> Settings:
    env = os.environ if env is None else env
    return Settings(
        host=(env.get("IDXEL_HOST") or DEFAULT_HOST).strip(),
        port=_int(env, "IDXEL_PORT", DEFAULT_PORT, 1, 65535),
        chat_per_min=_int(env, "IDXEL_RL_CHAT_PER_MIN", DEFAULT_CHAT_PER_MIN, 0, 100_000),
        post_per_min=_int(env, "IDXEL_RL_POST_PER_MIN", DEFAULT_POST_PER_MIN, 0, 100_000),
    )
