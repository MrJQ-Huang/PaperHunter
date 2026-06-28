import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..utils.llm_client import LLMConfig, test_llm_connection

router = APIRouter()


class LLMSettingsRequest(BaseModel):
    llm_api_type: str
    llm_model: str
    llm_base_url: str
    llm_api_key: str | None = None
    cc_switch_config_path: str | None = None


class LLMTestRequest(BaseModel):
    llm_api_type: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None


class CCSwitchImportRequest(BaseModel):
    path: str | None = None
    save: bool = True
    test: bool = True


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}...{value[-4:]}"


def _runtime_config() -> dict[str, str]:
    return {
        "llm_api_type": settings.llm_api_type,
        "llm_model": settings.llm_model,
        "llm_base_url": settings.llm_base_url,
        "llm_api_key_masked": _mask_secret(settings.llm_api_key),
        "has_llm_api_key": bool(settings.llm_api_key and settings.llm_api_key != "tp-placeholder"),
        "cc_switch_config_path": settings.cc_switch_config_path,
        "download_dir": settings.download_dir,
    }


def _env_path() -> Path:
    return Path(".env")


def _write_env(updates: dict[str, str]) -> None:
    path = _env_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    for line in lines:
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)

    if output and output[-1].strip():
        output.append("")
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")

    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def _apply_runtime(updates: dict[str, str]) -> None:
    mapping = {
        "LLM_API_TYPE": "llm_api_type",
        "LLM_MODEL": "llm_model",
        "LLM_BASE_URL": "llm_base_url",
        "LLM_API_KEY": "llm_api_key",
        "CC_SWITCH_CONFIG_PATH": "cc_switch_config_path",
    }
    for env_key, attr in mapping.items():
        if env_key in updates:
            setattr(settings, attr, updates[env_key])


def _config_from_request(body: LLMTestRequest) -> LLMConfig:
    return LLMConfig(
        api_type=(body.llm_api_type or settings.llm_api_type or "anthropic").lower(),
        api_key=body.llm_api_key or settings.llm_api_key,
        base_url=body.llm_base_url or settings.llm_base_url,
        model=body.llm_model or settings.llm_model,
    )


@router.get("/settings/llm")
async def get_llm_settings():
    return _runtime_config()


@router.put("/settings/llm")
async def update_llm_settings(body: LLMSettingsRequest):
    api_type = body.llm_api_type.lower().strip()
    if api_type not in {"anthropic", "openai"}:
        raise HTTPException(status_code=400, detail="llm_api_type must be anthropic or openai")
    if not body.llm_model.strip() or not body.llm_base_url.strip():
        raise HTTPException(status_code=400, detail="模型和 API 地址不能为空")

    updates = {
        "LLM_API_TYPE": api_type,
        "LLM_MODEL": body.llm_model.strip(),
        "LLM_BASE_URL": body.llm_base_url.strip().rstrip("/"),
    }
    if body.llm_api_key is not None and body.llm_api_key.strip():
        updates["LLM_API_KEY"] = body.llm_api_key.strip()
    if body.cc_switch_config_path is not None:
        updates["CC_SWITCH_CONFIG_PATH"] = body.cc_switch_config_path.strip()

    _write_env(updates)
    _apply_runtime(updates)
    return {"ok": True, "config": _runtime_config()}


@router.post("/settings/llm/test")
async def test_llm_settings(body: LLMTestRequest):
    try:
        config = _config_from_request(body)
        result = await test_llm_connection(config)
        return result
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "api_type": body.llm_api_type or settings.llm_api_type,
            "model": body.llm_model or settings.llm_model,
            "base_url": body.llm_base_url or settings.llm_base_url,
        }


@router.post("/settings/llm/import-ccswitch")
async def import_ccswitch(body: CCSwitchImportRequest):
    config = _discover_ccswitch_config(body.path)
    if not config:
        raise HTTPException(status_code=404, detail="未找到可识别的 CC Switch/Claude/OpenAI 配置")

    updates = _updates_from_discovered_config(config)
    if body.save:
        _write_env(updates)
    _apply_runtime(updates)

    connection_test = None
    if body.test:
        try:
            connection_test = await test_llm_connection(
                LLMConfig(
                    api_type=config["llm_api_type"],
                    api_key=config["llm_api_key"],
                    base_url=config["llm_base_url"],
                    model=config["llm_model"],
                )
            )
        except Exception as e:
            connection_test = {
                "ok": False,
                "error": str(e),
                "api_type": config["llm_api_type"],
                "model": config["llm_model"],
                "base_url": config["llm_base_url"],
            }

    return {
        "ok": True,
        "config": _public_discovered_config(config),
        "saved": body.save,
        "connection_test": connection_test,
    }


def _updates_from_discovered_config(config: dict[str, str]) -> dict[str, str]:
    return {
        "LLM_API_TYPE": config["llm_api_type"],
        "LLM_MODEL": config["llm_model"],
        "LLM_BASE_URL": config["llm_base_url"],
        "LLM_API_KEY": config["llm_api_key"],
        "CC_SWITCH_CONFIG_PATH": config.get("cc_switch_config_path", ""),
    }


