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
    # 1. Hapus folder screenshots lama
    print("Membersihkan folder screenshot lama...")
    for folder in ["screenshots_full", "screenshots"]:
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

    css_injection = """
    * {
        scroll-behavior: auto !important;
        animation: none !important;
        transition: none !important;
    }
    body, html {
        height: auto !important;
        overflow: visible !important;
        position: static !important;
    }
    #idxel-journey, .shell {
        height: auto !important;
        min-height: 100vh !important;
        overflow: visible !important;
        position: static !important;
    }
    .main, .side {
        height: auto !important;
        max-height: none !important;
        overflow: visible !important;
        position: static !important;
    }
    .table-wrap, .screener-table-wrap {
        max-height: none !important;
        overflow: visible !important;
    }
    """

    def capture(page, name):
        try:
            page.add_style_tag(content=css_injection)
        except Exception:
            pass
        page.wait_for_timeout(500)
        full_path = f"screenshots_full/{name}.png"
        std_path = f"screenshots/{name}.png"
        page.screenshot(path=full_path, full_page=True)
        shutil.copyfile(full_path, std_path)
        print(f"  -> Tersimpan: {full_path} & {std_path}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # bypass_csp=True penting agar CSP tidak memblokir inline css injection
            context = browser.new_context(
                viewport={"width": 1280, "height": 1000},
                bypass_csp=True,
                locale="id-ID",
                timezone_id="Asia/Jakarta"
            )
            page = context.new_page()
            
            print("Membuka server lokal...")
            page.goto("http://127.0.0.1:5500")
            page.wait_for_selector(".nav-item")
            # Tunggu inisialisasi data dashboard awal
            page.wait_for_timeout(2500)
            
            # Daftar halaman utama yang terdaftar
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
            
            print("\n--- Mengambil screenshot halaman utama ---")
            for page_id, wait_sel in main_pages:
                print(f"Mengambil screenshot: {page_id}...")
                btn = page.locator(f'.nav-item[data-page="{page_id}"]')
                if btn.count() > 0:
                    btn.first.click()
                    if wait_sel:
                        try:
                            page.wait_for_selector(wait_sel, timeout=5000)
                        except Exception:
                            pass
                    # Tunggu data settle (misal chart, canvas, dsb)
                    page.wait_for_timeout(1500)
                    capture(page, page_id)
                else:
                    print(f"Tombol nav {page_id} tidak ditemukan.")

            # Dialog / Modal Watchlist Picker
            print("\nMengambil screenshot dialog Watchlist Picker...")
            page.locator('.nav-item[data-page="watchlist"]').click()
            page.wait_for_timeout(1000)
            picker_btn = page.locator('button[data-action="watchlist-open-picker"]').first
            if picker_btn.count() > 0:
                picker_btn.click()
                try:
                    page.wait_for_selector("#watchlist-picker:not(.hidden)", timeout=3000)
                except Exception:
                    pass
                page.wait_for_timeout(500)
                capture(page, "watchlist-picker")
                # Tutup picker
                close_btn = page.locator('button[data-action="watchlist-close-picker"]').first
                if close_btn.count() > 0:
                    close_btn.click()
                page.wait_for_timeout(500)

            # Issuer Dossier beserta semua Tab-nya
            print("\n--- Mengambil screenshot Issuer Dossier ---")
            page.locator('.nav-item[data-page="screener"]').click()
            try:
                page.wait_for_selector("tr[data-action='open-issuer']", timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(1000)
            
            row = page.locator("tr[data-action='open-issuer']").first
            if row.count() > 0:
                row.click()
                # Tunggu dossier selesai dimuat (bukan loading)
                try:
                    page.wait_for_selector("text=Memuat hasil per emiten", state="detached", timeout=8000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)
                
                print("Mengambil screenshot tab Dossier: Overview...")
                capture(page, "issuer")
                capture(page, "issuer-overview")

                # Ambil screenshot tab-tab lain dalam issuer dossier
                tabs = [
                    ("Flow", "issuer-flow"),
                    ("Evidence", "issuer-evidence"),
                    ("Historical Analog", "issuer-historical-analog"),
                    ("Event Study", "issuer-event-study"),
                    ("Outcomes", "issuer-outcomes"),
                ]
                for tab_name, file_name in tabs:
                    print(f"Mengambil screenshot tab Dossier: {tab_name}...")
                    tab_btn = page.locator(f'button.tab[data-tab="{tab_name}"]').first
                    if tab_btn.count() > 0:
                        tab_btn.click()
                        page.wait_for_timeout(1000)
                        capture(page, file_name)

                # Report Dossier (Export/Report PDF view)
                print("Mengambil screenshot Dossier Report view...")
                report_btn = page.locator('button[data-action="export"]').first
                if report_btn.count() > 0:
                    report_btn.click()
                    page.wait_for_timeout(1000)
                    capture(page, "issuer-report")
                    # Tutup report
                    close_report_btn = page.locator('button[data-action="dossier-report-close"]').first
                    if close_report_btn.count() > 0:
                        close_report_btn.click()
                        page.wait_for_timeout(500)

            context.close()
            browser.close()
            print("\nSemua screenshot berhasil diambil!")
    finally:
        print("Menghentikan server...")
        server_process.kill()

if __name__ == "__main__":
    main()
