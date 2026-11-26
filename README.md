# Personal Learning Intelligence (PLI)

Platform pembelajaran adaptif berbasis AI untuk sekolah. **Status saat ini: FASE 6 — offline-first lengkap, sinkronisasi dua arah, keamanan/retensi, dan operasional selesai secara teknis dan terverifikasi lokal.**

Fase 1 menyediakan infrastruktur nyata: database, autentikasi, hak akses tiga peran, pengelolaan sekolah/tahun ajaran/kelas/mapel/kompetensi, PWA, penyimpanan lokal, log audit, backup/restore, dan pengujian otomatis. Fase 2 menambahkan materi & unggah berkas, bank soal 10 tipe, asesmen dengan acak/autosave/lanjut mengerjakan, penilaian objektif otomatis, koreksi uraian oleh guru, catatan belajar, analitik berbasis data nyata, serta impor siswa CSV/XLSX. Fase 3 menambahkan profil penguasaan berbasis Bayesian Knowledge Tracing (BKT), latihan adaptif, analisis celah belajar, rekomendasi remedial, dan evaluasi yang jujur. Fase 4 menambahkan pengelolaan penyedia AI, router dengan fallback dan anggaran, AI Tutor yang memakai profil siswa sendiri, RAG dengan sitasi, serta generator soal/materi berupa draf guru. Fase 5 menambahkan filter periode/kelas/mapel/kompetensi/siswa, grafik perkembangan dari data nyata, profil per siswa, dan ekspor Excel/PDF server-side. Fase 6 menambahkan sinkronisasi dua arah dengan konflik awet, rotasi kunci sesi, backup terenkripsi, retensi/penghapusan data, health/metrik, serta kesiapan PostgreSQL dan HTTPS. Prediksi dropout **tetap tidak diaktifkan** karena belum ada dataset tervalidasi.

> Fase 6 dinyatakan selesai secara teknis setelah 53 pengujian otomatis, probe API langsung Fase 1–6, instalasi bersih, build/audit frontend, dan verifikasi browser lokal lulus. Jawaban generatif live sudah diverifikasi memakai model Ollama lokal yang ditemukan lewat API penyedia (`qwen2.5:7b`), bukan ID model tebakan atau kunci cloud. Uji coba dengan guru/siswa sekolah nyata, penyedia AI cloud, dan lingkungan produksi tetap terpisah dan belum diklaim selesai.

## 1. Hasil audit proyek awal

Folder proyek `E:\VIBE CODING\open19` awalnya **kosong** (0 file). Tidak ada kode lama yang dipertahankan atau dimodifikasi. Seluruh struktur dibuat baru dengan asumsi:

- Deployment awal: satu komputer/server sekolah (SQLite), dengan jalur migrasi ke PostgreSQL.
- Akses awal: jaringan lokal sekolah; cookie `SameSite=Lax`, `Secure` dimatikan untuk HTTP lokal (aktifkan saat HTTPS produksi).
- Bahasa antarmuka: Bahasa Indonesia.
- Semua waktu disimpan dalam UTC.
- Berkas unggahan Fase 2 disimpan lokal di `data/uploads/`; ekstensi yang diizinkan: `.pdf`, `.txt`, `.md`, `.docx`, `.pptx`, `.png`, `.jpg`, `.jpeg`, `.webp`.

## 2. Arsitektur (ringkas)