def _public_discovered_config(config: dict[str, str]) -> dict[str, Any]:
    return {
        "llm_api_type": config["llm_api_type"],
        "llm_model": config["llm_model"],
        "llm_base_url": config["llm_base_url"],
        "llm_api_key": "",
        "llm_api_key_masked": _mask_secret(config.get("llm_api_key", "")),
        "has_llm_api_key": bool(config.get("llm_api_key")),
        "cc_switch_config_path": config.get("cc_switch_config_path", ""),
        "download_dir": settings.download_dir,
        "source": config.get("source", ""),
        "provider_name": config.get("provider_name", ""),
    }


def _discover_ccswitch_config(path: str | None = None) -> dict[str, str] | None:
    ccswitch_config = _discover_from_ccswitch(path)
    if ccswitch_config:
        return ccswitch_config

    env_config = _discover_from_env()
    if env_config:
        return env_config

    config_path = path or settings.cc_switch_config_path or os.getenv("CC_SWITCH_CONFIG_PATH", "")
    if config_path:
        file_config = _discover_from_json_file(Path(config_path).expanduser())
        if file_config:
            return file_config
    return None


def _discover_from_ccswitch(path: str | None = None) -> dict[str, str] | None:
    candidates: list[Path] = []

    if path:
        given = Path(path).expanduser()
        candidates.append(given / "cc-switch.db" if given.is_dir() else given)

    for env_name in ("CC_SWITCH_CONFIG_PATH", "CC_SWITCH_HOME", "CCSWITCH_HOME"):
        env_path = os.getenv(env_name)
        if env_path:
            given = Path(env_path).expanduser()
            candidates.append(given / "cc-switch.db" if given.is_dir() else given)

    if settings.cc_switch_config_path:
        given = Path(settings.cc_switch_config_path).expanduser()
        candidates.append(given / "cc-switch.db" if given.is_dir() else given)

    candidates.extend(_standard_ccswitch_db_candidates())

    seen: set[Path] = set()
    for db_path in candidates:
        db_path = db_path.expanduser()
        if db_path in seen:
            continue
        seen.add(db_path)
        config = _discover_from_ccswitch_db(db_path)
        if config:
            return config
    return None


def _standard_ccswitch_db_candidates() -> list[Path]:
    candidates = [Path.home() / ".cc-switch" / "cc-switch.db"]
    appdata = os.getenv("APPDATA")
    localappdata = os.getenv("LOCALAPPDATA")
    if appdata:
        candidates.append(Path(appdata) / "com.ccswitch.desktop" / "cc-switch.db")
        candidates.extend(_read_ccswitch_app_paths(Path(appdata) / "com.ccswitch.desktop" / "app_paths.json"))
    if localappdata:
        candidates.append(Path(localappdata) / "com.ccswitch.desktop" / "cc-switch.db")
        candidates.extend(_read_ccswitch_app_paths(Path(localappdata) / "com.ccswitch.desktop" / "app_paths.json"))
    return candidates


def _read_ccswitch_app_paths(path: Path) -> list[Path]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    result: list[Path] = []
    for value in _flatten_json(data).values():
        if not value:
            continue
        p = Path(value).expanduser()
        result.append(p / "cc-switch.db" if p.is_dir() else p)
    return result


def _discover_from_ccswitch_db(db_path: Path) -> dict[str, str] | None:
    if not db_path.exists() or db_path.name != "cc-switch.db":
        return None

    current_ids = _read_current_ccswitch_provider_ids(db_path)

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = None
        for app_type, current_id in current_ids:
            if current_id:
                row = conn.execute(
                    "select * from providers where id = ? and app_type = ?",
                    (current_id, app_type),
                ).fetchone()
                if row is not None:
                    break
        if row is None:
            row = conn.execute(
                "select * from providers where app_type = 'claude' and is_current = 1 limit 1",
            ).fetchone()
        if row is None:
            row = conn.execute(
                "select * from providers where app_type in ('claude', 'codex') and is_current = 1 order by case app_type when 'claude' then 0 else 1 end limit 1",
            ).fetchone()
        if row is None:
            return None

        endpoint_row = conn.execute(
            "select url from provider_endpoints where provider_id = ? and app_type = ? order by id desc limit 1",
            (row["id"], row["app_type"]),
        ).fetchone()
        common_key = "common_config_codex" if row["app_type"] == "codex" else "common_config_claude"
        common_row = conn.execute("select value from settings where key = ?", (common_key,)).fetchone()
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass

    try:
        settings_config = json.loads(row["settings_config"] or "{}")
    except Exception:
        settings_config = {}
    try:
        meta = json.loads(row["meta"] or "{}")
    except Exception:
        meta = {}
    try:
        common_config = json.loads(common_row["value"] or "{}") if common_row else {}
    except Exception:
        common_config = {}

    env = settings_config.get("env") or {}
    api_format = str(meta.get("apiFormat") or settings_config.get("apiFormat") or "anthropic").lower()
    api_type = "openai" if api_format == "openai" else "anthropic"
    base_url = (
        env.get("ANTHROPIC_BASE_URL")
        or env.get("OPENAI_BASE_URL")
        or (endpoint_row["url"] if endpoint_row else "")
        or ("https://api.openai.com/v1" if api_type == "openai" else "https://api.anthropic.com")
    )
    api_key = (
        env.get("ANTHROPIC_AUTH_TOKEN")
        or env.get("ANTHROPIC_API_KEY")
        or env.get("OPENAI_API_KEY")
        or ""
    )
    model = _select_ccswitch_model(env, common_config, api_type)

    if not api_key and not base_url and not model:
        return None

    return {
        "llm_api_type": api_type,
        "llm_api_key": str(api_key),
        "llm_base_url": str(base_url).rstrip("/"),
        "llm_model": str(model),
        "cc_switch_config_path": str(db_path.parent),
        "source": "cc-switch",
        "provider_name": str(row["name"]),
    }


