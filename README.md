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

### Portfolio Lab · prediksi GBM

Section **Prediktif GBM · return & maximum drawdown** (`forecast_gbm` di `portfolio_scenarios.py`, field `forecast` pada `POST /api/portfolio-analysis`) memprediksi distribusi return kumulatif dan maximum drawdown untuk horizon skenario (default 20/60/120 sesi).

- Model: geometric Brownian motion multivariat. Rerata dan kovarians log-return harian dikalibrasi dari 252 sesi terakhir (atau lookback bila lebih pendek). Bobot awal dibiarkan drift (buy-and-hold), sama seperti bootstrap.
- Uji out-of-sample: setiap 21 sesi, GBM dikalibrasi hanya dari sesi sebelum titik asal, lalu realisasi return dan MDD sesudahnya dinilai terhadap p10–p90 (coverage nominal 80%), PIT dan pinball loss. Baseline adalah semua jendela bergulir di sampel kalibrasi yang sama.
- Status per horizon dan target: `OOS_CALIBRATED` (boleh dibaca prediktif), `OOS_CALIBRATED_BELOW_BASELINE`, `OOS_MISCALIBRATED` (coverage meleset lebih dari 15 poin) atau `INSUFFICIENT_OOS_FOLDS`. Fold efektif = fold × 21 ÷ horizon dan minimal 10. Dengan snapshot ~700 sesi, horizon 60/120 belum bisa lolos.
- Batas: volatilitas konstan dan log-return normal, jadi fat tail dan perubahan rezim tidak tertangkap. MDD sering gagal kalibrasi karena drawdown nyata lebih dalam. Bobot yang sama dipakai di semua fold, jadi uji menilai GBM, bukan optimizer. Bruto tanpa biaya dan belum dividend-adjusted.
- Skenario bootstrap blok tetap ditampilkan sebagai pembanding eksploratif.

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

### Konfigurasi model

`.env.local` hanya membaca tiga variabel berikut. Environment proses didahulukan bila sudah terisi. Nama variabel harus persis; `OPENROUTER=...` tidak terbaca.

| Variabel | Default | Fungsi |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Wajib. |
| `OPENROUTER_MODEL` | `apodex/apodex-1.1-mini:free` | Model utama. |
| `OPENROUTER_FALLBACK_MODELS` | `nvidia/nemotron-3-super-120b-a12b:free,dots-studio/dots-3-note-preview:free` | Model cadangan, dipisah koma, dicoba berurutan. |

Katalog model `:free` sering berubah. Jika model hilang (HTTP 404), ganti di `.env.local` dengan model dari `https://openrouter.ai/api/v1/models` yang mencantumkan `response_format` di `supported_parameters`. Default dipilih dan diuji pada 2026-10-07.

### Model cadangan dan perbaikan jawaban

Ketiga fitur (penafsiran pencarian, riset emiten, Agent) memakai alur yang sama di `openrouter_live.py`:

- Model dicoba berurutan. HTTP 404 (model dipensiunkan), 429, 5xx dan error di tengah stream pindah ke model berikutnya. HTTP 401/402/403 dan jaringan putus langsung berhenti karena model lain tidak membantu.
- Jawaban yang ditolak validasi lokal mendapat satu giliran perbaikan pada model yang sama. Model menerima kode penolakan (misalnya `UNSUPPORTED_NUMBER`) beserta petunjuknya, lalu mengirim ulang JSON lengkap. Jika masih ditolak, model berikutnya dicoba. Penafsiran pencarian tidak memakai giliran perbaikan karena harus selesai sebelum batas 30 detik browser dan sudah punya fallback lokal.
- Angka dicocokkan berdasarkan nilai dan satuan, bukan string: `381.0` sah untuk kutipan `381,0`, `6250` untuk `Rp6.250`. Parafrase (`60 juta` untuk `60.000.000`), satuan berbeda (`%` vs `pp`) dan angka tanpa sumber tetap ditolak.
- Aturan validasi tidak dilonggarkan. Jika semua model gagal, UI menampilkan hasil mesin lokal dan `model_status.diagnostics.rejection` mencatat kode penolakan terakhir.

Batas free tier: akun tanpa kredit dibatasi sekitar 50 request model `:free` per hari. Satu pertanyaan Agent dapat memakai hingga 6 request (3 model × jawaban + perbaikan). Kurangi `OPENROUTER_FALLBACK_MODELS` untuk menghemat kuota.

### Streaming Agent

`POST /api/research-chat` dengan `"stream": true` mengembalikan `text/event-stream`. Tanpa `stream`, respons JSON tetap seperti sebelumnya.

| Event | Data | Arti |
|---|---|---|
| `status` | `{model, attempt}` | Model dan percobaan yang sedang berjalan. |
| `block` | satu blok jawaban | Blok sudah lolos `validate_answer_block`. |
| `reset` | `{model, rejection}` | Percobaan ditolak; blok yang sudah tampil ditarik. |
| `done` | payload respons JSON | Jawaban akhir, divalidasi ulang secara utuh. |
| `error` | `{error}` | Kode error yang sama dengan respons JSON, misalnya `SESSION_EXPIRED`. |

Teks blok ditampilkan sebagai Markdown sederhana: heading `###`, **tebal**, *miring*, `kode`, daftar `-` dan tabel pipa. Renderer membangun elemen dengan `textContent`, jadi HTML dari model tampil sebagai teks; link, gambar dan HTML tetap ditolak validator. Daftar bernomor tidak diminta karena angka urutan tanpa sumber ditolak sebagai `UNSUPPORTED_NUMBER`.

Teks model yang belum lolos validasi tidak pernah dikirim ke browser. Sesi riset tetap di memori server; fitur ini tidak menambah database, skema maupun dependensi.

Korpus `Business & Corporate Law/` dan file pengguna privat tidak disertakan. Pemilik mesin harus menyediakan korpus hukum secara lokal jika membutuhkan retrieval hukum. Tanpanya website tetap berjalan, tetapi tidak memiliki bukti hukum privat. PDF text-layer dapat diekstrak lokal; OCR/vision foto atau scan belum tersedia. File terunggah belum tentu terbaca.

API key harus berada di server. File privat utuh tidak boleh masuk prompt, log, export atau commit. Aplikasi tidak mengeksekusi transaksi saham. Output mendukung riset, bukan jaminan return, identifikasi pemilik manfaat atau kepastian hukum.

## Tes

```bash
PYTHONPATH=src python3 -m pytest -q
```

Tes memakai fixture/mocks untuk koneksi eksternal dan server loopback lokal. Tes OpenRouter memalsukan `urlopen`, termasuk respons SSE, sehingga tidak ada request jaringan. Jalankan dari root repo. Di Windows, `.gitattributes` menjaga snapshot `data/raw/` dan sumber `studies_*.py` tetap LF; tanpa itu `core.autocrlf` mengubah hash dan Portfolio Lab/Studies menjadi BLOCKED/NOT_TESTED. Hasil tes terpisah dari kualitas data, probabilitas forecasting dan hasil notebook.

## Yang tidak masuk Git

Screenshot/foto, handoff/moodboard/user-flow visual, plans, skills, instruksi agent, dokumentasi QA/design/privacy, usage log, key, korpus hukum privat, cache Python dan environment. README ini menjelaskan setup dan keterbatasan tanpa membawa dokumen perencanaan. Penghapusan dokumen dari versi terbaru tidak menghapus commit historis repository tujuan yang sudah ada sebelumnya.
