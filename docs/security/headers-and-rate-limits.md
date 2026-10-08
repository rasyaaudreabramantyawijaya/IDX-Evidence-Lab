# Response headers, rate limits and runtime settings

Implemented in `src/idx_evidence_lab/security.py`, `config.py` and `web_app.py` (`SearchHandler`).

## Headers (every response, including errors)
| Header | Value | Purpose |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Stops browsers guessing a different content type |
| `X-Frame-Options` | `DENY` | Blocks clickjacking by framing |
| `Referrer-Policy` | `no-referrer` | No URL leakage to other origins |
| `Permissions-Policy` | camera, microphone, geolocation off | Denies unused browser features |
| `Cross-Origin-Opener-Policy` | `same-origin` | Isolates the browsing context |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'` | Enforced. Only same-origin script, style, image and fetch. No `unsafe-eval`, no inline `<script>` or `<style>` |

**Inline style attributes:** `style-src-attr 'unsafe-inline'` is deliberate. Charts set per-data-point widths, colors and
positions through `style="..."`, which cannot become static classes. This only allows style *attributes*; it does not
allow inline scripts or `<style>` elements, so it does not weaken script injection protection.

**Where the page code lives:** `docs/prototypes/app.js` and `app.css` are generated from the chunks in `frontend/legacy/`
(`python scripts/build_legacy_ui.py`; CI fails if the committed files are stale). The HTML has no inline script or style.

## Rate limiting
Per client IP, in memory, fixed 60-second window, per server process.

| Bucket | Routes | Default |
|---|---|---|
| `chat` | `POST /api/research-chat`, `POST /api/issuer-research` (can spend OpenRouter credits) | 20 / min |
| `post` | all other `POST` routes | 120 / min |

Exceeding a limit returns `429` with `{"error":"RATE_LIMITED"}` and a `Retry-After` header. Limits reset on restart and are
not shared between processes; put a real limiter in front of the app if it is ever deployed behind a proxy
(behind a proxy every request shares the proxy's IP).

## Other protections
- Handler socket timeout of 30 s drops stalled or slow clients.
- Attachment file names containing control characters are rejected (`INVALID_ATTACHMENT`).

## Environment variables
| Variable | Default | Notes |
|---|---|---|
| `IDXEL_HOST` | `127.0.0.1` | A non-loopback value prints a warning: there is no authentication yet |
| `IDXEL_PORT` | `5500` | 1-65535 |
| `IDXEL_RL_CHAT_PER_MIN` | `20` | `0` disables the bucket |
| `IDXEL_RL_POST_PER_MIN` | `120` | `0` disables the bucket |

Invalid values stop startup with a clear message.

## Running in Docker
```bash
docker compose up --build        # serves http://127.0.0.1:5500, data/ mounted read-only
```
The port is published on loopback only. Do not publish it on a public interface until authentication exists.
