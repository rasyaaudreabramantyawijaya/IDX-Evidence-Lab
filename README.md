# IDX Evidence Lab

Prototype riset pasar saham Indonesia untuk Sectors Hackathon Track 03: Market Intelligence. Pengguna menelusuri emiten, sektor, berita, perhitungan fitur dan risiko portofolio dari snapshot Sectors lokal, lalu memeriksa sumber dan batas analisisnya.

Tim: Rasya Audrea Bramantya Wijaya, Fardan, Thariq, Seva.

## Jalankan website

Python 3.10+ diperlukan. Dari root repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-portfolio.txt
PYTHONPATH=src python3 -m idx_evidence_lab.web_app
```

Buka `http://127.0.0.1:5500` atau `http://127.0.0.1:5500/docs/prototypes/idx-evidence-lab-user-journey.html`. Server Python melayani website dan API pada origin yang sama. Windows: gunakan aktivasi virtual environment Windows dan set `PYTHONPATH=src` sebelum menjalankan modul.

### VS Code / Go Live

Alternatif: jalankan task **IDX Evidence Lab: Local API (5501)** lalu **Go Live**. Live Server memakai `127.0.0.1:5500`; `.vscode/settings.json` meneruskan `/api` ke API lokal di `127.0.0.1:5501`. Jika pengaturan proxy berubah, stop lalu mulai Go Live kembali. Jangan menjalankan server Python 5500 bersamaan dengan Live Server 5500.

Periksa `http://127.0.0.1:5500/api/health`. Respons kesehatan lokal tidak membuktikan bahwa provider OpenRouter sedang menerima request.

## Workspace

Dashboard, Screener, Watchlist, Studies, Riset emiten, Portfolio Lab, Market overview, News Universe, dossier per emiten, sumber/metode dan pengaturan existing. Studies menghitung widget allowlist dari target dan window. Portfolio Lab menghitung alokasi dan risiko. Riset emiten menyediakan percakapan teks dengan target emiten/sektor, lampiran lokal, Instant dan Agent.

READY berarti perhitungan tersedia untuk input tersebut, bukan prediksi akurat atau data lengkap. PARTIAL, INSUFFICIENT_EVIDENCE, missing dan stale tetap perlu dibaca. Auto-Agent untuk seluruh query kompleks, executor chat lintas workspace, paste panjang dan Profil belum boleh dianggap selesai hanya karena source/UI yang terkait ada.

## Struktur

```text
src/idx_evidence_lab/       Server, retrieval, analisis, perhitungan, provider adapters
docs/prototypes/           HTML/JavaScript, data tampilan dan dossier JSON
data/raw/sectors/          Snapshot pasar lokal beserta metadata/hash
configs/                  Schema query dan policy sumber saat runtime
scripts/                  Startup, konfigurasi lokal, export, helper perhitungan
tests/                    Tes perhitungan, API lokal dan frontend
reports/                  Manifest dan XML referensi rumus yang dibaca Studies
notebooks/                Notebook analisis dan validasi
fetch.ipynb               Notebook pengambilan data legacy
.vscode/                  Task API dan proxy Live Server
```

`docs/prototypes/` berisi file website yang diperlukan saat runtime, bukan hanya rencana desain. File `.fig` adalah artifact chart numerik MATLAB, bukan screenshot/foto.

Snapshot lokal yang aplikasi baca tetap disertakan, termasuk cache broker parsial. Startup tidak mengambil data pasar baru. Snapshot memiliki cakupan dan tanggal historis; jangan memperlakukannya sebagai data live. Repo tetap privat; izin akses GitHub tidak menggantikan kewajiban penggunaan/redistribusi data penyedia.

## Notebook

Seluruh 11 notebook di `notebooks/` dan `fetch.ipynb` disertakan. Untuk dependensi tambahan:

```bash
python3 -m pip install -r requirements-notebooks.txt
```

Notebook berbasis package lokal membutuhkan `src/`, snapshot dan artifact yang disebut di sel setup. Colab/Kaggle memerlukan upload/attachment proyek atau bundle sesuai petunjuk notebook. Path laptop pengembang tidak otomatis tersedia di Colab/Kaggle.

Notebook Portfolio Lab dan Factor Zoo membutuhkan bundle. Buat dari snapshot yang tersedia tanpa request API baru:

```bash
python3 scripts/export_portfolio_lab_notebook_data.py
```

Unggah `data/processed/portfolio_lab_bundle.zip` ke Colab atau lampirkan sebagai dataset Kaggle. ZIP tidak masuk Git karena dapat dibangun ulang.

`engine-smart-money_lq45-wXGBOOST.ipynb` masih memiliki import `backend.src.*` yang tidak tersedia pada checkout sumber ini. `fetch.ipynb` berisi pengambilan data dan memerlukan setup/credential yang sesuai. Keduanya merupakan notebook legacy, bukan runtime website atau bukti model tervalidasi. Dependensi pip tidak menyediakan modul backend yang hilang. Periksa sel sebelum menjalankan; sebagian dapat melakukan request API/training. Publikasi ini tidak menjalankan notebook, training atau fetch tersebut.

Gambar tersimpan, attachment gambar notebook dan output gambar embedded tidak ikut publikasi. Kode pembuat chart dan output bukan gambar dipertahankan. Pengguna dapat menjalankan sel visualisasi setelah meninjau inputnya.

## OpenRouter dan dokumen lokal

Instant tidak memerlukan OpenRouter. Untuk mengaktifkan Agent pada mesin sendiri:

```bash
python3 scripts/configure_openrouter.py
```

Key berada di `.env.local` dan tidak masuk Git. OpenRouter membantu menafsirkan instruksi dan menyusun jawaban dari bukti yang diizinkan, bukan mencari fakta pasar di luar snapshot. HTTP 429 adalah kegagalan provider/rate limit; key terkonfigurasi bukan bukti request berhasil. Uji offline tidak membuktikan limit provider sudah teratasi.

Korpus `Business & Corporate Law/` dan file pengguna privat tidak disertakan. Pemilik mesin harus menyediakan korpus hukum secara lokal jika membutuhkan retrieval hukum. Tanpanya website tetap berjalan, tetapi tidak memiliki bukti hukum privat. PDF text-layer dapat diekstrak lokal; OCR/vision foto atau scan belum tersedia. File terunggah belum tentu terbaca.

API key harus berada di server. File privat utuh tidak boleh masuk prompt, log, export atau commit. Aplikasi tidak mengeksekusi transaksi saham. Output mendukung riset, bukan jaminan return, identifikasi pemilik manfaat atau kepastian hukum.

## Tes

```bash
PYTHONPATH=src python3 -m pytest -q
```

Tes memakai fixture/mocks untuk koneksi eksternal dan server loopback lokal. Jalankan dari root repo. Hasil tes terpisah dari kualitas data, probabilitas forecasting dan hasil notebook.

## Yang tidak masuk Git

Screenshot/foto, handoff/moodboard/user-flow visual, plans, skills, instruksi agent, dokumentasi QA/design/privacy, usage log, key, korpus hukum privat, cache Python dan environment. README ini menjelaskan setup dan keterbatasan tanpa membawa dokumen perencanaan. Penghapusan dokumen dari versi terbaru tidak menghapus commit historis repository tujuan yang sudah ada sebelumnya.