```
open19/
├── backend/                 FastAPI + SQLAlchemy 2.x + Alembic
│   ├── app/core/            konfigurasi, keamanan, auth/CSRF, rate limit
│   ├── app/db/              engine, sesi, inisialisasi
│   ├── app/models/          39 tabel aplikasi (+ alembic_version): identitas, akademik, asesmen, intelijen, AI, analitik, operasional
│   ├── app/schemas/         validasi Pydantic v2 (learning, intelligence, ai, sync, privacy)
│   ├── app/api/v1/          endpoint REST (/api/v1/... termasuk /dashboard, /sync, /privacy, /ops, /learning, /intelligence, /ai)
│   ├── app/services/        seed demo, audit, grading, intelligence, dropout, ai_client/router/rag/tutor/generator, dashboard/export, retention/secrets/backup_crypto/health
│   ├── migrations/          revisi Alembic (head: b6d1f7a9c2e4)
│   └── tests/               pytest + TestClient (53 pengujian: Fase 1–4 + 2 Fase 5 + 6 Fase 6 + regresi seed)
├── frontend/                React 18 + TypeScript + Vite + Tailwind + React Router 7
│   ├── public/              manifest PWA, service worker, ikon PNG
│   └── src/                 API client, AuthContext, IndexedDB, halaman per peran
│       ├── pages/learning/  materi, soal, asesmen, koreksi, analitik, catatan, impor, hasil
│       ├── pages/intelligence/ penguasaan, latihan adaptif, celah belajar, evaluasi, mesin
│       ├── pages/ai/        penyedia, anggaran, dokumen, tanya dokumen, tutor, generator
│       └── pages/admin/     pengguna, kelas, mapel, pengaturan, operasional & privasi
├── scripts/                 instalasi & menjalankan (Windows .bat), backup/restore terenkripsi,
│                            smoke_test.py, probe Fase 2–6, fase3_clean_check.py, pembuat ikon
├── data/                    SQLite + kredensial demo + uploads + contoh CSV (diabaikan git)
├── docs/                    arsitektur, pengujian Fase 1–6, deployment, privasi, roadmap
├── requirements.txt
└── .env.example
```

Detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## 3. Instalasi untuk pengguna pemula Windows

### 3.1 Siapkan alat

1. Pasang **Python 3.11 atau lebih baru** dari <https://www.python.org/downloads/>.
   - Saat instalasi, **centang “Add Python to PATH”**.
2. Pasang **Node.js 20 atau lebih baru** (disarankan versi LTS) dari <https://nodejs.org/>.
3. Ekstrak folder proyek ke lokasi yang mudah, misalnya `C:\pli`.

### 3.2 Instalasi otomatis

Klik dua kali `scripts\setup-windows.bat`.

Skrip akan:

- membuat virtual environment Python (`.venv`),
- menginstal semua paket Python dan npm,
- menyalin `.env.example` menjadi `.env`,
- membuat database `data\pli.db`,
- menerapkan migrasi sampai `head`,
- membuat akun demo dengan **password acak** yang tersimpan di `data\demo_credentials.txt`.

> **Penting:** sebelum aplikasi dipakai banyak orang, ubah `PLI_SECRET_KEY` di `.env` dengan string acak panjang, dan set `PLI_DEMO_MODE=false`, `PLI_COOKIE_SECURE=true` bila memakai HTTPS.

### 3.3 Menjalankan

Klik dua kali `scripts\run-all.bat`. Dua jendela terminal akan terbuka:

- Backend: <http://127.0.0.1:8000> (dokumentasi API: `/docs`)
- Frontend: <http://localhost:5173>

Buka `http://localhost:5173` di browser. Masukkan salah satu akun dari `data\demo_credentials.txt`.

Untuk menghentikan: tutup kedua jendela terminal tersebut.

### 3.4 Cara lain (terminal)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
cd backend
python -m alembic upgrade head
python -m app.db.init_db
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal kedua:

```bat
cd frontend
npm install
npm run dev
```

## 4. Akun demo

Dibuat otomatis oleh `python -m app.db.init_db`:

| Username | Peran | Keterangan |
|---|---|---|
| `admin` | Administrator | Mengelola sekolah, akun, kelas, mapel, materi, soal, asesmen |
| `guru1` | Guru | Hanya kelas XII RPL 1; mengoreksi, memberi catatan, melihat analitik |
| `siswa1`, `siswa2` | Siswa | Hanya melihat kelas, materi, asesmen, hasil, dan catatan sendiri |

Password **dibuat acak** setiap database baru dan ditulis ke `data/demo_credentials.txt`. Password ini hanya untuk pengujian lokal, bukan password produksi. Semua akun demo menampilkan pesan “harus mengganti password” pada login pertama.

Saat verifikasi Fase 2 lokal juga dibuat satu akun hasil impor `siswa_import` (password ada di `data/fase2_import_demo.csv`) dan contoh materi/soal/asesmen. Hapus atau ganti sebelum pemakaian produksi.

## 5. Yang benar-benar berfungsi di Fase 1

### Administrator

