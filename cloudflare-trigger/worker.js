/**
 * Reliable exact-schedule Cloudflare Cron Worker that dispatches GitHub Actions
 * on-time for each daily slot (10:00 AM, 2:00 PM, 6:00 PM, 9:30 PM IST).
 *
 * Required Cloudflare Worker Secret:
 *   GH_WORKFLOW_TOKEN  -> GitHub Fine-Grained PAT with Actions: Read & Write on the repo.
 * Optional Worker Variables:
 *   GH_OWNER           -> default "ashik-sk890"
 *   GH_REPO            -> default "fb-motivation-autoposter"
 *   GH_WORKFLOW        -> default "daily_autopost.yml"
 *   GH_REF             -> default "main"
 *   TRIGGER_SECRET     -> optional bearer secret for manual HTTP POST tests
 */

const CRON_SLOT_MAP = {
  "30 4 * * *": "1",
  "30 8 * * *": "2",
  "30 12 * * *": "3",
  "0 16 * * *": "4",
};

function resolveSlotFromUtcHour(date) {
  const hour = date.getUTCHours();
  if (hour <= 6) return "1";
  if (hour <= 10) return "2";
  if (hour <= 14) return "3";
  return "4";
}

async function dispatchWorkflow(env, slot, dryRun = false) {
  const token = (env.GH_WORKFLOW_TOKEN || "").trim();
  if (!token) {
    throw new Error("Missing GH_WORKFLOW_TOKEN Worker secret.");
  }
  const owner = (env.GH_OWNER || "ashik-sk890").trim();
  const repo = (env.GH_REPO || "fb-motivation-autoposter").trim();
  const workflow = (env.GH_WORKFLOW || "daily_autopost.yml").trim();
  const ref = (env.GH_REF || "main").trim();

  const url = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`;
  const payload = JSON.stringify({
    ref,
    inputs: {
      slot: String(slot),
      dry_run: Boolean(dryRun),
      scheduled_check: !dryRun,
    },
  });

  let lastStatus = 0;
  let lastBody = "";
  for (let attempt = 0; attempt < 2; attempt++) {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "cloudflare-fb-autopost-trigger",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: payload,
    });
    lastStatus = resp.status;
    if (resp.status === 204 || resp.ok) {
      return { ok: true, status: resp.status, slot, dryRun };
    }
    lastBody = await resp.text();
    if (resp.status >= 500 && attempt === 0) {
      await new Promise((r) => setTimeout(r, 2000));
      continue;
    }
    break;
  }
  throw new Error(`GitHub workflow_dispatch failed (HTTP ${lastStatus}): ${lastBody}`);
}

export default {
  async scheduled(event, env, ctx) {
    const scheduledDate = new Date(event.scheduledTime || Date.now());
    const slot = CRON_SLOT_MAP[event.cron] || resolveSlotFromUtcHour(scheduledDate);
    ctx.waitUntil(dispatchWorkflow(env, slot, false));
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET") {
      return Response.json({
        ok: true,
        service: "fb-motivation-autopost-cron",
        repo: `${env.GH_OWNER || "ashik-sk890"}/${env.GH_REPO || "fb-motivation-autoposter"}`,
        crons: CRON_SLOT_MAP,
      });
    }

    if (request.method === "POST") {
      const secret = (env.TRIGGER_SECRET || "").trim();
      const auth = request.headers.get("Authorization") || "";
      if (!secret || auth !== `Bearer ${secret}`) {
        return Response.json({ ok: false, error: "Unauthorized" }, { status: 401 });
      }
      const slot = url.searchParams.get("slot") || resolveSlotFromUtcHour(new Date());
      const dryRun = url.searchParams.get("dry_run") !== "false";
      const result = await dispatchWorkflow(env, slot, dryRun);
      return Response.json(result);
    }

    return new Response("Method Not Allowed", { status: 405 });
  },
};
