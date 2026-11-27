"""Unit tests for content engine, renderer, art engine, and Composio publisher."""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.art_engine import _try_cloudflare_flux, _try_deepai, _try_gemini_imagen, build_illustrated_svg
from src.card_renderer import build_card_html
from src.composio_publisher import list_managed_pages, publish_post, resolve_target_pages
from src.config import ARCHETYPES_PATH, AppConfig, QUOTE_VAULT_PATH
from src.content_engine import PostPlan, SlideContent, _infer_metaphor_prompt, build_post_plan, load_json, save_history
from src.main import _publish_manifest_jobs, generate_and_render, resolve_slot
from src.music_engine import select_background_track
from src.video_engine import _build_single_card_cmd, _build_slideshow_cmd


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
        deepai_api_key="",
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
            ("pastel_viral", "pastel_ladder", "#E11D48"),
            ("vibrant_magazine", "sunburst_peak", "#2563EB"),
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

        seen_cf_urls: list[str] = []

        class FakeResp:
            def read(self) -> bytes:
                return json.dumps({"success": True, "result": {"image": b64_png}}).encode("utf-8")

            def __enter__(self) -> "FakeResp":
                return self

            def __exit__(self, *args) -> None:
                return None

        def fake_cf_open(req, timeout=75):
            seen_cf_urls.append(req.full_url)
            return FakeResp()

        with mock.patch("urllib.request.urlopen", side_effect=fake_cf_open):
            out = _try_cloudflare_flux("cinematic cliff climber at sunrise", "acc123", "tok123")
            self.assertEqual(out, fake_png)
            self.assertIn("flux-2-klein-9b", seen_cf_urls[0])

        def fake_deepai_open(req, timeout=60):
            class Resp:
                def __init__(self, payload: bytes) -> None:
                    self._p = payload
                def read(self) -> bytes:
                    return self._p
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return None
            if "api.deepai.org" in req.full_url:
                return Resp(json.dumps({"output_url": "https://cdn.example.com/out.png"}).encode("utf-8"))
            return Resp(fake_png)

        with mock.patch("urllib.request.urlopen", side_effect=fake_deepai_open):
            self.assertEqual(_try_deepai("charcoal sketch", "dp-key"), fake_png)

        class FakeGeminiImgResp:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [{"inlineData": {"mimeType": "image/png", "data": b64_png}}]
                                }
                            }
                        ]
                    }
                ).encode("utf-8")
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None

        with mock.patch("urllib.request.urlopen", return_value=FakeGeminiImgResp()):
            self.assertEqual(_try_gemini_imagen("charcoal sketch", "gem-key"), fake_png)

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

    def test_music_selector_video_cmds_and_video_publish(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mood_dir = tmp_path / "late-night"
            mood_dir.mkdir(parents=True)
            mp3 = mood_dir / "midnight-grind.mp3"
            mp3.write_bytes(b"ID3" + b"0" * 100)

            track = select_background_track("monochrome_alpha", seed=7, allow_download=False, cache_dir=tmp_path, custom_dir=tmp_path / "none")
            self.assertIsNotNone(track)
            self.assertEqual(track["category"], "late-night")

            custom_dir = tmp_path / "custom" / "trending"
            custom_dir.mkdir(parents=True)
            m4a = custom_dir / "fb_trending_1.m4a"
            m4a.write_bytes(b"\x00\x00\x00 ftyp" + b"0" * 80)
            custom_track = select_background_track("pastel_viral", seed=5, allow_download=False, cache_dir=tmp_path, custom_dir=custom_dir.parent)
            self.assertIsNotNone(custom_track)
            self.assertEqual(custom_track["source"], "custom")
            self.assertEqual(custom_track["path"], m4a)

            img1 = tmp_path / "c1.jpg"
            img2 = tmp_path / "c2.jpg"
            out_mp4 = tmp_path / "out.mp4"
            img1.write_bytes(b"\xff\xd8\xff" + b"0" * 50)
            img2.write_bytes(b"\xff\xd8\xff" + b"0" * 50)

            cmd1 = _build_single_card_cmd(img1, m4a, out_mp4)
            joined1 = " ".join(cmd1)
            self.assertNotIn("zoompan", joined1)
            self.assertIn("scale=1080:1920", joined1)
            self.assertIn("stillimage", joined1)
            self.assertIn("aloop=loop=-1", joined1)
            self.assertIn(str(m4a), cmd1)

            cmd2 = _build_slideshow_cmd([img1, img2], m4a, out_mp4)
            joined2 = " ".join(cmd2)
            self.assertIn("concat=n=2:v=1:a=0", joined2)
            self.assertIn("aloop=loop=-1", joined2)

            class FakeResp:
                def __init__(self, body_str: str) -> None:
                    self._data = body_str.encode("utf-8")
                def read(self) -> bytes:
                    return self._data
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return None

            def fake_open(req, timeout=45):
                payload = json.loads(req.data.decode("utf-8"))
                tname = payload["params"]["name"]
                if tname == "COMPOSIO_MANAGE_CONNECTIONS":
                    inner = {"successful": True, "data": {"results": {"facebook": {"accounts": [{"id": "fb_1", "status": "active", "is_default": True}]}}}}
                elif tname == "COMPOSIO_GET_TOOL_SCHEMAS":
                    inner = {"successful": True, "data": {"tool_schemas": {"FACEBOOK_CREATE_VIDEO_POST": {"input_schema": {"properties": {"page_id": {}, "description": {}, "file_url": {}, "title": {}, "published": {}}}}}}}
                else:
                    inner = {"successful": True, "data": {"results": [{"response": {"data": {"id": "vid_999"}}}]}}
                sse = f'data: {json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": json.dumps(inner)}]}})}\n\n'
                return FakeResp(sse)

            config = _test_config(composio_api_key="ck_sample_consumer_key")
            plan = PostPlan(slot=1, archetype_id=1, archetype_name="Apex Patience", post_type="single", caption="Test video", slides=[SlideContent("TEST", "TEST")], content_hash="vid1")
            with mock.patch("urllib.request.urlopen", side_effect=fake_open):
                res = publish_post(
                    config=config,
                    plan=plan,
                    image_paths=[img1],
                    target_page_id="1443084575557354",
                    video_public_url="https://example.com/post.mp4",
                )
            self.assertEqual(res["action"], "FACEBOOK_CREATE_VIDEO_POST")
            self.assertEqual(res["result"]["id"], "vid_999")

    def test_resolve_target_pages_filtering_and_page_branding(self) -> None:
        from unittest import mock

        discovered = [
            {"id": "1443084575557354", "name": "Mallick Yt", "composio_account": "fb_u1"},
            {"id": "1423121790882352", "name": "Anime kid Story ", "composio_account": "fb_u1"},
            {"id": "237094056146383", "name": "online course", "composio_account": "fb_u1"},
        ]
        with mock.patch("src.composio_publisher.list_managed_pages", return_value=discovered):
            by_id = resolve_target_pages(_test_config(facebook_page_id="1423121790882352,237094056146383"))
            self.assertEqual([p["id"] for p in by_id], ["1423121790882352", "237094056146383"])
            self.assertEqual([p["name"] for p in by_id], ["Anime kid Story", "online course"])
            self.assertTrue(all(p["account"] == "fb_u1" for p in by_id))

            by_name = resolve_target_pages(_test_config(facebook_page_id="anime kid,online course"))
            self.assertEqual([p["id"] for p in by_name], ["1423121790882352", "237094056146383"])

            all_three = resolve_target_pages(_test_config(facebook_page_id="all"))
            self.assertEqual([p["id"] for p in all_three], ["1443084575557354", "1423121790882352", "237094056146383"])

        self.assertIn("mask", _infer_metaphor_prompt("NEVER TRUST FAKE FRIENDS BEHIND KIND WORDS").lower())
        self.assertIn("dome", _infer_metaphor_prompt("PROTECT YOUR PEACE AND IGNORE TOXIC NOISE").lower())

        slide = SlideContent("NEVER LOOK BACK.", "LOOK BACK.", "", "dark_lion")
        html_anime = build_card_html(_test_config(), slide, "data:image/png;base64,AA", page_brand="Anime kid Story")
        self.assertIn(">AKS<", html_anime)
        self.assertIn(">@animekidstory<", html_anime)

    def test_publish_manifest_jobs_paces_pages_with_delay(self) -> None:
        from unittest import mock

        base_job = {
            "slot": 1,
            "archetype_id": 1,
            "archetype_name": "Apex Patience",
            "post_type": "single",
            "caption": "Test pacing",
            "content_hash": "hash123",
            "source": "vault",
            "slides": [{"quote": "STAY PATIENT.", "accent": "PATIENT."}],
            "image_paths": [],
        }
        manifest_3 = {
            "jobs": [
                {**base_job, "page_id": "1443084575557354", "page_name": "Mallick Yt"},
                {**base_job, "page_id": "1423121790882352", "page_name": "Anime kid Story"},
                {**base_job, "page_id": "237094056146383", "page_name": "online course"},
            ]
        }
        with (
            mock.patch("src.main.publish_post", return_value={"action": "FACEBOOK_CREATE_VIDEO_POST", "id": "p1"}) as pub_mock,
            mock.patch("src.main.save_history") as hist_mock,
            mock.patch("src.main.time.sleep") as sleep_mock,
        ):
            res = _publish_manifest_jobs(_test_config(), manifest_3)
            self.assertEqual([r["status"] for r in res], ["ok", "ok", "ok"])
            self.assertEqual(pub_mock.call_count, 3)
            self.assertEqual(hist_mock.call_count, 3)
            self.assertEqual(sleep_mock.call_args_list, [mock.call(30.0), mock.call(30.0)])

            sleep_mock.reset_mock()
            _publish_manifest_jobs(_test_config(), {"jobs": [manifest_3["jobs"][0]]})
            sleep_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
