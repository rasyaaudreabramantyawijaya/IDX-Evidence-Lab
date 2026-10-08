"""Golden-master harness: records the HTTP behavior of the API and later compares against it.

Why: the Phase 3 refactor (module split / FastAPI) must not change what clients receive. This module talks to
a running server over HTTP only, so it works unchanged for the current stdlib server and for a future one.

    python tests/golden_master.py capture              # (re)write tests/golden/*.json from a fresh local server
    python tests/golden_master.py check                # compare a fresh local server with the stored snapshots
    python tests/golden_master.py check --base-url http://127.0.0.1:8000   # compare an already running server

Rules baked in:
- No call may reach OpenRouter: `use_model` is never true and the server starts without a key.
- Random ids (uuid4) and wall-clock stamps are normalized; everything else must match exactly,
  except floats, which may differ slightly (relative tolerance GOLDEN_REL_TOL, default 1e-6).
- JSON key order is not compared; status codes and an allowlist of response headers are.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

# Headers that are part of the API contract. Date/Server/Content-Length are intentionally excluded.
CONTRACT_HEADERS = (
    "content-type", "cache-control", "vary", "retry-after",
    "access-control-allow-origin", "access-control-allow-methods", "access-control-allow-headers",
    "access-control-max-age",
    "x-content-type-options", "x-frame-options", "referrer-policy", "permissions-policy",
    "cross-origin-opener-policy", "content-security-policy", "content-security-policy-report-only",
)
# Floats may differ in the last digits across numpy/scipy releases (optimizer output varies by ~1e-9).
# 1e-6 is far below any real regression. For a same-machine before/after refactor check, tighten it:
#   GOLDEN_REL_TOL=1e-12 GOLDEN_ABS_TOL=1e-12 python tests/golden_master.py check
REL_TOL = float(os.environ.get("GOLDEN_REL_TOL", "1e-6"))
ABS_TOL = float(os.environ.get("GOLDEN_ABS_TOL", "1e-8"))  # only matters for values near zero (e.g. daily returns ~1e-4)
# Wall-clock fields that legitimately change on every run.
VOLATILE_KEYS = {"computed_at_utc"}
# The server rewrites this tracked artifact at runtime when numpy/scipy produce slightly different floats,
# so its hash (and fingerprints derived from it) depend on the installed library versions, not on the code.
ENV_DEPENDENT_SOURCES = {"docs/prototypes/portfolio-factor-zoo-data.json"}
# Hashes of numerically computed content: the numbers inside are still compared (with tolerance),
# but the hash itself changes whenever a library release alters the last digits.
ENV_DEPENDENT_HASH_KEYS = {"artifact_fingerprint"}
# Values that depend on the machine (local key file, locally indexed extra files), not on the code.
MACHINE_KEYS = {"openrouter_configured", "local_documents", "local_root"}

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
HEX32_RE = re.compile(r"^[0-9a-f]{32}$")
ORIGIN = "http://127.0.0.1:5500"
JSON_CT = {"Content-Type": "application/json"}


# ---------------------------------------------------------------- HTTP client

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def call(base: str, method: str, path: str, body=None, headers=None, raw: bytes | None = None):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode("utf-8"))
    request = urllib.request.Request(base + path, data=data, method=method, headers=dict(headers or {}))
    try:
        with _opener.open(request, timeout=180) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


# ---------------------------------------------------------------- normalization

def normalize(value, placeholders: dict[str, str], key: str = ""):
    """Replace run-specific values so two captures of the same code are identical."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in VOLATILE_KEYS:
                out[k] = "<volatile>"
            elif k in MACHINE_KEYS:
                out[k] = "<machine>"
            elif k in ENV_DEPENDENT_HASH_KEYS:
                out[k] = "<env-dependent>"
            else:
                out[k] = normalize(v, placeholders, k)
        return out
    if isinstance(value, list):
        return [normalize(v, placeholders, key) for v in value]
    if isinstance(value, str):
        if value in placeholders:
            return placeholders[value]
        if UUID_RE.match(value):
            return "<uuid>"
        if HEX32_RE.match(value) and key.endswith(("_ref", "_id")):
            return "<hex32>"
    return value