- [x] Melihat dan mengubah identitas sekolah
- [x] Membuat tahun ajaran dan semester (validasi tanggal)
- [x] Membuat, mengubah, menonaktifkan pengguna; reset password
- [x] Membuat dan mengubah kelas beserta anggota siswa & guru pengampu
- [x] Membuat mata pelajaran dan kompetensi
- [x] Melihat log audit (siapa melakukan apa, kapan, dari IP mana)
- [x] Melihat statistik jumlah pengguna, guru, siswa, kelas

### Guru

- [x] Login di HP/laptop
- [x] Melihat hanya kelas yang menjadi tanggung jawabnya
- [x] Melihat daftar siswa pada kelas yang diampu

### Siswa

- [x] Login di HP/laptop
- [x] Melihat hanya kelas tempat ia terdaftar
- [x] Melihat ringkasan jumlah kompetensi yang dipantau

### Umum

- [x] Session cookie httpOnly + CSRF token untuk semua penulisan data
- [x] Password di-hash dengan Argon2id; penguncian akun setelah 5 kegagalan
- [x] Pembatasan laju login (10 percobaan / 5 menit per IP)
- [x] Validasi input di backend (Pydantic) dan frontend
- [x] Pesan sukses/gagal pada setiap aksi penting (toast)
- [x] PWA: manifest, service worker, ikon 192/512/maskable, install prompt
- [x] Offline fallback untuk navigasi; data konteks disimpan di IndexedDB
- [x] Status online/offline dan antrean jawaban lokal di IndexedDB
- [x] Backup/restore SQLite + checksum SHA-256
- [x] Migrasi Alembic (`alembic upgrade head`)
- [x] Responsif: sidebar desktop, bottom navigation di layar kecil, tombol min. 44 px

## 6. Yang benar-benar berfungsi di Fase 2

### Guru & Administrator

- [x] Membuat, mengubah, menghapus, dan mempublikasikan materi; unggah berkas dengan validasi ekstensi/ukuran
- [x] Bank soal 10 tipe: pilihan ganda, pilihan ganda kompleks, benar/salah, menjodohkan, isian singkat, melengkapi, uraian, uraian bertahap, bergambar, proyek
- [x] Validasi kunci jawaban/rubrik di server; kunci disembunyikan dari siswa sebelum pengumpulan
- [x] Menyusun asesmen dari bank soal: durasi, jendela waktu, acak soal/opsi, bobot, izinkan lanjut, izinkan offline, publikasi
- [x] Edit asesmen mempertahankan soal yang sudah dipilih (`question_ids`)
- [x] Mengoreksi jawaban uraian/proyek; nilai dihitung ulang otomatis setelah koreksi
- [x] Melihat analitik kelas: jumlah siswa/upaya, rata-rata, lulus (≥70), kompetensi paling sulit, siswa perlu perhatian, dan bukti perhitungan
- [x] Mengirim catatan belajar (info/dorongan/perlu perhatian) hanya kepada siswa yang bersangkutan
- [x] Mengimpor siswa dari CSV/XLSX; duplikat username tidak ditimpa; password di-hash

### Siswa

- [x] Melihat materi yang dipublikasikan untuk kelasnya dan mengunduh berkas yang diizinkan
- [x] Memulai asesmen yang dipublikasikan, menjawab, berpindah soal, dan menyimpan otomatis
- [x] Melanjutkan upaya yang belum selesai bila diizinkan guru
- [x] Antre jawaban saat offline; sinkronisasi idempotent berdasarkan `client_id`
- [x] Konflik sinkronisasi dilaporkan; jawaban server tidak ditimpa diam-diam
- [x] Mengumpulkan jawaban; soal objektif dinilai otomatis, uraian menunggu guru
- [x] Melihat hanya hasil upayanya sendiri dan catatan dari gurunya; menandai catatan sudah dibaca

### Batasan yang disengaja

- Indikator anomali (fokus/halaman tersembunyi) hanya untuk ditinjau guru, **bukan** vonis kecurangan atau pengurangan nilai otomatis.
- Sinkronisasi Fase 2 bersifat satu arah (siswa → server) dengan rekonsiliasi konflik; sinkronisasi dua arah penuh ada di Fase 6.
- Kategori celah belajar berasal dari label guru; sistem tidak menebak kategori secara otomatis.

## 7. Yang benar-benar berfungsi di Fase 3

### Administrator

