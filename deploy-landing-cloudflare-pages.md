# Deploying the landing page to Cloudflare Pages

This guide deploys `landing_page/index.html` to Cloudflare Pages with strict security headers, automatic HTTPS, and one-click rollback. The page is fully self-contained (HTML + inline CSS, no scripts, no external assets), so there is no build step — only a copy step that keeps internal design artifacts out of the public deploy.

## What ships

Only two files are uploaded to the public CDN:

| File | Source | Purpose |
| --- | --- | --- |
| `index.html` | `landing_page/index.html` | The landing page itself |
| `_headers` | `landing_page/_headers` | HTTP response headers Cloudflare applies to every request |

Everything else in `landing_page/` (`brand-spec.md`, `DESIGN-HANDOFF.md`, `DESIGN-MANIFEST.json`, screenshot PNGs) is design tooling and is excluded by the build command below.

## Prerequisites

- A Cloudflare account (free tier is enough — Pages includes unlimited bandwidth and free TLS).
- The repo pushed to GitHub at `https://github.com/SubashMohan/me`.
- (Optional) A custom domain managed by Cloudflare DNS, if you want to point e.g. `me.example.com` at the deploy.

---

## Path A — Git-connected deploy (recommended)

Cloudflare clones the repo on every push to `main` and redeploys automatically. Pull requests get preview URLs too.

### 1. Create the Pages project

1. Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**.
2. Authorize Cloudflare for GitHub, then pick `SubashMohan/me`.
3. On the build configuration screen, set:

   | Field | Value |
   | --- | --- |
   | Project name | `me-landing` (free to change — appears in the default `*.pages.dev` URL) |
   | Production branch | `main` |
   | Framework preset | **None** |
   | Build command | `mkdir -p _site && cp landing_page/index.html landing_page/_headers _site/` |
   | Build output directory | `_site` |
   | Root directory (advanced) | leave as `/` |
   | Environment variables | leave empty |

4. **Save and Deploy.** First build takes ~30 s. The deploy lands at `https://me-landing.pages.dev`.

### 2. Confirm headers and content

```sh
curl -sI https://me-landing.pages.dev/
```

You should see, in any order: `content-security-policy`, `x-content-type-options: nosniff`, `referrer-policy: strict-origin-when-cross-origin`, `permissions-policy`, `cross-origin-opener-policy`, `cross-origin-resource-policy`, `strict-transport-security`, plus `cache-control: public, max-age=300, must-revalidate` (the `_headers` rule scoped to `/index.html`).

Open the URL in a browser. The page should render with system fonts and zero console errors. Any CSP violation (e.g. if someone later adds a `<script>` tag) appears here as a `Refused to ...` console message.

### 3. (Optional) Attach a custom domain

1. Pages project → **Custom domains** → **Set up a custom domain**.
2. Enter the apex or subdomain (`me.example.com`). If the zone is on Cloudflare DNS, Pages adds the `CNAME` automatically; otherwise add it manually.
3. Wait for the **Active** status (usually under a minute) — Cloudflare provisions a Universal SSL cert in the background.
4. Re-run `curl -sI https://me.example.com/` to confirm headers carry over.

### 4. Future deploys

Just `git push origin main`. The new build appears under **Deployments**; the previous build stays one click away under **Rollback**.

---

## Path B — Wrangler CLI direct upload

For one-off pushes without going through Git (e.g. emergency copy fix from a laptop without a repo push):

```sh
mkdir -p _site && cp landing_page/index.html landing_page/_headers _site/
pnpm dlx wrangler@latest pages deploy _site --project-name=me-landing --branch=main
```

`pnpm dlx` (or `npx`) avoids installing Wrangler globally. The first run opens a browser for OAuth and writes credentials to `~/.config/.wrangler/`.

Pushing to `--branch=main` updates production; any other branch name creates a preview deploy with its own URL.

---

## Verification checklist

After the first deploy:

- [ ] `curl -sI https://<deploy-url>/` shows all seven security headers plus the `Cache-Control` override.
- [ ] Browser DevTools → Console on the deploy URL → **0** CSP violation entries.
- [ ] Embedding the URL in `<iframe src="...">` from a different origin is blocked (`Refused to display ... because an ancestor violates ... frame-ancestors 'none'`).
- [ ] The five GitHub CTAs in the page all resolve to `https://github.com/SubashMohan/me` and return 200.
- [ ] None of these paths are reachable: `/brand-spec.md`, `/DESIGN-HANDOFF.md`, `/DESIGN-MANIFEST.json`, `/mp8nfqs1-*.png`. They should 404.

---

## HSTS preload (follow-up)

The current `Strict-Transport-Security` header is `max-age=63072000; includeSubDomains` — strict but reversible. Once HTTPS is confirmed stable on the apex and every subdomain you control, add `; preload`:

```
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
```

Then submit the apex domain at <https://hstspreload.org/>. Preload is hard to undo (browsers cache the entry for months), so wait until the site is settled before opting in.

---

## Rollback

Cloudflare keeps every deploy. To revert:

1. Pages project → **Deployments**.
2. Find the previous good build.
3. **... → Rollback to this deployment.**

Rollback is instant and does not touch Git.

---

## Decisions log entry

Append to `DECISIONS.md` per project convention once the first deploy lands:

```
## 2026-05-17 — landing page hosting
**Choice:** Cloudflare Pages, Git-connected to main; build command copies only landing_page/index.html + _headers into _site/.
**Why:** Free, fast CDN; built-in TLS and preview deploys; the _headers file lets us ship a strict CSP and HSTS without a Worker.
**Alternatives considered:** GitHub Pages (no _headers equivalent — would need a Worker or per-path shim); Vercel/Netlify (equivalent but we already use Cloudflare DNS).
```