def _mask_env_dependent_sources(body) -> None:
    sources = body.get("sources") if isinstance(body, dict) else None
    if not isinstance(sources, list):
        return
    touched = False
    for entry in sources:
        if isinstance(entry, dict) and entry.get("id") in ENV_DEPENDENT_SOURCES and "sha256" in entry:
            entry["sha256"] = "<env-dependent>"
            touched = True
    if touched and "request_fingerprint" in body:
        body["request_fingerprint"] = "<env-dependent>"


def fill(template, ctx: dict[str, str]):
    """Substitute {name} placeholders in request templates with live values."""
    if isinstance(template, str):
        return template.format_map(ctx) if "{" in template else template
    if isinstance(template, dict):
        return {k: fill(v, ctx) for k, v in template.items()}
    if isinstance(template, list):
        return [fill(v, ctx) for v in template]
    return template


# ---------------------------------------------------------------- scenario

class Recorder:
    def __init__(self, base: str):
        self.base = base
        self.cases: dict[str, dict] = {}
        self.ctx: dict[str, str] = {}          # live dynamic values: {"session_id": "..."}
        self.placeholders: dict[str, str] = {}  # live value -> stable placeholder

    def remember(self, name: str, live_value: str):
        self.ctx[name] = live_value
        self.placeholders[live_value] = "<" + name + ">"

    def run(self, name: str, method: str, path: str, body=None, headers=None, raw: bytes | None = None,
            raw_label: str | None = None, random_derived: tuple[str, ...] = ()):
        assert name not in self.cases, f"duplicate case {name}"
        live_body = fill(body, self.ctx) if body is not None else None
        live_path = fill(path, self.ctx)
        status, resp_headers, payload = call(self.base, method, live_path, live_body, headers, raw)
        kept = {h: resp_headers[h] for h in CONTRACT_HEADERS if resp_headers.get(h) is not None}
        record = {
            "request": {"method": method, "path": path, "headers": dict(headers or {}),
                        "body": body if raw is None else raw_label or f"<{len(raw)} raw bytes>"},
            "status": status,
            "headers": kept,
        }
        content_type = (kept.get("content-type") or "").split(";")[0]
        # Static files are already versioned in git: an exact byte hash is enough and keeps snapshots small.
        if content_type == "application/json" and not live_path.startswith("/docs/prototypes/"):
            parsed = json.loads(payload)
            record["body"] = normalize(parsed, self.placeholders)
            _mask_env_dependent_sources(record["body"])
            for key in random_derived:  # hashes whose input contains a random id (e.g. a uuid4 artifact ref)
                if isinstance(record["body"], dict) and key in record["body"]:
                    record["body"][key] = "<random-derived>"
        elif status >= 400 and content_type == "text/html":
            record["body_note"] = "stdlib error page; text differs between Python versions, not compared"
        else:
            record["body_sha256"] = hashlib.sha256(payload).hexdigest()
            record["body_bytes"] = len(payload)
        self.cases[name] = record
        return status, (json.loads(payload) if content_type == "application/json" else payload)