- [x] Melihat dan mengubah parameter BKT (`p_init`, `p_transit`, `p_slip`, `p_guess`, `mastery_threshold`) melalui halaman **Mesin Intelijen**
- [x] Memilih hitung ulang seluruh profil siswa setelah perubahan; perubahan tercatat di `engine_configs` dan log audit
- [x] Validasi server menolak parameter di luar rentang 0–1, `NaN`/`inf`, serta `p_slip + p_guess >= 1`

### Guru

- [x] Melihat profil penguasaan per kompetensi untuk semua siswa yang masih dalam cakupan kelasnya, beserta jumlah jawaban, akurasi, dan observasi BKT
- [x] Melihat analisis celah belajar berdasarkan kategori yang ia tetapkan pada soal
- [x] Meninjau indikator ketertinggalan sebagai **penunjuk**, bukan prediksi otomatis
- [x] Menyegarkan rekomendasi remedial dari profil penguasaan yang sebenarnya

### Siswa

- [x] Melihat hanya profil penguasaan dan rekomendasinya sendiri
- [x] Mengambil soal adaptif dari kompetensi dengan penguasaan terendah
- [x] Menjawab soal objektif tanpa menerima kunci jawaban, rubrik, atau kunci pencocokan
- [x] Mengirim jawaban secara idempoten dengan `client_id`; profil BKT diperbarui dari bukti yang dapat ditinjau

### Batasan yang disengaja

- **Tidak ada prediksi dropout aktif.** Endpoint `/intelligence/dropout-evaluation` mengembalikan `evaluasi_tidak_tersedia` sampai dataset berlabel dengan persetujuan, manifest tervalidasi, metrik precision/recall/F1, dan confusion matrix tersedia.
- BKT dihitung ulang dari awal setiap ada jawaban/koreksi baru sehingga idempoten dan aman setelah regrade.
- Soal `matching` tidak dipakai dalam latihan adaptif karena kunci pencocokannya tidak boleh dikirim ke siswa.
- Rekomendasi tidak menghakimi siswa; keputusan remedial tetap menjadi tanggung jawab guru.

## 8. Cara menguji

### 8.1 Otomatis

```bat
cd backend
python -m pytest
```

Hasil terakhir: **53 passed**. Pengujian Fase 4 memakai transport HTTP penyedia palsu untuk jalur tanpa model; jalur generatif live juga diuji terpisah lewat Ollama lokal yang modelnya ditemukan lewat API penyedia, bukan dengan kunci cloud. Fase 5/6 menguji filter/scoping, ekspor, konflik, retensi, rotasi, backup terenkripsi, health, dan RBAC.

```bat
cd ..
python scripts\fase3_clean_check.py
python scripts\smoke_test.py
python scripts\fase2_probe.py
python scripts\fase3_probe.py
python scripts\fase4_probe.py
python scripts\fase5_probe.py
python scripts\fase6_probe.py
cd frontend
npm run build
npm audit --audit-level=moderate
```

Hasil terakhir: **53 pengujian otomatis lulus**, instalasi bersih **semua pemeriksaan lulus** (head `b6d1f7a9c2e4`, 40 tabel termasuk `alembic_version`, 8 penyedia tanpa model hardcoded, tidak ada kunci mentah di tabel rotasi), smoke test Fase 1 **lulus**, probe Fase 2–6 **lulus**, build **berhasil**, audit **0 kerentanan**. Migrasi: `python -m alembic current` → `b6d1f7a9c2e4 (head)`. Jalankan keenam skrip probe **berurutan**; semuanya login beberapa peran sehingga bisa memicu rate limiter 10 login/5 menit bila digabung dengan banyak login browser.

Rincian: [`docs/FASE1_TESTING.md`](docs/FASE1_TESTING.md), [`docs/FASE2_TESTING.md`](docs/FASE2_TESTING.md), [`docs/FASE3_TESTING.md`](docs/FASE3_TESTING.md), [`docs/FASE4_TESTING.md`](docs/FASE4_TESTING.md), [`docs/FASE5_TESTING.md`](docs/FASE5_TESTING.md), [`docs/FASE6_TESTING.md`](docs/FASE6_TESTING.md), [`docs/FASE6_DEPLOYMENT.md`](docs/FASE6_DEPLOYMENT.md), dan [`docs/PRIVACY_CONSENT_RETENTION.md`](docs/PRIVACY_CONSENT_RETENTION.md).

### 8.2 Manual singkat Fase 1

