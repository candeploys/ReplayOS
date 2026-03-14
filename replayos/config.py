from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib

ALLOWED_PROVIDERS = {"local_qwen", "claude_api", "openai_api"}
ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass(frozen=True)
class ProviderConfig:
    default: str
    local_base_url: str
    local_model: str
    claude_model: str
    openai_model: str


@dataclass(frozen=True)
class SafetyConfig:
    require_ghost_run: bool
    require_approval_for_high_risk: bool


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int


@dataclass(frozen=True)
class AuthConfig:
    require_api_key: bool
    allow_localhost_without_key: bool
    api_keys: tuple[str, ...]


@dataclass(frozen=True)
class LimitsConfig:
    max_request_bytes: int
    default_search_limit: int
    max_search_limit: int
    default_recent_limit: int
    max_recent_limit: int
    default_top_k: int
    max_top_k: int
    rate_limit_requests: int
    rate_limit_window_seconds: int


@dataclass(frozen=True)
class ObservabilityConfig:
    log_level: str
    log_json: bool


@dataclass(frozen=True)
class RuntimeConfig:
    environment: str
    provider_timeout_seconds: int


@dataclass(frozen=True)
class AlertingConfig:
    error_rate_threshold: float
    error_window_seconds: int
    min_requests_for_alarm: int


@dataclass(frozen=True)
class DataPolicyConfig:
    default_retention_days: int
    allow_full_delete: bool


@dataclass(frozen=True)
class PluginConfig:
    directories: tuple[str, ...]


@dataclass(frozen=True)
class AppConfig:
    provider: ProviderConfig
    safety: SafetyConfig
    server: ServerConfig
    auth: AuthConfig
    limits: LimitsConfig
    observability: ObservabilityConfig
    runtime: RuntimeConfig
    alerting: AlertingConfig
    data_policy: DataPolicyConfig
    plugins: PluginConfig
    anthropic_api_key: str
    openai_api_key: str


def _bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, int):
        return value != 0
    return default


