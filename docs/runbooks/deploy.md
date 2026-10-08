# Deploying the image

The `release` workflow (`.github/workflows/release.yml`) builds the runtime image on every merge to `main`, smoke-tests
it, and pushes it to GitHub Container Registry. This is what any host (laptop, VPS, Fly.io, Render) pulls.

| Git event | Image tags |
|---|---|
| merge to `main` | `latest`, `sha-<commit>` |
| tag `v1.2.3` | also `1.2.3`, `1.2` |

Reference: `ghcr.io/<owner>/<repo>:<tag>`, all lowercase (this repo: `ghcr.io/rasyaaudreabramantyawijaya/hackathon_sectors`).

## What the image is not
- **It contains no market data.** `data/` (about 300 MB, provider-licensed) is mounted read-only at runtime. A container
  without the mount starts but has no snapshots. Keep the package **private** (GHCR default for a private repo).
- **No authentication and no TLS.** Anyone who can reach the port can use the API, including the research chat, which
  can spend OpenRouter credits. Publish the port on loopback only, or put it behind a proxy or host feature that
  requires login. Rate limits (`IDXEL_RL_*`) are per process and per client IP only.
- **No React build yet.** The container serves the legacy page. `frontend/dist` is not served (planned).

## First-time access
1. A person with repository access creates a Personal Access Token (classic) with `read:packages`.
2. `echo "$TOKEN" | docker login ghcr.io -u <github-username> --password-stdin`
3. Prepare a folder with a `data/` directory (copy from the repository checkout or the team's shared snapshot).

## Run
```bash
export IDXEL_IMAGE=ghcr.io/rasyaaudreabramantyawijaya/hackathon_sectors:latest
docker compose -f docker-compose.release.yml up -d
curl -s http://127.0.0.1:5500/api/health            # {"ok": true, ...}
docker compose -f docker-compose.release.yml ps       # STATUS: healthy after about 40 s
```
Optional: `OPENROUTER_API_KEY` in the shell enables Agent mode (never commit it; never bake it into an image).

## Release a version
```bash
git switch main && git pull
git tag v0.1.0 && git push origin v0.1.0     # triggers the workflow; check the Actions summary for the digest
```
`latest` always follows `main`. For anything people depend on, pin `vX.Y.Z` or `sha-<commit>`.

## Roll back
```bash
export IDXEL_IMAGE=ghcr.io/rasyaaudreabramantyawijaya/hackathon_sectors:sha-<previous-commit>
docker compose -f docker-compose.release.yml up -d      # pull_policy: always fetches that tag
```
Find the previous tag under the repository's Packages page. Images are immutable per `sha-` tag; `latest` moves.

## Environment
| Variable | Default | Notes |
|---|---|---|
| `IDXEL_HOST` | `0.0.0.0` in the image | Publish only on `127.0.0.1` unless something in front provides login |
| `IDXEL_PORT` | `5500` | |
| `IDXEL_RL_CHAT_PER_MIN` / `IDXEL_RL_POST_PER_MIN` | `20` / `120` | `0` disables |
| `OPENROUTER_API_KEY` | unset | Enables model features |

## If the workflow fails
- *Smoke test step:* the container logs print in the next step; usually a missing file in the image or a changed route.
- *Push step, 403:* repository Settings > Actions > General > Workflow permissions must allow the job's `packages: write`
  (the workflow requests it itself; an organization policy can still block it).
- Rebuild locally first: `docker compose up --build`.

## Known gaps
- Dependencies come from `requirements-portfolio.txt` ranges, so two builds on different days can differ. Pinning to
  `uv.lock` is a follow-up.
- Image is `linux/amd64` only. Add `linux/arm64` if a host needs it (slower build under emulation).
- Trivy is report-only.
- No automatic deploy: pulling the new image is manual until a host is chosen.
