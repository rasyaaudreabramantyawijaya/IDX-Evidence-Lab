# IDX Evidence Lab

Prototype riset saham Indonesia untuk **Sectors Hackathon Track 03: Market Intelligence**. Anda dapat menyaring emiten, menyusun studi, membaca arus asing dan berita, menguji alokasi portofolio, lalu mengajukan pertanyaan berdasarkan bukti yang tersedia.

**Data pasar pada prototype berasal dari snapshot lokal.** Startup tidak mengambil data Sectors baru. Agent OpenRouter dan riwayat bersama Supabase merupakan sambungan opsional; clone baru dapat berjalan tanpa keduanya. Aplikasi mendukung riset dan tidak mengirim order saham.

![Dashboard IDX Evidence Lab dengan ringkasan pasar dan grafik IHSG/LQ45](docs/assets/readme/dashboard.png)

Snapshot UI dalam README ini diambil pada 8 Oktober 2026 dari aplikasi lokal. Tanggal data mengikuti snapshot yang tersedia, bukan tanggal pengambilan gambar. Gambar tidak memuat API key, lampiran privat, atau percakapan pengguna.

## Daftar isi

- [Menjalankan di macOS dan Windows](#menjalankan-di-macos-dan-windows)
- [Workspace dan fitur](#workspace-dan-fitur)
- [Studies: paket dan 14 fitur](#studies-paket-dan-14-fitur)
- [Portfolio Lab dan Monte Carlo GBM](#portfolio-lab-dan-monte-carlo-gbm)
- [Riset emiten, Agent dan riwayat](#riset-emiten-agent-dan-riwayat)
- [Performa: bukti nyata dan contoh mock](#performa-bukti-nyata-dan-contoh-mock)
- [Struktur repo dan notebook](#struktur-repo-dan-notebook)
- [Pengujian dan troubleshooting](#pengujian-dan-troubleshooting)

## Menjalankan di macOS dan Windows

### Kebutuhan

- Git dan Python **3.10 atau lebih baru**.
- Browser desktop: Safari, Chrome, atau Edge.
- Koneksi internet untuk clone dan instalasi dependensi. Analisis snapshot lokal tidak memerlukan API key.
- Terminal tetap terbuka selama server berjalan.

Frontend menggunakan HTML, CSS, dan JavaScript. Anda tidak perlu Node.js, npm, MATLAB, GPU, atau build frontend untuk menjalankan website. Helper pengujian browser dan notebook mempunyai kebutuhan tambahan.

### macOS: MacBook, iMac, Mac mini, Apple Silicon maupun Intel

Buka Terminal. Pastikan `python3 --version` menunjukkan Python 3.10+. Jika Python belum tersedia, gunakan installer dari [python.org](https://www.python.org/downloads/macos/).

```bash
git clone https://github.com/rasyaaudreabramantyawijaya/IDX-Evidence-Lab.git
cd IDX-Evidence-Lab

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-portfolio.txt

IDXEL_RESEARCH_HISTORY_MODE=local IDXEL_ALLOW_PROVIDER_REQUESTS=0 IDXEL_PORT=5500 PYTHONPATH=src python3 -m idx_evidence_lab.web_app
```

Buka **http://127.0.0.1:5500**. Server Python melayani UI dan API pada alamat yang sama. Gunakan Safari atau browser pilihan Anda. Hentikan server dengan **Control+C**.

Untuk menjalankan lagi, masuk ke folder repo, aktifkan `.venv`, lalu ulangi perintah server terakhir. Flag `local` menyimpan riwayat pada komputer sendiri; flag `0` mencegah pemakaian kredit provider selama mencoba UI.

**iPhone/iPad:** repo ini berupa aplikasi web, bukan aplikasi native iOS/iPadOS. Jalankan backend di Mac atau server. Alamat `127.0.0.1` pada iPhone menunjuk iPhone itu sendiri, sehingga tidak membuka server Mac. Akses lintas perangkat membutuhkan hosting atau koneksi jaringan yang diatur dengan aman; deployment publik belum menjadi bagian dari setup lokal ini.

### Windows: PowerShell

Install Python dari [python.org](https://www.python.org/downloads/windows/) dan Git. Buka PowerShell; cek `py -3 --version`.

```powershell
git clone https://github.com/rasyaaudreabramantyawijaya/IDX-Evidence-Lab.git
cd IDX-Evidence-Lab

py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-portfolio.txt

$env:PYTHONPATH = "src"
$env:IDXEL_PORT = "5500"
$env:IDXEL_RESEARCH_HISTORY_MODE = "local"
$env:IDXEL_ALLOW_PROVIDER_REQUESTS = "0"
.\.venv\Scripts\python.exe -m idx_evidence_lab.web_app
```

Buka **http://127.0.0.1:5500** di Edge atau Chrome. Perintah di atas memakai Python virtual environment langsung, sehingga Anda tidak perlu mengubah execution policy untuk menjalankan `Activate.ps1`. Hentikan dengan **Ctrl+C**.

Jika `py` tidak dikenali tetapi `python --version` sudah menunjukkan versi yang sesuai, ganti `py -3 -m venv .venv` dengan `python -m venv .venv`. Jalankan perintah dari root repo, bukan dari `src/`.

### Alternatif: VS Code Live Server pada port 5500

Gunakan alternatif ini jika ingin **Go Live** untuk frontend. Jangan jalankan server mandiri Python 5500 pada waktu yang sama.

1. Buka root repo di VS Code dan install extension Live Server.
2. Jalankan backend di terminal pada **5514**:
   - macOS, setelah mengaktifkan venv: `IDXEL_PORT=5514 PYTHONPATH=src IDXEL_RESEARCH_HISTORY_MODE=local IDXEL_ALLOW_PROVIDER_REQUESTS=0 python3 -m idx_evidence_lab.web_app`.
   - Windows: gunakan environment PowerShell di atas, ubah `$env:IDXEL_PORT = "5514"`, lalu jalankan modul dengan Python venv.
3. Buka `docs/prototypes/idx-evidence-lab-user-journey.html` dan pilih **Go Live**.
4. Buka http://127.0.0.1:5500/docs/prototypes/idx-evidence-lab-user-journey.html.

Pada checkout ini, `.vscode/settings.json` meneruskan `/api` ke `http://127.0.0.1:5514/api`. Restart Go Live setelah mengubah proxy. Task **IDX Evidence Lab Seva: Local API (5514)** di `.vscode/tasks.json` juga dapat menyalakan sidecar melalui `scripts/run_portfolio_api_sidecar.py`. Task memakai executable `python3`; jika executable itu tidak tersedia di Windows, gunakan perintah terminal Windows di atas.

Cek http://127.0.0.1:5500/api/health. Health menunjukkan backend yang terhubung; health yang sukses belum membuktikan provider model menerima request.

## Workspace dan fitur

| Workspace | Isi dan tujuan |
|---|---|
| Dashboard | Ringkasan kondisi pasar untuk menentukan area riset. |
| Screener | Menyaring universe snapshot LQ45 dan memeriksa hasil event historis. |
| Watchlist | Menyimpan emiten pantauan di browser Anda. |
| Studies | Memilih paket analisis dan fitur engineering per emiten. |
| Riset emiten | Percakapan berbasis bukti, hasil perhitungan, dan konteks prototype. |
| Portfolio Lab | Alokasi, risiko, walk-forward, skenario, dan forecasting GBM. |
| Market overview | Indeks, arus asing, breadth, RSI, sektor, dan konteks tail loss. |
| News Universe | Menelusuri arsip berita lokal dengan filter. |
| Dossier emiten | Detail emiten yang Anda buka melalui ticker. |
| Sumber & metode · PDF | Pemeriksaan definisi, sumber dan asumsi, serta tampilan laporan untuk cetak/PDF. |

### Dashboard

- **Unusual Flow:** emiten dengan deviasi arus asing terhadap pembanding historis.
- **Market Regime IHSG:** posisi close/SMA50 terhadap SMA200 dan volatilitas 20 sesi.
- **Market Breadth LQ45:** jumlah naik, tetap, turun, serta proporsi di atas SMA.
- **Market capitalization:** agregat kapitalisasi universe snapshot yang tersedia.
- Grafik IHSG/LQ45, berita terbaru, dan **Signal vs Market Baseline** untuk membandingkan aturan regime dengan buy-and-hold historis.

Kartu membawa Anda ke workspace terkait. Hasil historis dan anomali flow membantu penelusuran; keduanya tidak menetapkan rekomendasi beli/jual.

### Screener

Cari ticker/nama, pilih sektor atau regime, lalu buka emiten. Tabel memuat:

- Flow strength **Z20 asing** dan jumlah sampel event.
- Rerata outcome **5D/20D**, hit rate ungguli IHSG 20D, confidence interval 95%, dan baseline delta.
- Regime teknikal per emiten, dihitung dari histori emiten tersebut.
- Ringkasan breadth LQ45 dan jumlah emiten yang sesuai filter.

Definisi event memakai net buy asing positif dengan Z20 ≥ 2. Entry berada pada close sesi berikutnya; perbandingan IHSG memakai tanggal identik. Kolom Data/As of yang berulang tidak ditampilkan pada tabel utama.

### Watchlist

Tambah/hapus emiten pilihan, cari melalui picker, dan urutkan kolom analisis. Watchlist tetap tersimpan lewat `localStorage` pada browser yang sama. Hasilnya memakai snapshot dan perhitungan yang tersedia; watchlist belum menjadi daftar pantauan cloud lintas pengguna.

### Dossier emiten

Klik ticker untuk membuka detail, lalu pilih tab:

| Tab | Yang dapat diperiksa |
|---|---|
| Overview | Ringkasan emiten, harga dan arus asing pada sumbu waktu bersama. |
| Flow | Net flow, akumulasi beberapa sesi, serta arsip broker yang tersedia. |
| Evidence | Bukti dan interpretasi outcome historis beserta pembanding. |
| Historical Analog | Kemiripan episode historis untuk konteks penelitian. |
| Event Study | Pilih event dan baca lintasan setelah entry. |
| Outcomes | Evaluasi historis per event, pembanding IHSG dan asumsi biaya yang tersedia. |

Kemiripan episode tidak membuktikan hasil masa depan. Cakupan data broker berbeda dari arus asing dan tidak mengungkap pemilik manfaat.

### Market overview

![Market Overview dengan grafik indeks dan regime IHSG](docs/assets/readme/market-overview.png)

Anda dapat membaca grafik IHSG/LQ45, regime IHSG, unusual foreign flow, beli/jual asing harian, Z-score flow bulanan, RSI market breadth, dan heatmap sektor. Panel tail-loss memuat surface historis 3D dan histogram distribusi kerugian harian dengan ambang empiris p95.

Surface 3D mendukung rotasi/zoom. Data visual berasal dari artifact numerik yang tersedia; MATLAB desktop hanya diperlukan bila ingin membangun ulang atau memakai sinkronisasi lokal yang terkait. Parameter tail dan ambang historis membutuhkan pemeriksaan ketidakpastian sebelum interpretasi prediktif.

### News Universe

Filter berita menurut emiten, sektor, tanggal, dan topik yang dikenali. Buka item untuk membaca ringkasan serta metadata sumber. Arsip berita dalam repo mempunyai cakupan terbatas; jangan menganggapnya feed berita live atau arsip lengkap.

### Sumber & metode · PDF

Periksa sumber snapshot, definisi indikator/event, cakupan, metode dan asumsi. Gunakan tampilan cetak browser untuk menyimpan laporan sebagai PDF. Panel ringkas pada workspace tidak menggantikan pemeriksaan sumber ketika Anda ingin menyimpulkan hasil penelitian.

### Pencarian bahasa alami dan interaksi grafik

Search box mencari workspace, emiten, fitur, paket, dan berita dalam katalog prototype. Tujuan yang Anda sebutkan secara eksplisit mendapat prioritas. Contoh:

> Aku mau masukkan BBCA ADMR BMRI BBRI ke Portfolio Lab dengan profil risiko agresif modal 1 milyar.

Query tersebut menyiapkan **Portfolio Lab**, empat ticker, profil agresif dan modal **Rp1.000.000.000**. Navigasi/prefill tidak menjalankan analisis atau mengirim prompt Agent; tekan tombol analisis ketika input sudah sesuai. Pencarian lokal ini tidak melatih LLM.

Pada grafik 2D yang mendukungnya, crosshair menunjukkan posisi X/Y, label tanggal/sesi/ticker, nilai dan tooltip. Grafik harga gabungan menampilkan nilai close, SMA dan EMA pada tanggal yang sama. Gunakan hover; grafik yang dapat difokuskan juga mendukung tombol panah/Home/End. Grafik 3D memakai interaksi rotasi dan tooltip titik.

## Studies: paket dan 14 fitur

![Studies dengan carousel paket dan katalog feature engineering](docs/assets/readme/studies.png)

Pilih maksimal **5 emiten** dari universe snapshot **45 simbol LQ45**. Pilih satu paket, tambah/kurangi fitur dengan tombol +/centang, atur periode, lalu tekan **Jalankan analisis** atau Enter/Return. Carousel mendukung geser manual, tombol navigasi, putaran otomatis dan jeda interaksi.

| Paket | Fitur yang disertakan |
|---|---|
| Issuer Quality | Valuation & quality, financial fragility, compare issuers, evidence & methodology. |
| Risk Ratios | Price & volatility, IHSG context & regime, market breadth, evidence & methodology. |
| Volatility | Price & volatility, trend & momentum, liquidity proxy. |
| Flow & Events | Issuer flow, event timeline, event outcomes, price & volatility, evidence & methodology. |
| Factor Map | Factor characteristics, valuation & quality, trend & momentum, evidence & methodology. |
| Evidence Review | Price & volatility, valuation & quality, issuer flow, timeline, IHSG context, breadth, compare issuers, evidence & methodology. |

Nama **Risk Ratios** adalah label paket Studies. Rasio portofolio Sharpe/Sortino/Calmar dan CAPM berada di Portfolio Lab.

### Katalog fitur engineering

| Fitur | Isi perhitungan/tampilan | Visual utama ketika input tersedia |
|---|---|---|
| Price & volatility | Return kumulatif, volatilitas tahunan, downside deviation, drawdown, ATR14. | Deret harga/risiko; perbandingan return periode vs volatilitas tahunan lintas emiten. |
| Trend & momentum | SMA14, EMA14, RSI14, MACD12/26. | Close + SMA + EMA pada satu grafik; indikator pada panel terkait. |
| Liquidity proxy | Close × volume dan rerata turnover proxy. | Deret turnover. Ini proxy transaksi, bukan depth/spread order book. |
| Valuation & quality | Earnings yield, dividend yield, ROE, debt-to-equity. | Perbandingan metrik yang seunit; field mengikuti laporan. |
| Financial fragility | Leverage/profitabilitas dan field kas, utang, laba, arus kas bila tersedia. | Perbandingan tahunan pada definisi dan satuan yang cocok. |
| Issuer flow & response | Net arus asing harian dan flow strength Z20. | Harga/flow dan batang Z-score. |
| Event timeline | Filings, berita terpilih, aksi korporasi, suspensi. | Daftar kronologis untuk membaca bukti peristiwa. |
| IHSG context & regime | IHSG close, SMA50/200, volatilitas dan return relatif benchmark. | Overlay indeks/moving average serta konteks benchmark. |
| Market breadth · LQ45 | Naik/turun/tetap; di atas SMA20/SMA50. | Batang jumlah dan proporsi partisipasi emiten. |
| Factor characteristics & exposure | Value, quality, momentum, low volatility. | Profil karakteristik/skor; exposure bila bobot tersedia. |
| Compare issuers | Valuasi, ROE, leverage dan return pada periode bersama. | Batang peer comparison per metrik sejenis. |
| Event study & outcomes | Outcome 5/20D, delta IHSG, hit rate/CI95, MAE/MFE close 20D. | Lintasan event, batang outcome/excursion dan interval hit rate. |
| Custom feature engineering | Difference, pct change, rolling mean/std, robust Z. | Deret hasil transform allowlist pada close, volume atau foreign flow. |
| Evidence & methodology | Observasi, snapshot dan cakupan input perhitungan. | Ringkasan/tabulasi; tidak perlu chart untuk metadata. |

![Overlay harga BBCA, SMA14 dan EMA14 dengan crosshair dan label tanggal tepat](docs/assets/readme/studies-trend.png)

Hasil tersusun per emiten. Compare issuers memakai pilihan bersama; market breadth memakai universe LQ45. Anda dapat menyimpan susunan studi pada browser. Target return pada grafik gabungan merupakan input pembanding untuk periode yang sama, bukan forecast.

Periode deteksi event terpisah dari window indikator. Default Event study & outcomes memakai histori tersedia, sama dengan Screener. MAE/MFE mengukur minimum/maksimum `close / entry_close - 1`, termasuk entry 0, hingga exit 20 sesi. Keduanya memakai harga close, bukan high/low intraday.

UI dapat menampilkan **0 sebagai placeholder** bila data tidak tersedia. Engine tetap mempertahankan null dan alasan missing; placeholder tidak menjadi observasi untuk training/perhitungan. Field bank dan nonbank, tanggal laporan, serta jumlah event matang dapat berbeda.

## Portfolio Lab dan Monte Carlo GBM

Pilih emiten, profil **Konservatif/Moderat/Agresif**, asumsi risk-free tahunan, dan modal opsional. Tekan **Jalankan analisis lokal**.

| Bagian | Isi |
|---|---|
| Alokasi | Bobot long-only, nominal, ilustrasi lot 100 saham, dan sisa kas. |
| Risiko | Sharpe, Sortino, Calmar, volatilitas, downside deviation dan maximum drawdown. |
| Konsentrasi | Distribusi sektor dan karakteristik eksposur portofolio. |
| Optimizer | Markowitz long-only dengan estimasi Black–Litterman dan batas diversifikasi yang mengikuti profil. |
| Audit model | Metode pembanding dan baseline; HRP tersedia dalam jalur audit. |
| Walk-forward | Estimasi dari sesi sebelumnya, rebalance bulanan, pembanding equal-weight pada tanggal identik. |
| Bootstrap | Skenario eksploratif dengan blok return historis. |
| GBM | Monte Carlo multivariat, lintasan contoh, median/p10–p90, return dan maximum drawdown per horizon. |
| CAPM | Beta/IHSG historis dan hurdle berbasis risk-free/premi asumsi. |
| Factor Zoo | Scatter 3D value–momentum–quality, warna low-volatility, leaderboard dan exposure berbobot. |

Factor Zoo menyajikan karakteristik relatif, belum merupakan faktor return Fama–French atau attribution return. CAPM memakai asumsi manual dan histori yang tersedia. Biaya transaksi belum masuk seluruh hasil Portfolio Lab; alokasi lot merupakan ilustrasi.

### Model GBM yang digunakan

Model tetap **geometric Brownian motion multivariat**, versi `multivariate_gbm_fixed_share_v1` pada [portfolio_scenarios.py](src/idx_evidence_lab/portfolio_scenarios.py). Engine mengestimasi rerata/kovarians log-return dari jendela trailing, default 252 sesi, dan mensimulasikan aset berkorelasi. Bobot awal mengikuti buy-and-hold/fixed-share sehingga dapat drift.

Default UI: **300 lintasan**, **seed 42**, horizon **20/60/120 sesi bursa**. Grafik menampilkan 20 lintasan contoh dari simulasi tersebut, median dan pita p10–p90. Seluruh jalur bermula dari indeks portofolio 100. Bootstrap tetap menjadi pembanding skenario terpisah.

![Monte Carlo GBM dengan lintasan, median, pita kuantil, dan crosshair](docs/assets/readme/portfolio-gbm.png)

Pengujian out-of-sample mengkalibrasi GBM dari sesi sebelum setiap origin, dengan langkah 21 sesi. Engine membandingkan realisasi berikutnya terhadap kuantil melalui coverage, PIT dan pinball loss. Coverage nominal p10–p90 adalah 80%; pinball lebih kecil lebih baik. Baseline berasal dari jendela historis dalam sampel kalibrasi yang sama.

Minimum fold efektif = **10**, dengan estimasi `fold × 21 / horizon`. Status return dan drawdown dapat berbeda. Label internal `OOS_CALIBRATED` memakai kriteria kode dan tidak menjamin prediksi pada data baru. GBM mengasumsikan parameter konstan dan log-return normal; fat tail/perubahan regime dapat menyebabkan miscalibration.

## Riset emiten, Agent dan riwayat

![Riset emiten dengan sidebar riwayat dan composer; mode lokal tanpa percakapan contoh](docs/assets/readme/research.png)

- **Instant:** retrieval dan analisis lokal dari snapshot serta hasil perhitungan.
- **Agent:** OpenRouter menyusun jawaban dari konteks yang diizinkan dan validasi sumber/angka.
- **Cek konteks · tanpa API:** lihat bukti, metrik dan celah data sebelum mengirim prompt.
- Template **Analisis emiten / Bandingkan emiten / Jelaskan portofolio / Ringkas untuk video** mengisi draft; Anda memilih Kirim.
- Sidebar menyimpan prompt dan jawaban asli. Label Agent hanya berlaku pada respons provider yang berhasil; fallback tetap mendapat identitas hasil lokal.

Konteks menggabungkan snapshot, hasil Studies/Portfolio yang tercatat dan dokumentasi metode terpilih. Aplikasi tidak mengirim seluruh repo, API key, dokumen internal atau file privat ke satu prompt; persiapan konteks tidak melatih model. Analisis lama yang hanya berada di memori browser perlu dijalankan ulang agar engine mencatat artifact lokalnya.

Contoh prompt untuk dicoba sendiri:

> Bandingkan BBCA dan BMRI berdasarkan valuasi, kualitas, arus asing dan risiko yang tersedia. Sebutkan periode serta sumber tiap angka. Pisahkan temuan historis, asumsi dan interpretasi; jelaskan bagian yang belum memiliki data.

### Mengaktifkan OpenRouter pada mesin sendiri

Jalankan helper dari root repo:

```bash
# macOS, venv aktif
python3 scripts/configure_openrouter.py
```

```powershell
# Windows
.\.venv\Scripts\python.exe scripts/configure_openrouter.py
```

Tempel key pada input tersembunyi. Pilih model yang tersedia untuk akun Anda, atau tekan Enter untuk default kode. Helper membuat `.env.local`; helper menolak overwrite jika file itu sudah ada. Pertahankan konfigurasi lain saat mengedit file yang sudah ada, jangan menghapusnya untuk mengulang setup.

Restart backend dengan **`IDXEL_ALLOW_PROVIDER_REQUESTS=1`** untuk mengizinkan prompt:
- macOS: ganti `IDXEL_ALLOW_PROVIDER_REQUESTS=0` pada perintah server dengan `1`.
- Windows: set `$env:IDXEL_ALLOW_PROVIDER_REQUESTS = "1"` sebelum memulai backend.

| Variabel | Fungsi |
|---|---|
| `OPENROUTER_API_KEY` | Key milik operator server; simpan privat. |
| `OPENROUTER_MODEL` | Model utama. |
| `OPENROUTER_FALLBACK_MODELS` | Model cadangan untuk jalur lokal yang mendukungnya. |
| `IDXEL_ALLOW_PROVIDER_REQUESTS` | `0` memblokir transport provider; `1` mengizinkannya. |

Periksa [katalog model OpenRouter](https://openrouter.ai/models) bila model default tidak tersedia. Biaya dan kuota mengikuti akun/model Anda. Key yang terbaca tidak membuktikan request berhasil. Jalur lokal dapat mencoba fallback atau repair dalam batas kode; satu prompt lokal dapat memakai lebih dari satu request. Jalur bersama di bawah membatasi satu percobaan.

Markdown jawaban mendukung heading, teks, daftar dan tabel. Mode lokal mendukung streaming blok tervalidasi; mode bersama menunggu jawaban akhir yang lolos proyeksi publik. Aplikasi tidak menyediakan web search untuk mengambil fakta pasar baru.

Lampiran teks/PDF text-layer tersedia pada mode lokal sesuai batas UI. OCR/vision untuk scan atau gambar belum tersedia. Korpus hukum privat tidak termasuk clone; file yang diterima belum tentu dapat diekstrak atau menjadi bukti.

### Riwayat lokal vs riwayat bersama Supabase

| Mode | Penyimpanan dan perilaku |
|---|---|
| `IDXEL_RESEARCH_HISTORY_MODE=local` | SQLite privat di folder data aplikasi, terpisah per checkout. Rename/pin lokal tersedia. `IDXEL_RESEARCH_HISTORY_PATH` dapat mengatur lokasi alternatif. |
| `IDXEL_RESEARCH_HISTORY_MODE=shared` | PostgreSQL Supabase: pengguna aplikasi membaca dan melanjutkan thread yang sama. Pesan lama tetap immutable; pin hanya milik browser sendiri. |

Clone tidak menerima credential operator atau otomatis terhubung ke database bersama. Untuk mengaktifkan mode bersama, operator menerapkan [migration SQL](supabase/migrations/202610080001_shared_research_history.sql), lalu menyediakan `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, dan mode `shared` di environment **backend**. Pada macOS, file konfigurasi privat memerlukan permission 0600. Pada Windows, gunakan environment backend/secret store untuk mode bersama karena pemeriksaan permission file saat ini memakai bit POSIX.

Jangan letakkan Supabase secret/service key pada frontend. Mode bersama menolak lampiran privat dan kredensial yang terdeteksi; jangan mengirim informasi rahasia pada thread publik. Dua kiriman bersamaan tidak boleh menimpa thread: UI mempertahankan draft saat konflik. Opening, polling dan replay riwayat tidak mengirim request model.

Batas awal bersama adalah **20 giliran Agent per jam UTC** untuk instalasi bersama, termasuk percobaan yang gagal. Satu pengiriman memakai satu percobaan model tanpa fallback/repair otomatis. Pembatalan tidak menjamin pengembalian kredit provider. Migrasi riwayat lama harus melewati preview dan pemeriksaan privasi melalui [script migrasi](scripts/migrate_shared_research_history.py); pemeriksaan aktivasi lokal pada 8 Oktober 2026 menemukan 0 sesi lama.

Operator telah mengaktifkan mode bersama pada prototype lokal. Pengguna lain memerlukan akses ke instance aplikasi yang terhubung ke database itu; menyalin repo saja tidak menyamakan riwayat. Deployment Vercel, data pasar live dan autentikasi production masih merupakan pekerjaan terpisah.

## Performa: bukti nyata dan contoh mock

### Bukti yang tersedia

| Jenis bukti | Hasil/sumber | Yang dapat disimpulkan |
|---|---|---|
| Agreement rumus Studies | **57/57 kasus referensi** pada 4 kelompok, [manifest](reports/studies-reference-manifest.json) dan [JUnit XML](reports/studies-reference-tests.xml). | Formula cocok pada kasus dan toleransi yang tercatat. Ini bukan 100% akurasi prediksi pasar atau cakupan 14 fitur. |
| Kelompok referensi | Price/risk 4, trend/momentum 24, custom transforms 15, event outcomes 14 kasus. | Ruang lingkup deterministik yang diperiksa. |
| Suite software | Run lokal 8 Oktober 2026: **483 tes lulus**, 5 warning deprecation PyMuPDF. | Pemeriksaan kode/API/privasi dan mock provider; bukan evaluasi kualitas LLM nyata. |
| Browser | Snapshot UI, overlay SMA/EMA dan crosshair serta lintasan GBM berhasil dirender dari data lokal. | Bukti fitur visual; tidak membuktikan profitability. |
| OpenRouter | Penyusunan README/snapshot mengirim **0 prompt model**. | Tidak ada benchmark LLM nyata baru untuk diklaim. |

Contoh **hasil GBM nyata dari snapshot lokal**, sesuai gambar di atas: BBCA, ADMR, BMRI, BBRI; profil agresif; lookback 252; risk-free manual 7,129% p.a.; modal Rp1 miliar; cutoff **2026-09-24**, 300 simulasi, seed 42.

| Horizon | Coverage return p10–p90 | Status return | Coverage MDD p10–p90 | Status MDD |
|---|---|---|---|---|
| 20 sesi | 71,4% | `OOS_CALIBRATED` menurut kriteria engine | 61,9% | `OOS_MISCALIBRATED` |
| 60 sesi | 52,6% | `INSUFFICIENT_OOS_FOLDS` | 57,9% | `INSUFFICIENT_OOS_FOLDS` |
| 120 sesi | 43,8% | `INSUFFICIENT_OOS_FOLDS` | 68,8% | `INSUFFICIENT_OOS_FOLDS` |

Target coverage nominal adalah 80%. Hasil ini berubah dengan input, periode dan snapshot. MDD 20 sesi belum terkalibrasi pada contoh ini; horizon panjang belum memiliki fold efektif yang cukup. Return yang lolos kriteria internal tidak menetapkan bahwa keseluruhan model “bagus” atau siap dipakai untuk keputusan investasi.

### MOCK: contoh kartu performa yang baik, bukan hasil pengujian

**Seluruh angka tabel berikut fiktif untuk ilustrasi presentasi.** Tabel tidak berasal dari training, backtest, OpenRouter, atau hasil Portfolio Lab. Jangan menggunakannya sebagai bukti performa pada judging video.

| Metrik ilustratif | Model MOCK | Baseline MOCK | Cara membaca |
|---|---|---|---|
| Coverage p10–p90 | 80% | 75% | Contoh coverage model dekat nominal 80%. |
| Pinball loss | 0,025 | 0,030 | Contoh loss model lebih rendah dari pembanding. |
| Fold efektif | 12 | 12 | Contoh jumlah fold memenuhi batas minimum 10. |

Contoh caption: **“MOCK: ilustrasi format evaluasi model; hasil benchmark belum diwakili oleh angka ini.”** Untuk menampilkan hasil asli, gunakan tabel OOS dari input yang Anda jalankan, termasuk kegagalan kalibrasi dan jumlah sampelnya.

## Struktur repo dan notebook

```text
src/idx_evidence_lab/       Backend, retrieval, engine numerik, adapter provider/storage
docs/prototypes/           HTML/JS, JSON tampilan, dossier emiten, artifact chart
docs/assets/readme/        Enam screenshot UI yang aman untuk README
data/raw/sectors/          Snapshot sumber lokal dan metadata/hash
configs/                  Schema query dan policy sumber/provider
scripts/                  Startup, konfigurasi key, export, verifikasi, migrasi
supabase/migrations/       Schema/RPC untuk riwayat bersama
tests/                    Tes formula, API, UI, privasi dan storage
reports/                  Manifest/XML referensi rumus yang dipakai Studies
notebooks/                Notebook analisis dan validasi
fetch.ipynb               Notebook pengambilan data legacy
.vscode/                  Task dan proxy Live Server
```

Website membutuhkan `docs/prototypes/` saat runtime. File `.fig` merupakan artifact chart MATLAB. Simpan definisi/periode sumber; data mentah kosong tidak boleh menjadi observasi nol. Keanggotaan LQ45 saat ini tidak otomatis mewakili membership historis atau seluruh IDX.

Untuk dependensi notebook tambahan:

```bash
# macOS, venv aktif
python3 -m pip install -r requirements-notebooks.txt
python3 scripts/export_portfolio_lab_notebook_data.py
```

```powershell
# Windows
.\.venv\Scripts\python.exe -m pip install -r requirements-notebooks.txt
.\.venv\Scripts\python.exe scripts/export_portfolio_lab_notebook_data.py
```

Export membangun `data/processed/portfolio_lab_bundle.zip` dari snapshot yang tersedia tanpa fetch baru. Upload bundle ke Colab atau lampirkan sebagai dataset Kaggle sesuai sel setup. Notebook membutuhkan package lokal, data dan artifact yang disebutkan di dalamnya; path laptop pengembang tidak tersedia pada mesin orang lain.

Notebook `engine-smart-money_lq45-wXGBOOST.ipynb` masih mengimpor `backend.src.*` yang tidak tersedia di checkout ini. `fetch.ipynb` memerlukan setup credential dan dapat melakukan request API. Notebook legacy bukan runtime website atau bukti model tervalidasi. Periksa sel sebelum training/fetch; penulisan README ini tidak menjalankan notebook tersebut.

Panduan integrasi quant-lab dan rencana Vercel milik maintainer merupakan referensi pengembangan lokal. Runtime tidak membutuhkan sibling quant-lab, folder skill atau path absolut komputer pengembang.

## Pengujian dan troubleshooting

Jalankan dari root repo:

```bash
# macOS, venv aktif
python3 -m pytest -q
```

```powershell
# Windows
.\.venv\Scripts\python.exe -m pytest -q
```

Tes memakai fixture/mocks provider dan koneksi server loopback. Tes referensi dan browser tidak mengukur kualitas respons OpenRouter nyata. Helper browser di `scripts/verify_*_browser.mjs` memerlukan Node.js, Playwright dan browser, serta konfigurasi helper yang sesuai; semuanya opsional untuk menjalankan website.

| Masalah | Pemeriksaan |
|---|---|
| `No module named idx_evidence_lab` | Jalankan dari root repo dan set `PYTHONPATH=src`. |
| `Address already in use` | Pilih server mandiri atau Go Live; jangan memakai port 5500 untuk dua listener. |
| API 404 saat Go Live | Pastikan backend 5514 hidup dan proxy `/api` sesuai. Stop/start Go Live setelah perubahan. |
| UI/API contract berbeda | Pastikan frontend dan backend berasal dari checkout/versi yang sama; restart dan reload. |
| Agent belum tersambung | Periksa konfigurasi model/key dan flag provider. Jangan tampilkan nilai key pada log/screenshot. |
| HTTP 401/402/429 | Periksa authentication, kredit atau rate limit pada akun provider; status health tidak membuktikan pemulihan. |
| Riwayat bersama tidak tersedia | Periksa migration/RPC, environment backend dan permission konfigurasi. Shared mode gagal tertutup, tanpa fallback diam-diam ke SQLite. |
| Hash/Studies reference gagal di Windows | Pertahankan LF melalui `.gitattributes`; jangan mengedit/menormalisasi snapshot sumber atau manifest secara sembarang. |
| Panel kosong atau nol placeholder | Periksa input, warm-up indikator, periode, field laporan dan kematangan event. |
| Data belum terbaru | Website membaca snapshot. Menjalankan ulang server tidak melakukan refresh Sectors. |

Server dan UI telah diperiksa pada macOS dengan dependensi yang tersedia; instalasi ulang pada Mac bersih belum diuji pada pembaruan README ini. Instruksi PowerShell mengikuti struktur repo tetapi **belum diuji pada mesin Windows nyata**. Karena branch dapat berbeda, sesuaikan proxy dengan file konfigurasi pada clone Anda.

## Privasi, publikasi dan batas penggunaan

API key, `.env.local`, database lokal, lampiran pengguna, korpus hukum, usage log, rencana internal dan cache tetap di luar Git. Enam screenshot README mendapat pengecualian spesifik dalam `.gitignore`; gambar tersebut tidak menyertakan identitas percakapan atau key.

Repo yang dapat diakses publik tidak otomatis memberikan hak redistribusi data provider. Periksa lisensi dan ketentuan sumber sebelum menyebarkan data atau mengaktifkan layanan live. Aplikasi tidak menyediakan jaminan return, penetapan pemilik manfaat, kepastian hukum, atau eksekusi transaksi.

`README` ini mendokumentasikan prototype pada checkout saat ini. **Supabase bersama, deployment aplikasi, dan pembaruan data Sectors adalah tiga kemampuan berbeda.** Operator harus menyiapkan secret server, persistence, akses pengguna, refresh tervalidasi dan pengujian cloud sebelum menyebut layanan Vercel/data live siap.
