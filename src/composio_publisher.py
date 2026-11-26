"""Composio Facebook Page publishing adapter supporting ck_* MCP and ak_* SDK keys."""

from __future__ import annotations

import inspect
import json
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from src.config import AppConfig, GENERATED_DIR
from src.content_engine import PostPlan


class _ComposioBackend(Protocol):
    """Unified execution interface across Composio MCP HTTP and Python SDK."""

    def get_schema_properties(self, slug: str) -> set[str]:
        ...

    def execute(self, slug: str, arguments: dict[str, Any], account: str | None = None) -> Any:
        ...

    def list_active_facebook_accounts(self) -> list[str]:
        ...


def _extract_payload_data(raw_response: Any) -> Any:
    """Normalize Composio execute response across SDK and MCP wrapper formats."""
    if isinstance(raw_response, dict):
        if "data" in raw_response and raw_response["data"] is not None:
            return raw_response["data"]
        return raw_response
    if hasattr(raw_response, "model_dump"):
        return _extract_payload_data(raw_response.model_dump())
    return raw_response


class _McpHttpBackend:
    """Calls Composio Connect MCP (https://connect.composio.dev/mcp) with ck_* consumer key."""

    def __init__(self, mcp_url: str, consumer_key: str, default_account: str = "") -> None:
        self._url = mcp_url
        self._default_account = default_account.strip()
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "x-consumer-api-key": consumer_key,
        }
        self._req_id = 0

    def _call_mcp(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        req = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", "ignore")

        rpc_obj: dict[str, Any] | None = None
        for line in raw.splitlines():
            if line.startswith("data: "):
                rpc_obj = json.loads(line[6:])
                break
        if rpc_obj is None:
            rpc_obj = json.loads(raw)

        if "error" in rpc_obj:
            raise RuntimeError(f"Composio MCP RPC error: {rpc_obj['error']}")

        result = rpc_obj.get("result") or {}
        content_items = result.get("content") or []
        if content_items and "text" in content_items[0]:
            parsed_text = json.loads(content_items[0]["text"])
            if result.get("isError"):
                raise RuntimeError(f"Composio MCP tool error: {parsed_text}")
            return parsed_text
        if result.get("isError"):
            raise RuntimeError(f"Composio MCP tool error: {result}")
        return result

    def list_active_facebook_accounts(self) -> list[str]:
        if self._default_account:
            return [self._default_account]
        try:
            res = self._call_mcp(
                "COMPOSIO_MANAGE_CONNECTIONS",
                {"toolkits": [{"name": "facebook", "action": "list"}]},
            )
            fb_info = ((res.get("data") or {}).get("results") or {}).get("facebook") or {}
            accounts = fb_info.get("accounts") or []
            active = [a for a in accounts if str(a.get("status", "")).lower() == "active"]
            active.sort(key=lambda a: (0 if a.get("is_default") else 1))
            return [str(a["id"]) for a in active if a.get("id")]
        except Exception:
            return []

    def get_schema_properties(self, slug: str) -> set[str]:
        try:
            res = self._call_mcp("COMPOSIO_GET_TOOL_SCHEMAS", {"tool_slugs": [slug]})
            schemas = (res.get("data") or {}).get("tool_schemas") or {}
            props = ((schemas.get(slug) or {}).get("input_schema") or {}).get("properties") or {}
            return set(props.keys())
        except Exception:
            return set()

    def execute(self, slug: str, arguments: dict[str, Any], account: str | None = None) -> Any:
        chosen_account = (account or self._default_account).strip()
        if not chosen_account:
            active_accounts = self.list_active_facebook_accounts()
            if active_accounts:
                chosen_account = active_accounts[0]

        tool_entry: dict[str, Any] = {"tool_slug": slug, "arguments": arguments}
        if chosen_account:
            tool_entry["account"] = chosen_account

        res = self._call_mcp(
            "COMPOSIO_MULTI_EXECUTE_TOOL",
            {
                "tools": [tool_entry],
                "sync_response_to_workbench": False,
                "thought": f"Execute {slug} for automated Facebook Page publishing.",
                "current_step": slug,
                "current_step_metric": "1/1",
            },
        )
        if not res.get("successful", True) and res.get("error"):
            raise RuntimeError(str(res["error"]))
        results = (res.get("data") or {}).get("results") or []
        if results:
            first = results[0]
            if first.get("error"):
                raise RuntimeError(str(first["error"]))
            response_obj = first.get("response") or {}
            if response_obj.get("successful") is False and response_obj.get("error"):
                raise RuntimeError(str(response_obj["error"]))
            return response_obj.get("data") if "data" in response_obj else response_obj
        return res.get("data", res)


class _SdkBackend:
    """Calls Composio Python SDK directly with an ak_* project API key."""

    def __init__(self, api_key: str, user_id: str, allowed_dir: Path) -> None:
        from composio import Composio  # type: ignore

        sig = inspect.signature(Composio)
        kwargs: dict[str, Any] = {"api_key": api_key}
        if "dangerously_allow_auto_upload_download_files" in sig.parameters:
            kwargs["dangerously_allow_auto_upload_download_files"] = True
        if "file_upload_dirs" in sig.parameters:
            kwargs["file_upload_dirs"] = [str(allowed_dir.resolve())]
        self._client = Composio(**kwargs)
        self._user_id = user_id

    def list_active_facebook_accounts(self) -> list[str]:
        return []

    def get_schema_properties(self, slug: str) -> set[str]:
        try:
            tool = self._client.tools.get_raw_composio_tool_by_slug(slug)
            raw = tool.model_dump() if hasattr(tool, "model_dump") else dict(tool)
            params = raw.get("input_parameters") or raw.get("parameters") or {}
            props = params.get("properties") or {}
            return set(props.keys())
        except Exception:
            return set()

    def execute(self, slug: str, arguments: dict[str, Any], account: str | None = None) -> Any:
        sig = inspect.signature(self._client.tools.execute)
        kwargs: dict[str, Any] = {
            "slug": slug,
            "user_id": self._user_id,
            "arguments": arguments,
        }
        if "dangerously_skip_version_check" in sig.parameters:
            kwargs["dangerously_skip_version_check"] = True
        if "slug" not in sig.parameters:
            return self._client.tools.execute(slug, user_id=self._user_id, arguments=arguments)
        return self._client.tools.execute(**kwargs)


def _select_backend(config: AppConfig, allowed_dir: Path) -> _ComposioBackend:
    """Pick MCP HTTP backend for ck_* keys or Python SDK backend for ak_* keys."""
    if not config.composio_api_key:
        raise RuntimeError("COMPOSIO_API_KEY is missing. Set it in environment variables or GitHub Secrets.")
    if config.composio_api_key.startswith("ck_"):
        return _McpHttpBackend(
            config.composio_mcp_url,
            config.composio_api_key,
            default_account=config.composio_facebook_account,
        )
    return _SdkBackend(config.composio_api_key, config.composio_user_id, allowed_dir)


def _pick_key(available: set[str], candidates: tuple[str, ...], fallback: str) -> str:
    """Choose the first matching parameter key from a schema property set."""
    for name in candidates:
        if name in available:
            return name
    return fallback


def _extract_pages_list(resp: Any) -> list[dict[str, Any]]:
    data = _extract_payload_data(resp)
    if isinstance(data, dict):
        for key in ("data", "pages", "items", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    if isinstance(data, list):
        return data
    return []


def list_managed_pages(config: AppConfig) -> list[dict[str, Any]]:
    """Fetch all unique Facebook Pages across active Composio Facebook connections."""
    backend = _select_backend(config, GENERATED_DIR)
    accounts = backend.list_active_facebook_accounts()
    if not accounts:
        return _extract_pages_list(backend.execute("FACEBOOK_LIST_MANAGED_PAGES", {}))

    seen_ids: set[str] = set()
    all_pages: list[dict[str, Any]] = []
    for acc_id in accounts:
        try:
            resp = backend.execute("FACEBOOK_LIST_MANAGED_PAGES", {}, account=acc_id)
            for page in _extract_pages_list(resp):
                pid = str(page.get("id") or page.get("page_id") or "").strip()
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    page_copy = dict(page)
                    page_copy["composio_account"] = acc_id
                    all_pages.append(page_copy)
        except Exception:
            continue
    return all_pages


def resolve_target_pages(config: AppConfig) -> list[dict[str, str]]:
    """Return list of target Facebook pages ({id, name, account}) — all managed pages by default."""
    raw_ids = config.facebook_page_id.strip()
    if raw_ids and raw_ids.lower() != "all":
        ids = [part.strip() for part in raw_ids.split(",") if part.strip()]
        return [{"id": pid, "name": config.brand_name, "account": config.composio_facebook_account} for pid in ids]

    pages = list_managed_pages(config)
    resolved: list[dict[str, str]] = []
    for page in pages:
        pid = str(page.get("id") or page.get("page_id") or "").strip()
        if pid:
            pname = str(page.get("name") or config.brand_name).strip()
            acc = str(page.get("composio_account") or config.composio_facebook_account).strip()
            resolved.append({"id": pid, "name": pname, "account": acc})
    if not resolved:
        raise RuntimeError(
            "No Facebook Page found via Composio. Connect your Facebook Page in Composio or set FACEBOOK_PAGE_ID."
        )
    return resolved


def resolve_page_id(config: AppConfig) -> str:
    """Return configured FACEBOOK_PAGE_ID or auto-discover the first managed page."""
    return resolve_target_pages(config)[0]["id"]


def publish_post(
    config: AppConfig,
    plan: PostPlan,
    image_paths: list[Path],
    public_urls: list[str] | None = None,
    target_page_id: str | None = None,
    account: str | None = None,
) -> dict[str, Any]:
    """Publish a single photo or multi-photo carousel post to Facebook via Composio."""
    if not image_paths:
        raise ValueError("Cannot publish a post without at least one rendered image.")

    backend = _select_backend(config, image_paths[0].parent)
    page_id = target_page_id or resolve_page_id(config)
    media_refs = (
        public_urls
        if public_urls and len(public_urls) == len(image_paths)
        else [str(p.resolve()) for p in image_paths]
    )

    if plan.post_type == "carousel" and len(media_refs) > 1:
        try:
            props = backend.get_schema_properties("FACEBOOK_CREATE_MULTI_PHOTO_POST")
            page_key = _pick_key(props, ("page_id", "id"), "page_id")
            msg_key = _pick_key(props, ("message", "caption", "text"), "message")
            urls_key = _pick_key(props, ("photo_urls", "urls", "images", "media_urls", "photos"), "photo_urls")
            args = {
                page_key: page_id,
                msg_key: plan.caption,
                urls_key: media_refs,
            }
            result = backend.execute("FACEBOOK_CREATE_MULTI_PHOTO_POST", args, account=account)
            return {
                "action": "FACEBOOK_CREATE_MULTI_PHOTO_POST",
                "page_id": page_id,
                "result": _extract_payload_data(result),
            }
        except Exception as multi_err:
            fallback = _publish_single_photo(backend, page_id, plan.caption, media_refs[0], account=account)
            fallback["carousel_fallback_reason"] = str(multi_err)
            return fallback

    return _publish_single_photo(backend, page_id, plan.caption, media_refs[0], account=account)


def _publish_single_photo(
    backend: _ComposioBackend,
    page_id: str,
    caption: str,
    media_ref: str,
    account: str | None = None,
) -> dict[str, Any]:
    """Publish a single photo post via FACEBOOK_CREATE_PHOTO_POST."""
    props = backend.get_schema_properties("FACEBOOK_CREATE_PHOTO_POST")
    page_key = _pick_key(props, ("page_id", "id"), "page_id")
    msg_key = _pick_key(props, ("message", "caption", "text"), "message")
    if media_ref.startswith("http://") or media_ref.startswith("https://"):
        media_key = _pick_key(props, ("url", "photo", "image", "source"), "url")
    else:
        media_key = _pick_key(props, ("source", "image", "photo", "url"), "source")

    args: dict[str, Any] = {
        page_key: page_id,
        msg_key: caption,
        media_key: media_ref,
    }
    if "published" in props:
        args["published"] = True

    result = backend.execute("FACEBOOK_CREATE_PHOTO_POST", args, account=account)
    return {
        "action": "FACEBOOK_CREATE_PHOTO_POST",
        "page_id": page_id,
        "result": _extract_payload_data(result),
    }