def scenario(base: str) -> dict[str, dict]:
    r = Recorder(base)

    # --- static assets and page shell
    for name, path in (("page_root", "/"), ("page_index", "/index.html"),
                       ("asset_user_journey_html", "/docs/prototypes/idx-evidence-lab-user-journey.html"),
                       ("asset_studies_ui_js", "/docs/prototypes/studies-ui.js"),
                       ("asset_app_js", "/docs/prototypes/app.js"),
                       ("asset_app_css", "/docs/prototypes/app.css"),
                       ("asset_market_overview_json", "/docs/prototypes/market-overview-data.json"),
                       ("asset_news_universe_json", "/docs/prototypes/news-universe.json"),
                       ("asset_evt_surface_json", "/docs/prototypes/ihsg-evt-tail-surface-data.json"),
                       ("asset_evt_surface_fig", "/docs/prototypes/ihsg-evt-tail-surface.fig"),
                       ("not_found_route", "/definitely-missing"),
                       ("not_found_asset", "/docs/prototypes/not-listed.json")):
        r.run(name, "GET", path)

    # --- read-only API
    for name, path in (("health", "/api/health"), ("studies_catalog", "/api/studies-catalog"),
                       ("portfolio_data", "/api/portfolio-data"), ("factor_zoo_view", "/api/portfolio-factor-zoo-view"),
                       ("factor_zoo_data", "/api/portfolio-factor-zoo-data"), ("dashboard_data", "/api/dashboard-data"),
                       ("screener_analysis", "/api/screener-analysis"), ("sector_heatmap", "/api/sector-heatmap"),
                       ("news_universe", "/api/news-universe"), ("research_targets", "/api/research-targets"),
                       ("source_report", "/api/source-report"),
                       ("issuer_daily_bbca", "/api/issuer-daily?ticker=BBCA"),
                       ("issuer_daily_tlkm", "/api/issuer-daily?ticker=TLKM"),
                       ("issuer_daily_lowercase", "/api/issuer-daily?ticker=bbca"),
                       ("issuer_daily_unknown", "/api/issuer-daily?ticker=ZZZZ"),
                       ("issuer_daily_missing_param", "/api/issuer-daily")):
        r.run(name, "GET", path)
    r.run("cors_get_allowed_origin", "GET", "/api/portfolio-data", headers={"Origin": ORIGIN})
    r.run("cors_get_foreign_origin", "GET", "/api/portfolio-data", headers={"Origin": "http://evil.example"})
    r.run("method_not_supported_put", "PUT", "/api/health", body={})
    r.run("method_not_supported_head", "HEAD", "/api/health")

    # --- CORS preflight
    pre = {"Origin": ORIGIN, "Access-Control-Request-Method": "POST"}
    r.run("preflight_studies_allowed", "OPTIONS", "/api/studies-run", headers=pre)
    r.run("preflight_portfolio_allowed", "OPTIONS", "/api/portfolio-analysis", headers=pre)
    r.run("preflight_foreign_origin", "OPTIONS", "/api/studies-run",
          headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    r.run("preflight_unlisted_route", "OPTIONS", "/api/search", headers=pre)

    # --- search and issuer research (local only: use_model never true)
    for name, body in (("search_ok", {"query": "BBCA laba bersih"}), ("search_sector", {"query": "perbankan kredit"}),
                       ("search_empty", {"query": ""}), ("search_too_long", {"query": "a" * 501}),
                       ("search_not_string", {"query": 5}), ("search_not_object", [1, 2])):
        r.run(name, "POST", "/api/search", body, JSON_CT)
    r.run("search_body_too_large", "POST", "/api/search", None, JSON_CT, raw=b"x" * 5000, raw_label="<5000 x bytes>")
    r.run("search_invalid_json", "POST", "/api/search", None, JSON_CT, raw=b"{not json", raw_label="<invalid json>")
    r.run("search_empty_body", "POST", "/api/search", None, JSON_CT, raw=b"", raw_label="<empty>")
    r.run("issuer_research_bbca", "POST", "/api/issuer-research", {"ticker": "BBCA", "query": "kinerja arus kas"}, JSON_CT)
    r.run("issuer_research_unknown_ticker", "POST", "/api/issuer-research", {"ticker": "ZZZZ", "query": "x"}, JSON_CT)
    r.run("unknown_post_route", "POST", "/api/nope", {}, JSON_CT)

    # --- portfolio analysis
    base_p = {"benchmark": "IHSG", "profile": "moderate", "lookback": 126, "risk_free_annual": 0.07129,
              "scenarios": {"horizons": [20], "simulations": 12, "seed": 7}}
    for name, extra in (("portfolio_markowitz", {"tickers": ["BBCA", "BMRI", "TLKM"], "method": "markowitz"}),
                        ("portfolio_hrp", {"tickers": ["BBCA", "BMRI", "TLKM"], "method": "hrp"}),
                        ("portfolio_max_diversification", {"tickers": ["BBCA", "BMRI", "TLKM"], "method": "maximum_diversification"}),
                        ("portfolio_integrated_lq45", {"tickers": ["BBCA", "ASII"], "method": "integrated",
                                                      "benchmark": "LQ45", "profile": "aggressive"}),
                        ("portfolio_with_capital", {"tickers": ["BBCA", "BMRI"], "method": "hrp", "total_capital": 100000000})):
        status, payload = r.run(name, "POST", "/api/portfolio-analysis", {**base_p, **extra}, JSON_CT)
        if name == "portfolio_markowitz" and status == 200 and payload.get("studies_artifact_ref"):
            r.remember("artifact_ref", payload["studies_artifact_ref"])
    for name, body in (("portfolio_bad_profile", {**base_p, "tickers": ["BBCA"], "method": "hrp", "profile": "x"}),
                       ("portfolio_unknown_field", {**base_p, "tickers": ["BBCA"], "method": "hrp", "zzz": 1}),
                       ("portfolio_duplicate_tickers", {**base_p, "tickers": ["BBCA", "bbca"], "method": "hrp"}),
                       ("portfolio_no_tickers", {**base_p, "tickers": [], "method": "hrp"}),
                       ("portfolio_unknown_ticker", {**base_p, "tickers": ["ZZZZ"], "method": "hrp"}),
                       ("portfolio_not_object", [1])):
        r.run(name, "POST", "/api/portfolio-analysis", body, JSON_CT)
    r.run("portfolio_body_too_large", "POST", "/api/portfolio-analysis", None, JSON_CT, raw=b"x" * 16385,
          raw_label="<16385 x bytes>")

    # --- studies: every widget in the live catalog, plus linked and negative cases
    status, catalog = r.run("studies_catalog_again", "GET", "/api/studies-catalog")
    widgets = [w["id"] if isinstance(w, dict) and "id" in w else (w.get("widget_id") if isinstance(w, dict) else w)
               for w in (catalog.get("widgets", []) if status == 200 else [])]
    for widget in widgets:
        r.run(f"studies_run__{widget}", "POST", "/api/studies-run",
              {"widget_id": widget, "targets": ["BBCA"], "window": "available"}, JSON_CT)
    r.run("studies_custom_engineering", "POST", "/api/studies-run",
          {"widget_id": "custom_engineering", "targets": ["BBCA"], "window": "20",
           "params": {"field": "close", "transform": "rolling_mean"}}, JSON_CT)
    if "artifact_ref" in r.ctx:
        for widget in ("portfolio_risk", "capm_benchmark"):
            r.run(f"studies_linked_portfolio__{widget}", "POST", "/api/studies-run",
                  {"widget_id": widget, "targets": ["BBCA", "BMRI", "TLKM"], "window": "available",
                   "portfolio_artifact_ref": "{artifact_ref}"}, JSON_CT, random_derived=("request_fingerprint",))
    r.run("studies_unknown_widget", "POST", "/api/studies-run", {"widget_id": "code"}, JSON_CT)
    r.run("studies_unknown_ref", "POST", "/api/studies-run",
          {"widget_id": "portfolio_risk", "targets": ["BBCA"], "window": "available",
           "portfolio_artifact_ref": "0" * 32}, JSON_CT)
    r.run("studies_body_too_large", "POST", "/api/studies-run", None, JSON_CT, raw=b"x" * 16385,
          raw_label="<16385 x bytes>")

    # --- research sessions (local answers only)
    status, session = r.run("research_session_create", "POST", "/api/research-sessions", {}, JSON_CT)
    if status == 201:
        r.remember("session_id", session["session_id"])
        chat = {"session_id": "{session_id}", "expected_revision": 0, "query": "ringkas BBCA", "use_model": False,
                "artifact_refs": []}
        r.run("research_chat_local", "POST", "/api/research-chat", chat, JSON_CT)
        r.run("research_chat_stale_revision", "POST", "/api/research-chat", chat, JSON_CT)
        r.run("research_chat_empty_query", "POST", "/api/research-chat", {**chat, "expected_revision": 1, "query": ""}, JSON_CT)
        r.run("research_chat_query_too_long", "POST", "/api/research-chat",
              {**chat, "expected_revision": 1, "query": "x" * 4001}, JSON_CT)
        text = base64.b64encode("Catatan pengguna: BBCA\n".encode()).decode()
        r.run("research_attachment_text", "POST", "/api/research-attachments",
              {"session_id": "{session_id}", "file": {"name": "catatan.txt", "mime": "text/plain", "data": text}}, JSON_CT)
        r.run("research_attachment_video_refused", "POST", "/api/research-attachments",
              {"session_id": "{session_id}", "file": {"name": "a.mp4", "mime": "video/mp4", "data": text}}, JSON_CT)
        r.run("research_attachment_control_char_name", "POST", "/api/research-attachments",
              {"session_id": "{session_id}", "file": {"name": "bad\u0000.txt", "mime": "text/plain", "data": text}}, JSON_CT)
        r.run("research_attachment_invalid_base64", "POST", "/api/research-attachments",
              {"session_id": "{session_id}", "file": {"name": "x.txt", "mime": "text/plain", "data": "***"}}, JSON_CT)
        r.run("research_cancel", "POST", "/api/research-cancel",
              {"session_id": "{session_id}", "expected_revision": 1}, JSON_CT)
    r.run("research_chat_unknown_session", "POST", "/api/research-chat",
          {"session_id": "expired", "expected_revision": 0, "query": "BBCA", "use_model": False, "artifact_refs": []}, JSON_CT)
    r.run("research_chat_not_object", "POST", "/api/research-chat", [1, 2], JSON_CT)
    r.run("research_chat_body_too_large", "POST", "/api/research-chat", None, JSON_CT, raw=b"x" * (64 * 1024 + 1),
          raw_label="<65537 x bytes>")
    return r.cases


# ---------------------------------------------------------------- compare

def _close(a, b, path: str, out: list[str]):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}/{k}: unexpected new field")
            elif k not in b:
                out.append(f"{path}/{k}: field missing")
            else:
                _close(a[k], b[k], f"{path}/{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} -> {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            _close(x, y, f"{path}[{i}]", out)
    elif isinstance(a, float) and isinstance(b, float):
        if not math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL):
            out.append(f"{path}: {a!r} -> {b!r}")
    elif a != b or type(a) is not type(b):
        out.append(f"{path}: {a!r} -> {b!r}")


