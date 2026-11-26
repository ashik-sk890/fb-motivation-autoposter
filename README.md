# Multi-Page Modern Motivation Facebook Autoposter (Composio + GitHub Actions)

Fully automated **4 posts/day on EACH connected Facebook Page** using 6 trending visual card styles (`paper_sketch`, `sunrise_metaphor`, `saffron_editorial`, `cartoon_metaphor`, `gold_spotlight`, `monochrome_alpha`), built to keep running in the cloud **even if your phone is turned off for years**.

## Architecture (Zero Phone Dependency)
- **Cloud Scheduler (GitHub Actions):** Runs 4 times daily via `.github/workflows/daily_autopost.yml` (`10:00`, `14:00`, `18:00`, `21:30` UTC+05:30), publishing unique non-repeating posts across **all** your connected Facebook Pages.
- **Anti-60-Day-Disable & Zero-Bloat Design:**
  - `state/posted_history.json` is committed back after posts, resetting GitHub's 60-day schedule inactivity timer indefinitely while preventing duplicate quotes.
  - When the repository is **public**, rendered `.jpg` images are force-pushed to a single-commit orphan `media` branch so `main` stays lightweight forever (no multi-year image bloat). When **private**, Composio's file auto-upload handles image delivery.
- **Composio Facebook Integration:** Supports both **`ck_*` Connect Consumer Keys** (via `https://connect.composio.dev/mcp`) and **`ak_*` Project API Keys** (`composio` SDK), calling `FACEBOOK_LIST_MANAGED_PAGES`, `FACEBOOK_CREATE_PHOTO_POST`, and `FACEBOOK_CREATE_MULTI_PHOTO_POST`.
- **Top-50 Motivation Content & Art Engine:**
  - `data/top_50_archetypes.json` encodes 50 distinct dark-motivation, discipline, stoic, loyalty, lone-wolf, and numbered rule-series archetypes.
  - Note: Meta's Graph API blocks unapproved scraping of third-party Facebook Pages without `Page Public Content Access` App Review, so this engine pairs those 50 curated archetypes + optional Gemini/OpenAI live synthesis + a 1,400+ non-repeating combinatorial vault instead of fragile scraping.
  - `src/art_engine.py` + `src/card_renderer.py` render `1080x1350` dark chiaroscuro cards fading into `#000000` with centered crest/monogram, crimson/amber accent highlights, and crisp typography via Playwright Chromium (plus procedural dark SVG fallback if an image API is offline).

## Setup Guide (5 Minutes)

### 1. Connect your Facebook Page in Composio
1. Sign in at https://app.composio.dev
2. Go to **Toolkits / Apps → Facebook** and connect your **Facebook Page** (grant `pages_manage_posts` and `pages_read_engagement` permissions).
3. Copy your **Composio API Key** and note your **User / Entity ID** (usually `"default"` or the user ID shown in your Composio connected account).

### 2. Push this project to GitHub
Create a new GitHub repository (recommended: **Public** with zero secrets in files — keep all keys inside **GitHub Secrets** so `raw.githubusercontent.com` serves images reliably) and push this folder.

### 3. Add GitHub Repository Secrets
In your GitHub repo: **Settings → Secrets and variables → Actions → Secrets → New repository secret**:

| Secret Name | Required? | Description |
| --- | --- | --- |
| `COMPOSIO_API_KEY` | **Yes** | Your Composio API key (`ck_*` or `ak_*`) |
| `CLOUDFLARE_ACCOUNT_ID` | Recommended (Free) | Free-tier FLUX.1-schnell AI artwork (10,000 free Neurons/day, no card) |
| `CLOUDFLARE_API_TOKEN` | Recommended (Free) | Cloudflare Workers AI token with Read/Write AI permission |
| `COMPOSIO_USER_ID` | Optional | Composio user/entity ID (for `ak_*` keys; defaults to `default`) |
| `FACEBOOK_PAGE_ID` | Optional | Leave blank or `all` to post to **all** managed pages; or comma-separated IDs |
| `GEMINI_API_KEY` | Optional | Enables unlimited fresh AI-written quotes & Imagen artwork |
| `OPENAI_API_KEY` | Optional | Alternative AI quote/image generator |
| `HF_TOKEN` | Optional | Hugging Face token for FLUX.1-schnell dark AI artwork |
| `POLLINATIONS_API_KEY` | Optional | Pollinations API key for Flux image generation |

### 4. Customize Your Page Branding (Variables)
In **Settings → Secrets and variables → Actions → Variables**:
- `BRAND_NAME` (e.g. `Mindset & Attitude`)
- `BRAND_MONOGRAM` (2–3 letters inside the crest badge, e.g. `MA`)
- `BRAND_HANDLE` (footer handle, e.g. `@mindset__official`)

### 5. Test Immediately
Go to **Actions → Daily Facebook Page Autoposter (5x/Day) → Run workflow**:
- First test with **`dry_run = true`** and inspect the uploaded workflow artifact images.
- Then run with **`dry_run = false`** to verify the live post on your Facebook Page!

## Important Meta / Token Longevity Note
Even with Composio managing OAuth refreshes, Meta can invalidate Page tokens if you change your Facebook password, remove the app from Facebook Business Integrations, or trigger a Facebook account security checkpoint. Keep 2FA active and avoid revoking the Composio app connection.