def _read_current_ccswitch_provider_ids(db_path: Path) -> list[tuple[str, str | None]]:
    settings_path = db_path.parent / "settings.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            return [
                ("claude", str(data.get("currentProviderClaude")) if data.get("currentProviderClaude") else None),
                ("codex", str(data.get("currentProviderCodex")) if data.get("currentProviderCodex") else None),
            ]
        except Exception:
            pass
    return [("claude", None), ("codex", None)]


def _select_ccswitch_model(env: dict[str, Any], common_config: dict[str, Any], api_type: str) -> str:
    if api_type == "openai":
        return str(env.get("OPENAI_MODEL") or env.get("MODEL") or "gpt-4.1-mini")

    configured = str(common_config.get("model") or "").lower()
    if configured in {"opus", "sonnet", "haiku"}:
        key = f"ANTHROPIC_DEFAULT_{configured.upper()}_MODEL"
        name_key = f"{key}_NAME"
        return str(env.get(key) or env.get(name_key) or env.get("ANTHROPIC_MODEL") or "claude-3-5-sonnet-latest")

    return str(
        env.get("ANTHROPIC_MODEL")
        or env.get("ANTHROPIC_DEFAULT_SONNET_MODEL")
        or env.get("ANTHROPIC_DEFAULT_OPUS_MODEL")
        or env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")
        or "claude-3-5-sonnet-latest"
    )


def _discover_from_env() -> dict[str, str] | None:
    anthropic_key = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")
    anthropic_base = os.getenv("ANTHROPIC_BASE_URL")
    anthropic_model = os.getenv("ANTHROPIC_MODEL") or os.getenv("CLAUDE_MODEL")
    if anthropic_key and (anthropic_base or anthropic_model):
        return {
            "llm_api_type": "anthropic",
            "llm_api_key": anthropic_key,
            "llm_base_url": anthropic_base or "https://api.anthropic.com",
            "llm_model": anthropic_model or "claude-3-5-sonnet-latest",
        }

    openai_key = os.getenv("OPENAI_API_KEY")
    openai_base = os.getenv("OPENAI_BASE_URL")
    openai_model = os.getenv("OPENAI_MODEL")
    if openai_key and (openai_base or openai_model):
        return {
            "llm_api_type": "openai",
            "llm_api_key": openai_key,
            "llm_base_url": openai_base or "https://api.openai.com/v1",
            "llm_model": openai_model or "gpt-4.1-mini",
        }
    return None


def _discover_from_json_file(path: Path) -> dict[str, str] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    flat = _flatten_json(data)
    key = _first(flat, ["api_key", "apikey", "auth_token", "anthropic_auth_token", "openai_api_key", "token"])
    base = _first(flat, ["base_url", "api_base", "anthropic_base_url", "openai_base_url", "url"])
    model = _first(flat, ["model", "default_model", "anthropic_model", "openai_model"])
    provider = (_first(flat, ["provider", "api_type", "type"]) or "").lower()

    if not key and not base and not model:
        return None
    api_type = "openai" if "openai" in provider else "anthropic"
    if base and ("openai" in base or "/chat/completions" in base):
        api_type = "openai"

    return {
        "llm_api_type": api_type,
        "llm_api_key": key or "",
        "llm_base_url": base or ("https://api.openai.com/v1" if api_type == "openai" else "https://api.anthropic.com"),
        "llm_model": model or ("gpt-4.1-mini" if api_type == "openai" else "claude-3-5-sonnet-latest"),
        "cc_switch_config_path": str(path),
    }


def _flatten_json(value: Any, prefix: str = "") -> dict[str, str]:
    result: dict[str, str] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten_json(item, child))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            result.update(_flatten_json(item, f"{prefix}.{idx}"))
    elif value is not None:
        result[prefix.lower()] = str(value)
    return result


def _first(flat: dict[str, str], names: list[str]) -> str | None:
    for wanted in names:
        for key, value in flat.items():
            if key.endswith(wanted.lower()) and value:
                return value
    return None