1. Buka `http://localhost:5173`, login sebagai `admin`.
2. Buka **Pengaturan** → ubah nama sekolah → harus muncul pesan sukses.
3. Buka **Pengguna** → tambah siswa baru → muncul di daftar.
4. Buka **Kelas** → ubah anggota kelas → jumlah siswa berubah.
5. Logout, login sebagai `guru1` → hanya melihat kelas XII RPL 1; URL `/users` harus mengalihkan ke dashboard.
6. Logout, login sebagai `siswa1` → hanya melihat kelasnya sendiri.
7. Matikan koneksi/Wi-Fi → status berubah menjadi Offline, halaman yang sudah dibuka masih bisa ditampilkan.
8. Di Chrome/Edge, buka menu browser → **Install app** (jika tersedia) → aplikasi terbuka sebagai PWA.

### 8.3 Manual singkat Fase 2

1. Login `admin`/`guru1` → **Materi** → tambah materi dan unggah `data\fase2_upload_demo.txt` → materi muncul dengan tautan unduh.
2. **Soal** → buat satu pilihan ganda dengan tepat satu kunci, lalu satu uraian tanpa opsi → keduanya tersimpan.
3. **Asesmen** → buat asesmen, pilih kedua soal, centang publikasi → asesmen muncul; tombol **Ubah** membuka lagi 2 soal terpilih.
4. Logout → login `siswa1` → **Asesmen** → **Kerjakan** → isi uraian, pilih opsi benar, pindah soal, kumpulkan → muncul nilai dengan 1 otomatis dan 1 menunggu guru.
5. **Hasil** → riwayat hanya menampilkan upaya siswa tersebut.
6. Logout → login `guru1` → **Koreksi** → beri poin uraian → nilai gabungan berubah; **Analitik** menampilkan angka yang sama.
7. **Catatan** → kirim catatan dorongan; logout → login `siswa1` → **Catatan** → catatan tampil dan bisa ditandai dibaca.
8. **Impor** → unggah `data\fase2_import_demo.csv` ke kelas XII RPL 1 → hasil “Dibuat: 1”.

Langkah dan bukti verifikasi lengkap: [`docs/FASE2_TESTING.md`](docs/FASE2_TESTING.md).

### 8.4 Manual singkat Fase 3

1. Login `siswa1` → **Penguasaan** → profil menampilkan probabilitas BKT, jumlah jawaban, dan bukti perhitungan.
2. Tekan **Segarkan** pada rekomendasi → muncul toast jumlah rekomendasi yang dibuat.
3. **Latihan Adaptif** → **Ambil soal** → pilih jawaban → **Kirim jawaban** → kartu hasil menunjukkan poin, probabilitas sebelum/sesudah, dan status penguasaan.
4. Kirim jawaban yang sama lagi → muncul pesan bahwa jawaban sudah tercatat sebelumnya; tidak ada observasi baru.
5. Logout → login `guru1` → **Penguasaan** → pilih siswa untuk melihat profilnya; **Celah Belajar** → kategori berasal dari label soal; **Evaluasi** → status `evaluasi_tidak_tersedia` dan indikator berlabel `Prediksi: tidak`.
6. Logout → login `admin` → **Mesin Intelijen** → ubah salah satu parameter lalu **Simpan parameter** → muncul toast dan sumber berubah menjadi `Override sekolah`.

Langkah dan bukti verifikasi lengkap: [`docs/FASE3_TESTING.md`](docs/FASE3_TESTING.md).

### 8.5 Manual singkat Fase 4

1. Login `admin` → **Penyedia AI** → ubah batas token harian → **Simpan anggaran** → angka berubah setelah dimuat ulang.
2. Buka **Dokumen AI** → unggah TXT/MD/PDF/DOCX/PPTX, isi judul, klik **Indeks** → status muncul (`indexed` atau `indexed_lexical`).
3. **Generator AI** → buat draf → status tetap `draft`; hanya tombol **Setujui/Publikasikan** yang membuat konten tersedia bagi siswa.
4. **Tanya Dokumen** → ajukan pertanyaan sesuai isi dokumen → jawaban menyertakan sitasi; tanpa potongan relevan muncul `Data tidak tersedia`.
5. Logout → login `siswa1` → **AI Tutor** → kirim pertanyaan. Dengan model terverifikasi, jawaban sungguhan dari penyedia ditampilkan beserta riwayat percakapan siswa itu sendiri; tanpa model, aplikasi menampilkan alasan `belum tersedia`, bukan jawaban buatan.
6. Coba buka `/ai-providers` sebagai guru/siswa atau `/ai-tutor` sebagai guru → ProtectedRoute mengalihkan ke dashboard.

