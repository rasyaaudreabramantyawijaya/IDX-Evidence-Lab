"""Save an OpenRouter key locally without echoing it into the terminal or Git."""

from __future__ import annotations

import getpass
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".env.local"


def main() -> int:
    if CONFIG.exists():
        print("Konfigurasi .env.local sudah ada. Hapus atau ubah file itu secara lokal sebelum menjalankan setup lagi.")
        return 1
    key = getpass.getpass("Tempel OpenRouter API key (input tersembunyi): ").strip()
    if not key or "\n" in key or "\r" in key:
        print("Key kosong atau formatnya tidak valid.", file=sys.stderr)
        return 1
    if not re.fullmatch(r"[A-Za-z0-9._-]+", key):
        print("Format key tidak dikenali; nilai tidak disimpan.", file=sys.stderr)
        return 1
    model = input("Model OpenRouter [qwen/qwen3.8-27b:free]: ").strip()
    model = model or "qwen/qwen3.8-27b:free"
    if not re.fullmatch(r"[A-Za-z0-9._:/-]+", model):
        print("Format model tidak valid; nilai tidak disimpan.", file=sys.stderr)
        return 1
    content = f"OPENROUTER_API_KEY={key}\nOPENROUTER_MODEL={model}\n"
    descriptor = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(content)
    except Exception:
        CONFIG.unlink(missing_ok=True)
        raise
    print("Key tersimpan di .env.local dengan izin file privat. Muat ulang Riset emiten untuk memperbarui status sambungan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
