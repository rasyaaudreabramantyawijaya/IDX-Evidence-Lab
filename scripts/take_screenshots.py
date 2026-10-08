import os
import shutil
import subprocess
import time
import socket
from playwright.sync_api import sync_playwright

def wait_for_port(port, timeout=15):
    start_time = time.time()
    while True:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                return True
        except OSError:
            if time.time() - start_time > timeout:
                return False
            time.sleep(0.2)

def main():
    print("Membersihkan folder screenshot lama...")
    for folder in ["screenshots"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"Folder '{folder}' berhasil dihapus.")
        os.makedirs(folder, exist_ok=True)

    print("Memulai local server...")
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    server_process = subprocess.Popen(
        [".venv\\Scripts\\python", "-m", "idx_evidence_lab.web_app"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    if not wait_for_port(5500):
        print("Gagal memulai server lokal pada port 5500")
        server_process.kill()
        return

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            
            print("Navigating to local server...")
            page.goto("http://127.0.0.1:5500")
            page.wait_for_selector(".nav-item")
            page.wait_for_timeout(2500)
            
            main_pages = [
                ("dashboard", ".ihsg-headline"),
                ("screener", ".screener-table"),
                ("watchlist", "#idxel-main"),
                ("studies", "#study-canvas"),
                ("research", ".research-chat-shell"),
                ("portfolio-lab", "#factor-zoo-canvas"),
                ("market", ".market-overview-grid"),
                ("news-universe", ".news-layout"),
                ("sources", ".source-report"),
                ("settings", "#idxel-main"),
            ]
            
            for page_id, wait_sel in main_pages:
                print(f"Taking screenshot of {page_id}...")
                btn = page.locator(f'.nav-item[data-page="{page_id}"]')
                if btn.count() > 0:
                    btn.first.click()
                    if wait_sel:
                        try:
                            page.wait_for_selector(wait_sel, timeout=5000)
                        except Exception:
                            pass
                    page.wait_for_timeout(1500)
                    page.screenshot(path=f"screenshots/{page_id}.png", full_page=True)

            print("Capturing issuer dossier...")
            page.locator('.nav-item[data-page="screener"]').click()
            page.wait_for_selector("tr[data-action='open-issuer']", timeout=5000)
            page.wait_for_timeout(1000)
            
            row = page.locator("tr[data-action='open-issuer']").first
            if row.count() > 0:
                row.click()
                try:
                    page.wait_for_selector("text=Memuat hasil per emiten", state="detached", timeout=8000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)
                page.screenshot(path="screenshots/issuer.png", full_page=True)
                page.screenshot(path="screenshots/issuer-overview.png", full_page=True)

                tabs = [
                    ("Flow", "issuer-flow"),
                    ("Evidence", "issuer-evidence"),
                    ("Historical Analog", "issuer-historical-analog"),
                    ("Event Study", "issuer-event-study"),
                    ("Outcomes", "issuer-outcomes"),
                ]
                for tab_name, file_name in tabs:
                    tab_btn = page.locator(f'button.tab[data-tab="{tab_name}"]')
                    if tab_btn.count() > 0:
                        tab_btn.click()
                        page.wait_for_timeout(1000)
                        page.screenshot(path=f"screenshots/{file_name}.png", full_page=True)

            browser.close()
            print("Done capturing screenshots.")
    finally:
        print("Stopping server...")
        server_process.kill()

if __name__ == "__main__":
    main()