Status AI di dashboard diambil langsung dari `GET /ai/status`. Rincian dan batasan verifikasi: [`docs/FASE4_TESTING.md`](docs/FASE4_TESTING.md).

### 8.6 Manual singkat Fase 5

1. Login `guru1` → **Dashboard** → ubah periode/kelas/mapel/kompetensi/siswa → kartu dan dua grafik berubah sesuai data asesmen/BKT yang tersimpan.
2. Klik **Unduh Excel** dan **Unduh PDF** → berkas terunduh lewat API; toast sukses muncul. Buka berkas untuk melihat baris sesuai filter.
3. Buka **Perkembangan** → pilih siswa dalam kelas binaan → grafik nilai, tabel kompetensi, hasil, rekomendasi, dan catatan tampil.
4. Logout → login `siswa1` → **Perkembangan** → hanya profil sendiri yang muncul; filter siswa terkunci. Coba alamat profil siswa lain → ditolak.
5. Grafik kosong pada rentang tanggal tanpa data menampilkan pesan, bukan angka rekaan.

Rincian: [`docs/FASE5_TESTING.md`](docs/FASE5_TESTING.md).

### 8.7 Manual singkat Fase 6

1. Login `guru1` → **Sinkronisasi** → lihat strategi `client_updated_at` dan daftar konflik dalam cakupan kelas. Bila ada konflik, pilih **Tinjau & selesaikan**, tentukan server/klien, isi catatan, simpan → status berubah dan keputusan tercatat.
2. Logout → login `siswa1` → **Sinkronisasi** → hanya konflik sendiri, tanpa tombol resolusi.
3. Logout → login `admin` → **Operasional** → status layanan, kebijakan retensi, dan riwayat penghapusan terbaca.
4. Klik **Bersihkan data kedaluwarsa** → modal menolak bila ketikan bukan `BERSIHKAN`; dengan ketikan benar, API mengembalikan jumlah data yang dibersihkan.
5. Klik **Putar kunci sesi** → konfirmasi `ROTASI`. Hanya petunjuk kunci yang muncul; kunci mentah tidak pernah ditampilkan. Lakukan ini hanya di instalasi uji karena `.env` server berubah.
6. Permintaan/hapus siswa uji memakai ketikan `AJUKAN`/`HAPUS` dan menghasilkan sertifikat berbasis hash. Jangan lakukan pada data produksi tanpa persetujuan.
7. Buka `/api/health/live`, `/api/health/ready`, `/api/metrics` → respons aktif dengan header `X-Request-ID`; `/api/v1/ops/status` hanya untuk admin.

Rincian: [`docs/FASE6_TESTING.md`](docs/FASE6_TESTING.md).

## 9. Backup & restore

```bat
python scripts\backup.py
python scripts\restore.py backups\pli-YYYYMMDD-HHMMSS.db.enc
```

**Hentikan backend sebelum restore.** Backup baru dienkripsi dengan Fernet memakai `PLI_BACKUP_ENCRYPTION_KEY` dan disertai metadata `.meta.json` berisi checksum ciphertext. Restore menolak kunci salah, checksum tidak cocok, atau metadata hilang. Restore menyimpan salinan database lama sebagai `data/pli.before-restore.db`. Backup plaintext lama dengan `.sha256` masih dapat dipulihkan untuk migrasi. Simpan kunci backup terpisah dari berkas backup; backup juga mencakup `data/uploads` bila disalin manual bersama file database. Panduan server: [`docs/FASE6_DEPLOYMENT.md`](docs/FASE6_DEPLOYMENT.md).

## 10. Keamanan & privasi