def compare(stored: dict[str, dict], live: dict[str, dict]) -> list[str]:
    problems: list[str] = []
    for name in sorted(set(stored) | set(live)):
        if name not in live:
            problems.append(f"[{name}] case no longer produced")
            continue
        if name not in stored:
            problems.append(f"[{name}] new case without a stored snapshot (run capture and review)")
            continue
        found: list[str] = []
        _close({k: v for k, v in stored[name].items() if k != "request"},
               {k: v for k, v in live[name].items() if k != "request"}, "", found)
        problems.extend(f"[{name}] {line}" for line in found[:12])
        if len(found) > 12:
            problems.append(f"[{name}] ... {len(found) - 12} more differences")
    return problems


# ---------------------------------------------------------------- storage

LARGE_SNAPSHOT_BYTES = 50_000  # bigger records are stored gzipped (.json.gz) to keep the repo small


def write_snapshots(cases: dict[str, dict]) -> None:
    GOLDEN_DIR.mkdir(exist_ok=True)
    for stale in [*GOLDEN_DIR.glob("*.json"), *GOLDEN_DIR.glob("*.json.gz")]:
        stale.unlink()
    for name, record in cases.items():
        text = json.dumps(record, indent=1, ensure_ascii=False) + "\n"
        if len(text) > LARGE_SNAPSHOT_BYTES:
            # mtime=0 and a fixed name keep the bytes identical between captures of identical data.
            (GOLDEN_DIR / f"{name}.json.gz").write_bytes(gzip.compress(text.encode("utf-8"), mtime=0))
        else:
            (GOLDEN_DIR / f"{name}.json").write_text(text, encoding="utf-8")