def _int(value: object, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return default


def _float(value: object, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _validate_config(config: AppConfig) -> None:
    if config.provider.default not in ALLOWED_PROVIDERS:
        allowed = ", ".join(sorted(ALLOWED_PROVIDERS))
        raise ValueError(f"provider.default must be one of: {allowed}")

    if not (1 <= config.server.port <= 65535):
        raise ValueError("server.port must be between 1 and 65535")

    if config.observability.log_level not in ALLOWED_LOG_LEVELS:
        allowed_levels = ", ".join(sorted(ALLOWED_LOG_LEVELS))
        raise ValueError(f"observability.log_level must be one of: {allowed_levels}")

    if config.limits.max_request_bytes < 1024:
        raise ValueError("limits.max_request_bytes must be >= 1024")

    if config.limits.default_search_limit <= 0 or config.limits.max_search_limit <= 0:
        raise ValueError("search limits must be positive")
    if config.limits.default_search_limit > config.limits.max_search_limit:
        raise ValueError("default_search_limit cannot exceed max_search_limit")

    if config.limits.default_recent_limit <= 0 or config.limits.max_recent_limit <= 0:
        raise ValueError("recent limits must be positive")
    if config.limits.default_recent_limit > config.limits.max_recent_limit:
        raise ValueError("default_recent_limit cannot exceed max_recent_limit")

    if config.limits.default_top_k <= 0 or config.limits.max_top_k <= 0:
        raise ValueError("top_k limits must be positive")
    if config.limits.default_top_k > config.limits.max_top_k:
        raise ValueError("default_top_k cannot exceed max_top_k")

    if config.limits.rate_limit_requests <= 0 or config.limits.rate_limit_window_seconds <= 0:
        raise ValueError("rate limit values must be positive")

    if config.runtime.provider_timeout_seconds <= 0:
        raise ValueError("runtime.provider_timeout_seconds must be positive")

    if not 0 < config.alerting.error_rate_threshold <= 1:
        raise ValueError("alerting.error_rate_threshold must be between 0 and 1")
    if config.alerting.error_window_seconds <= 0:
        raise ValueError("alerting.error_window_seconds must be positive")
    if config.alerting.min_requests_for_alarm <= 0:
        raise ValueError("alerting.min_requests_for_alarm must be positive")

    if config.data_policy.default_retention_days <= 0:
        raise ValueError("data_policy.default_retention_days must be positive")

    if config.auth.require_api_key and not config.auth.api_keys and not config.auth.allow_localhost_without_key:
        raise ValueError(
            "auth.require_api_key=true but no API keys were configured. "
            "Set REPLAYOS_API_KEYS in .env or disable require_api_key for local development."
        )


def load_config(config_path: Path, env_path: Path | None = None) -> AppConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    env_vars = dict(os.environ)
    if env_path is not None:
        env_vars.update(load_env_file(env_path))

    provider = raw.get("provider", {})
    local = provider.get("local_qwen", {})
    claude = provider.get("claude_api", {})
    openai = provider.get("openai_api", {})

    safety = raw.get("safety", {})
    server = raw.get("server", {})
    auth = raw.get("auth", {})
    limits = raw.get("limits", {})
    observability = raw.get("observability", {})
    runtime = raw.get("runtime", {})
    alerting = raw.get("alerting", {})
    data_policy = raw.get("data_policy", {})
    plugins = raw.get("plugins", {})

    configured_keys = _string_list(auth.get("api_keys", []))
    env_keys = _string_list(env_vars.get("REPLAYOS_API_KEYS", ""))
    api_keys = tuple(dict.fromkeys([*configured_keys, *env_keys]))

    plugin_dirs = _string_list(plugins.get("directories", []))
    plugin_dirs.extend(_string_list(env_vars.get("REPLAYOS_PLUGIN_DIRS", "")))

    config = AppConfig(
        provider=ProviderConfig(
            default=str(provider.get("default", "local_qwen")).strip(),
            local_base_url=str(local.get("base_url", "http://localhost:11434")).rstrip("/"),
            local_model=str(local.get("model", "qwen2.5:7b-instruct-q4_K_M")),
            claude_model=str(claude.get("model", "claude-sonnet-4")),
            openai_model=str(openai.get("model", "gpt-5-mini")),
        ),
        safety=SafetyConfig(
            require_ghost_run=_bool(safety.get("require_ghost_run", True), True),
            require_approval_for_high_risk=_bool(
                safety.get("require_approval_for_high_risk", True), True
            ),
        ),
        server=ServerConfig(
            host=str(server.get("host", "127.0.0.1")),
            port=_int(server.get("port", 8787), 8787),
        ),
        auth=AuthConfig(
            require_api_key=_bool(auth.get("require_api_key", True), True),
            allow_localhost_without_key=_bool(auth.get("allow_localhost_without_key", False), False),
            api_keys=api_keys,
        ),
        limits=LimitsConfig(
            max_request_bytes=_int(limits.get("max_request_bytes", 1_048_576), 1_048_576),
            default_search_limit=_int(limits.get("default_search_limit", 10), 10),
            max_search_limit=_int(limits.get("max_search_limit", 100), 100),
            default_recent_limit=_int(limits.get("default_recent_limit", 20), 20),
            max_recent_limit=_int(limits.get("max_recent_limit", 200), 200),
            default_top_k=_int(limits.get("default_top_k", 5), 5),
            max_top_k=_int(limits.get("max_top_k", 20), 20),
            rate_limit_requests=_int(limits.get("rate_limit_requests", 120), 120),
            rate_limit_window_seconds=_int(limits.get("rate_limit_window_seconds", 60), 60),
        ),
        observability=ObservabilityConfig(
            log_level=str(observability.get("log_level", "INFO")).strip().upper(),
            log_json=_bool(observability.get("log_json", True), True),
        ),
        runtime=RuntimeConfig(
            environment=str(runtime.get("environment", env_vars.get("REPLAYOS_ENV", "production"))).strip(),
            provider_timeout_seconds=_int(runtime.get("provider_timeout_seconds", 60), 60),
        ),
        alerting=AlertingConfig(
            error_rate_threshold=_float(alerting.get("error_rate_threshold", 0.2), 0.2),
            error_window_seconds=_int(alerting.get("error_window_seconds", 300), 300),
            min_requests_for_alarm=_int(alerting.get("min_requests_for_alarm", 20), 20),
        ),
        data_policy=DataPolicyConfig(
            default_retention_days=_int(data_policy.get("default_retention_days", 30), 30),
            allow_full_delete=_bool(data_policy.get("allow_full_delete", False), False),
        ),
        plugins=PluginConfig(directories=tuple(dict.fromkeys(plugin_dirs))),
        anthropic_api_key=env_vars.get("ANTHROPIC_API_KEY", ""),
        openai_api_key=env_vars.get("OPENAI_API_KEY", ""),
    )

    _validate_config(config)
    return config