- API key AI **tidak pernah** dikirim ke frontend; Fase 4 memakai nama environment variable server. Frontend hanya menerima `has_key` dan petunjuk terselubung, bukan nilai kunci. Tidak ada enkripsi kunci mentah karena tidak ada kunci yang disimpan di database.
- Tidak ada data siswa yang dikirim ke penyedia AI pada Fase 1–Fase 3: BKT dan adaptive engine dihitung lokal di backend. Fase 4 hanya mengirim konteks penguasaan siswa yang bersangkutan dan potongan dokumen yang diizinkan kepada penyedia aktif; administrator menentukan penyedia dan model yang dipakai.
- Kunci jawaban, rubrik, dan kunci pencocokan tidak dikirim kepada siswa sebelum upaya dikumpulkan atau saat latihan adaptif.
- Catatan guru hanya dapat dibaca oleh siswa penerima; siswa tidak bisa melihat catatan siswa lain atau profil BKT siswa lain.
- Parameter BKT disimpan di server, dapat diubah administrator, dan setiap perubahan tercatat di log audit.
- Indikator anomali, celah belajar, dan ketertinggalan bersifat advisory; tidak ada keputusan otomatis terhadap siswa.
- Berkas unggahan disimpan lokal dengan nama acak dan hanya ekstensi tertentu yang diterima; tidak ada eksekusi berkas.
- Tidak ada kamera, mikrofon, atau pengawasan invasif.
- Kunci sesi server dapat diputar; kunci lama hanya diverifikasi satu siklus. Kunci API AI dan kunci backup hanya ada di server, tidak di database atau frontend.
- Sinkronisasi dua arah mencatat konflik secara awet; guru/admin dapat memilih versi server/klien dan keputusan tercatat di log audit.
- Retensi membersihkan data sementara dengan konfirmasi admin; penghapusan siswa menghasilkan sertifikat hash dan log audit dipertahankan sebagai bukti.
- Backup database dienkripsi dengan checksum ciphertext; restore gagal bila kunci/checksum tidak valid.
- Kebijakan privasi, contoh informed consent, dan prosedur penghapusan: [`docs/PRIVACY_CONSENT_RETENTION.md`](docs/PRIVACY_CONSENT_RETENTION.md).

## 11. Rencana fase berikutnya

Lihat [`docs/ROADMAP.md`](docs/ROADMAP.md). Fase 1–6 sudah tersedia secara teknis; generatif live terverifikasi memakai instance Ollama lokal dan model yang ditemukan lewat API penyedia. Penyedia cloud tetap memerlukan kunci API server dan verifikasi administrator sesuai kebijakan sekolah; prediksi dropout tetap menunggu dataset berlabel tervalidasi. UAT sekolah dengan guru/siswa nyata dan deployment produksi belum dilakukan.

## 12. Keterbatasan yang sudah diketahui

- Rate limiter login berbasis memori proses: hanya efektif untuk satu proses backend; untuk multi-worker produksi diperlukan pembatas laju bersama di reverse proxy.
- Belum ada prediksi dropout tervalidasi. Ekspor Excel/PDF sudah tersedia dari data Fase 2/Fase 3.
- Jawaban generatif live baru teruji dengan Ollama lokal (`qwen2.5:7b`, ditemukan lewat `/api/tags`); penyedia cloud belum teruji karena tidak ada kunci API. Tanpa penyedia/model terverifikasi, status aplikasi secara jujur melaporkan `belum tersedia`. Generasi pada CPU lokal ≈107 detik; timeout penyedia lokal 180 detik.
- BKT memakai satu set parameter global per sekolah; belum ada kalibrasi per siswa, per mapel, atau per kompetensi.
- Konflik sinkronisasi tidak diselesaikan otomatis: guru/admin harus memilih versi server/klien. Versi klien hanya dapat diterapkan sebelum upaya dikumpulkan.
- Rotasi kunci mempertahankan kunci lama satu siklus agar sesi aktif tidak langsung putus; `PLI_SECRET_KEY_PREVIOUS` perlu dibersihkan setelah masa transisi.
- Penghapusan data mengikuti permintaan/eksekusi eksplisit admin; log audit sengaja dipertahankan.
- PostgreSQL/SSL/monitoring produksi sudah disiapkan konfigurasi dan dokumentasinya, tetapi belum diuji pada server sekolah nyata.
- Restore database mengharuskan backend dihentikan; kunci backup yang hilang membuat berkas tidak dapat dipulihkan.
- Instalasi PWA bergantung pada dukungan browser/OS; tidak semua browser menyediakan prompt install yang sama.
- UAT dengan guru/siswa sekolah nyata masih menunggu pengguna.
