"""Unit tests for content engine, renderer, art engine, and Composio publisher."""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.art_engine import _try_cloudflare_flux, build_illustrated_svg
from src.card_renderer import build_card_html
from src.composio_publisher import list_managed_pages, publish_post
from src.config import ARCHETYPES_PATH, AppConfig, QUOTE_VAULT_PATH
from src.content_engine import PostPlan, SlideContent, build_post_plan, load_json, save_history
from src.main import generate_and_render, resolve_slot


def _test_config(**overrides: str) -> AppConfig:
    base = dict(
        brand_name="Attitude | Motivation | Mindset",
        brand_monogram="AP",
        brand_handle="@attitude__test",
        composio_api_key="test-key",
        composio_user_id="test-user",
        composio_mcp_url="https://connect.composio.dev/mcp",
        composio_facebook_account="",
        facebook_page_id="",
        gemini_api_key="",
        openai_api_key="",
        hf_token="",
        pollinations_api_key="",
        cloudflare_account_id="",
        cloudflare_api_token="",
        use_composio_fal=False,
        public_media_base_url="",
    )
    base.update(overrides)
    return AppConfig(**base)


class TestContentAndData(unittest.TestCase):
    def test_top_50_archetypes_valid_and_mapped(self) -> None:
        archetypes = load_json(ARCHETYPES_PATH, {})["archetypes"]
        vault = load_json(QUOTE_VAULT_PATH, {})
        themes = set(vault["visual_themes"].keys())

        self.assertEqual(len(archetypes), 50)
        for item in archetypes:
            self.assertIn(item["visual_theme"], themes)
            self.assertTrue(item["hashtags"])

    def test_slots_deduplicate_and_fallback_to_combinatorial(self) -> None:
        config = _test_config()
        with tempfile.TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "history.json"
            seen_hashes: set[str] = set()

            for run_idx in range(16):
                slot = (run_idx % 4) + 1
                plan = build_post_plan(config, slot=slot, seed=100 + run_idx, history_path=history_path)
                self.assertNotIn(plan.content_hash, seen_hashes)
                self.assertTrue(plan.slides)
                self.assertIn("#", plan.caption)
                if slot == 2:
                    self.assertEqual(plan.post_type, "carousel")
                    self.assertGreaterEqual(len(plan.slides), 4)
                else:
                    self.assertEqual(plan.post_type, "single")
                seen_hashes.add(plan.content_hash)
                save_history(plan, {"ok": True}, history_path=history_path)

            saved = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["hashes"]), 16)

    def test_resolve_slot_utc_mapping(self) -> None:
        expected = [(4, 1), (8, 2), (12, 3), (16, 4), (22, 4)]
        for hour, slot in expected:
            dt = datetime(2026, 11, 27, hour, 30, tzinfo=timezone.utc)
            self.assertEqual(resolve_slot("auto", utc_now=dt), slot)


