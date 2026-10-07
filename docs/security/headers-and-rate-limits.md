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
| `Content-Security-Policy` (enforced) | `frame-ancestors 'none'; object-src 'none'; base-uri 'self'` | Only rules the current page already satisfies |
| `Content-Security-Policy-Report-Only` | `default-src 'self'; script-src 'self'; style-src 'self'; ...` | The strict target policy. Violations show in the browser console but nothing is blocked |

**Why CSP is report-only:** the page still has an inline `<script>` and `<style>` in
`docs/prototypes/idx-evidence-lab-user-journey.html`. An enforced strict policy would break it. After the frontend split
(Phase 4) there is no inline code; move the report-only value into `Content-Security-Policy` then.

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