def read_snapshots() -> dict[str, dict]:
    out = {p.name[: -len(".json")]: json.loads(p.read_text(encoding="utf-8")) for p in sorted(GOLDEN_DIR.glob("*.json"))}
    for p in sorted(GOLDEN_DIR.glob("*.json.gz")):
        out[p.name[: -len(".json.gz")]] = json.loads(gzip.decompress(p.read_bytes()).decode("utf-8"))
    return out


# ---------------------------------------------------------------- local server

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _link_or_copy(src, dst):
    """Hardlink read-only snapshot files (fast, no extra disk); fall back to a copy across volumes."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


RUNTIME_DIRS = ("src", "configs", "reports")  # same layout the Docker image ships; data/ is linked in


@contextmanager
def local_server(source: Path = ROOT):
    """Start the real entry point (`python -m idx_evidence_lab.web_app`) from a throwaway copy of `source`.

    A copy is used because some GET endpoints rewrite tracked files (e.g. the factor-zoo artifact), and a
    comparison tool must never dirty the working tree. The copy also makes results independent of untracked
    local files. No API key is passed and rate limits are off.
    """
    with tempfile.TemporaryDirectory(prefix="golden-") as tmp:
        cwd = Path(tmp)
        for name in RUNTIME_DIRS:
            shutil.copytree(source / name, cwd / name, ignore=shutil.ignore_patterns("__pycache__"))
        (cwd / "docs").mkdir()
        shutil.copytree(source / "docs" / "prototypes", cwd / "docs" / "prototypes")
        shutil.copytree(source / "data", cwd / "data", copy_function=_link_or_copy)
        yield from _run_server(cwd)


def _run_server(cwd: Path):
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OPENROUTER", "IDXEL"))}
    env.update(PYTHONPATH=str(cwd / "src"), IDXEL_PORT=str(port), IDXEL_RL_CHAT_PER_MIN="0",
               IDXEL_RL_POST_PER_MIN="0", PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.Popen([sys.executable, "-m", "idx_evidence_lab.web_app"], cwd=cwd, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(240):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=2).close()
                break
            except Exception:
                if proc.poll() is not None:
                    raise RuntimeError("server exited during startup")
                time.sleep(0.25)
        else:
            raise RuntimeError("server did not become healthy")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def main(argv: list[str]) -> int:
    if argv and argv[0] == "serve":
        # Isolated server for browser tests: prints the base URL, runs until interrupted.
        with local_server() as base:
            print(base, flush=True)
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                return 0
    if not argv or argv[0] not in {"capture", "check"}:
        print(__doc__)
        return 2
    base_url = argv[argv.index("--base-url") + 1] if "--base-url" in argv else None

    def collect():
        if base_url:
            return scenario(base_url)
        with local_server() as base:
            return scenario(base)

    cases = collect()
    if argv[0] == "capture":
        write_snapshots(cases)
        by_status: dict[int, int] = {}
        for rec in cases.values():
            by_status[rec["status"]] = by_status.get(rec["status"], 0) + 1
        print(f"wrote {len(cases)} snapshots to {GOLDEN_DIR.relative_to(ROOT)}; status counts: {dict(sorted(by_status.items()))}")
        return 0
    problems = compare(read_snapshots(), cases)
    print("\n".join(problems) if problems else f"OK: {len(cases)} cases match")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