class TestRenderingAndArt(unittest.TestCase):
    def test_all_modern_visual_styles_render_valid_svg_and_html(self) -> None:
        config = _test_config()
        styles = [
            ("paper_sketch", "cliff_birds", "#DC2626"),
            ("paper_sketch", "chained_mind", "#DC2626"),
            ("sunrise_metaphor", "crimson_tree", "#DC2626"),
            ("saffron_editorial", "strategist", "#111111"),
            ("cartoon_metaphor", "wrong_person_tap", "#2563EB"),
            ("gold_spotlight", "mentor_split", "#FACC15"),
            ("monochrome_alpha", "lion", "#FF3B30"),
        ]
        for layout_style, motif, accent in styles:
            svg = build_illustrated_svg(layout_style, motif, accent, seed=42)
            self.assertTrue(svg.startswith("<svg"))
            self.assertIn("</svg>", svg)
            slide = SlideContent(
                quote="TRUST NO <FAKE> FRIENDS. WALK ALONE.",
                accent="WALK ALONE.",
                badge="RULE #01",
                visual_theme="dark_lion",
            )
            html_out = build_card_html(
                config,
                slide,
                "data:image/svg+xml;base64,AAAA",
                accent_color=accent,
                layout_style=layout_style,
                svg_motif=motif,
            )
            self.assertIn("&lt;fake&gt;", html_out.lower())
            self.assertIn("walk alone.", html_out.lower())

    def test_cloudflare_flux_and_ai_art_blend(self) -> None:
        import base64
        from unittest import mock

        fake_png = b"\x89PNG\r\n\x1a\n" + b"0" * 16000
        b64_png = base64.b64encode(fake_png).decode("ascii")

        class FakeResp:
            def read(self) -> bytes:
                return json.dumps({"success": True, "result": {"image": b64_png}}).encode("utf-8")

            def __enter__(self) -> "FakeResp":
                return self

            def __exit__(self, *args) -> None:
                return None

        with mock.patch("urllib.request.urlopen", return_value=FakeResp()):
            out = _try_cloudflare_flux("charcoal sketch of wolf", "acc123", "tok123")
            self.assertEqual(out, fake_png)

        config = _test_config()
        slide = SlideContent("NEVER BE AN OPTION", "OPTION", "", "dark_eagle")
        html_ai = build_card_html(
            config,
            slide,
            "data:image/png;base64,AAAA",
            layout_style="paper_sketch",
            is_ai_art=True,
        )
        self.assertIn("mix-blend-mode: multiply", html_ai)

    def test_multi_page_manifest_produces_distinct_posts_per_page(self) -> None:
        config = _test_config()
        pages = [
            {"id": "111", "name": "Mallick Yt"},
            {"id": "222", "name": "Anime kid Story"},
            {"id": "333", "name": "online course"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            manifest = generate_and_render(
                config=config,
                slot=2,
                output_dir=out_dir,
                allow_remote_art=False,
                seed=77,
                pages=pages,
            )
            self.assertEqual(manifest["pages_count"], 3)
            hashes = {job["content_hash"] for job in manifest["jobs"]}
            self.assertEqual(len(hashes), 3)
            for job in manifest["jobs"]:
                self.assertEqual(job["post_type"], "carousel")
                self.assertGreaterEqual(len(job["cards"]), 4)
                for card in job["cards"]:
                    self.assertTrue(Path(card["html_path"]).exists())


class TestComposioPublisher(unittest.TestCase):
    def test_composio_discovery_and_carousel_fallback(self) -> None:
        calls: list[tuple[str, dict]] = []

        class FakeTool:
            def __init__(self, props: dict) -> None:
                self._props = props

            def model_dump(self) -> dict:
                return {"input_parameters": {"properties": self._props}}

        class FakeTools:
            def get_raw_composio_tool_by_slug(self, slug: str) -> FakeTool:
                if slug == "FACEBOOK_CREATE_MULTI_PHOTO_POST":
                    return FakeTool({"page_id": {}, "message": {}, "photo_urls": {}})
                return FakeTool({"page_id": {}, "message": {}, "url": {}, "published": {}})

            def execute(self, slug: str, user_id: str, arguments: dict, dangerously_skip_version_check: bool = True) -> dict:
                calls.append((slug, arguments))
                if slug == "FACEBOOK_LIST_MANAGED_PAGES":
                    return {"data": {"pages": [{"id": "99887766", "name": "Test Page"}]}}
                if slug == "FACEBOOK_CREATE_MULTI_PHOTO_POST":
                    raise RuntimeError("Simulated multi-photo endpoint constraint")
                return {"data": {"post_id": "99887766_12345"}}

        class FakeComposio:
            def __init__(self, api_key: str, **kwargs) -> None:
                self.tools = FakeTools()

        fake_mod = types.ModuleType("composio")
        fake_mod.Composio = FakeComposio  # type: ignore[attr-defined]
        prev_mod = sys.modules.get("composio")
        sys.modules["composio"] = fake_mod

        try:
            config = _test_config()
            pages = list_managed_pages(config)
            self.assertEqual(pages[0]["id"], "99887766")

            with tempfile.TemporaryDirectory() as tmp:
                img1 = Path(tmp) / "c1.jpg"
                img2 = Path(tmp) / "c2.jpg"
                img1.write_bytes(b"\xff\xd8\xff" + b"0" * 50)
                img2.write_bytes(b"\xff\xd8\xff" + b"0" * 50)

                plan = PostPlan(
                    slot=2,
                    archetype_id=2,
                    archetype_name="Warrior Mindset Rules",
                    post_type="carousel",
                    caption="Follow for rules",
                    slides=[SlideContent("RULE 1", "RULE"), SlideContent("RULE 2", "RULE")],
                    content_hash="abc123",
                )
                res = publish_post(
                    config=config,
                    plan=plan,
                    image_paths=[img1, img2],
                    public_urls=["https://example.com/1.jpg", "https://example.com/2.jpg"],
                )
                self.assertEqual(res["action"], "FACEBOOK_CREATE_PHOTO_POST")
                self.assertIn("carousel_fallback_reason", res)
                self.assertEqual(res["page_id"], "99887766")
                self.assertEqual(calls[-1][0], "FACEBOOK_CREATE_PHOTO_POST")
                self.assertEqual(calls[-1][1]["url"], "https://example.com/1.jpg")
        finally:
            if prev_mod is not None:
                sys.modules["composio"] = prev_mod
            else:
                sys.modules.pop("composio", None)

    def test_ck_mcp_backend_sse_and_multi_photo(self) -> None:
        from unittest import mock

        captured_requests: list[dict] = []

        class FakeResponse:
            def __init__(self, body_str: str) -> None:
                self._data = body_str.encode("utf-8")

            def read(self) -> bytes:
                return self._data

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args) -> None:
                return None

        def fake_urlopen(req, timeout=45):
            payload = json.loads(req.data.decode("utf-8"))
            captured_requests.append({"headers": dict(req.header_items()), "payload": payload})
            tool_name = payload["params"]["name"]
            if tool_name == "COMPOSIO_MANAGE_CONNECTIONS":
                inner = {
                    "successful": True,
                    "data": {
                        "results": {
                            "facebook": {
                                "accounts": [
                                    {"id": "fb_acc_1", "status": "active", "is_default": True},
                                    {"id": "fb_acc_2", "status": "active", "is_default": False},
                                ]
                            }
                        }
                    },
                }
            elif tool_name == "COMPOSIO_GET_TOOL_SCHEMAS":
                inner = {
                    "successful": True,
                    "data": {
                        "tool_schemas": {
                            "FACEBOOK_CREATE_MULTI_PHOTO_POST": {
                                "input_schema": {
                                    "properties": {"page_id": {}, "message": {}, "photo_urls": {}}
                                }
                            }
                        }
                    },
                }
            else:
                slug = payload["params"]["arguments"]["tools"][0]["tool_slug"]
                if slug == "FACEBOOK_LIST_MANAGED_PAGES":
                    inner = {
                        "successful": True,
                        "data": {"results": [{"response": {"data": {"data": [{"id": "55443322"}]}}}]},
                    }
                else:
                    inner = {
                        "successful": True,
                        "data": {"results": [{"response": {"data": {"id": "55443322_999"}}}]},
                    }
            sse = f': connected\n\nevent: message\ndata: {json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": json.dumps(inner)}]}})}\n\n'
            return FakeResponse(sse)

        config = _test_config(composio_api_key="ck_sample_consumer_key")
        with tempfile.TemporaryDirectory() as tmp, mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            img1 = Path(tmp) / "c1.jpg"
            img2 = Path(tmp) / "c2.jpg"
            img1.write_bytes(b"\xff\xd8\xff" + b"0" * 50)
            img2.write_bytes(b"\xff\xd8\xff" + b"0" * 50)

            plan = PostPlan(
                slot=2,
                archetype_id=2,
                archetype_name="Warrior Mindset Rules",
                post_type="carousel",
                caption="Follow for rules",
                slides=[SlideContent("RULE 1", "RULE"), SlideContent("RULE 2", "RULE")],
                content_hash="mcp123",
            )
            res = publish_post(
                config=config,
                plan=plan,
                image_paths=[img1, img2],
                public_urls=["https://example.com/1.jpg", "https://example.com/2.jpg"],
            )
            self.assertEqual(res["action"], "FACEBOOK_CREATE_MULTI_PHOTO_POST")
            self.assertEqual(res["page_id"], "55443322")
            self.assertEqual(res["result"]["id"], "55443322_999")
            self.assertEqual(captured_requests[0]["headers"]["X-consumer-api-key"], "ck_sample_consumer_key")


if __name__ == "__main__":
    unittest.main()
