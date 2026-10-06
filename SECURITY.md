# Security policy

IDX Evidence Lab is a private research prototype that runs on localhost. It is not hardened for public exposure yet.

## Reporting a vulnerability
Do not open a public issue. Message the repository owner (Rasya Audrea Bramantya Wijaya) directly with a description,
steps to reproduce and impact. Expect an acknowledgement within a few days.

## Handling secrets
- API keys (for example OpenRouter) live in `.env.local`, which is gitignored. Never commit keys, paste them into
  issues/PRs, or include them in logs or exports.
- If a key is committed or leaked, revoke it at the provider first, then remove it from the repository.
- CI runs gitleaks on every PR and weekly.

## Data and files
- Provider data under `data/raw/sectors/` is subject to the provider's redistribution terms. Keep the repository private.
- Private corpora (`Business & Corporate Law/`), screenshots and user files must not be committed. CI fails if
  forbidden file types are tracked.

## Known gaps (tracked for later phases)
- No authentication or rate limiting. Do not expose the server beyond localhost.
- No Content-Security-Policy or other security response headers yet.
- Attachment upload (`/api/research-attachments`) has a size limit but no content-type verification.
