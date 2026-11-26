# Panduan verifikasi Fase 4 — AI Provider, Tutor, RAG, dan Generator

Dokumen ini membuktikan bahwa Fase 4 berjalan sebagai fitur nyata, bukan prototipe statis. Semua perintah dijalankan dari folder proyek `E:\VIBE CODING\open19` kecuali dinyatakan lain.

## 1. Prasyarat dan keadaan penyedia

1. Selesaikan instalasi sampai Fase 3 sesuai `README.md`.
2. Terapkan migrasi Fase 4:

```bat
cd backend
python -m alembic upgrade head
python -m alembic current
```

Hasil terverifikasi: `f4a6d8b1c3e7 (head)`.

3. Jalankan seed sekali lagi pada database yang sudah ada agar penyedia baru ditambahkan tanpa menimpa konfigurasi administrator:

```bat
python -m app.db.init_db
```

Pada database lokal hasilnya: `Seed: {'status': 'already_seeded', 'providers_added': '4'}`. Seed tidak membuat ID model. Administrator harus melakukan discovery atau verifikasi model terlebih dahulu.

4. Jalankan backend dan frontend:

```bat
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bat
cd frontend
npm run dev
```

> **Keadaan pengujian:** tidak ada kunci API penyedia atau instance Ollama tervalidasi pada lingkungan ini. Karena itu perilaku generatif diuji dengan transport HTTP palsu di pytest, sedangkan server langsung diuji untuk memastikan ia **menolak/jujur tidak tersedia** bila tidak ada model aktif. Tidak ada jawaban AI statis yang dipakai sebagai pengganti.

## 2. Pengujian otomatis backend

```bat
cd backend
python -m pytest --disable-warnings -q
```

Hasil terverifikasi: **45 passed** (10 Fase 1, 11 Fase 2, 12 Fase 3, 10 Fase 4 termasuk regresi reject/validasi draf/JSON mode, 2 regresi seed).

Delapan pengujian Fase 4 (`tests/test_ai.py`) mencakup:

- status jujur bila belum ada penyedia aktif/model terverifikasi;
- katalog adapter dan masking kunci: frontend hanya melihat nama env variable dan petunjuk terselubung;
- pembatasan peran administrator pada konfigurasi penyedia/model;
- fallback penyedia, pencatatan dua percobaan, anggaran token/biaya, dan alasan kegagalan;
- unggah/indeks TXT, potongan teks, sitasi, serta `Data tidak tersedia` bila tidak ada potongan relevan;
- AI Tutor khusus siswa, idempotent per `client_id`, dan prompt berbasis profil penguasaan siswa itu sendiri;
- draf generator tetap privat sampai guru menyetujui; publikasi membuat `Question`/`LearningMaterial` hanya lewat `approve(publish=True)`;
- tidak ada kunci API mentah pada payload frontend.

Satu regresi tambahan memastikan peningkatan database yang sudah terisi menambah penyedia yang hilang tanpa menimpa berkas kredensial demo.

## 3. Instalasi bersih

```bat
python scripts\fase3_clean_check.py
```

Hasil terverifikasi:

```text
DB_VERSION= f4a6d8b1c3e7
TABLES= 37
USERS= 4
PROVIDERS= 8
DB_VERSION= True
USERS= True
ADAPTIVE_PRACTICES= True
ENGINE_CONFIGS= True
QUESTION_GAP_CATEGORY= True
BKT_EVIDENCE_ID= True
AI_PROVIDER_MODELS= True
GENERATED_CONTENTS= True
AI_PROVIDER_SCHOOL_SCOPE= True
AI_USAGE_SCHOOL_SCOPE= True
TUTOR_CLIENT_ID= True
SEEDED_PROVIDERS= True
NO_HARDCODED_MODELS= True
TEMP_CREDENTIALS= True
CANONICAL_CREDENTIALS_UNCHANGED= True
```

`TABLES= 37` sudah termasuk `alembic_version`, sehingga ada 36 tabel aplikasi. `ai_provider_models` sengaja kosong: tidak ada model yang dibundling atau ditebak.

## 4. Probe API langsung

Jalankan **berurutan** untuk menghindari pembatas laju login 10 percobaan/5 menit per IP:

```bat
python scripts\smoke_test.py
python scripts\fase2_probe.py
python scripts\fase3_probe.py
python scripts\fase4_probe.py
```

Jika probe keempat perlu diulang dalam waktu singkat, restart backend untuk mengosongkan pembatas laju proses. Hasil terakhir:

- `smoke_test.py`: semua pemeriksaan auth, RBAC, CSRF, dan sesi lulus.
- `fase2_probe.py`: 5 pemeriksaan lulus.
- `fase3_probe.py`: 11 pemeriksaan lulus.
- `fase4_probe.py`: 28 pemeriksaan lulus:

```text
[OK  ] Kredensial demo lengkap
[OK  ] Endpoint Fase 4 terdaftar
[OK  ] Path inti AI tersedia
[OK  ] Katalog 8 adapter
[OK  ] Katalog tidak membocorkan kunci
[OK  ] Status AI jujur sesuai inventaris
[OK  ] Delapan penyedia hasil seed
[OK  ] Model penyedia berasal dari inventaris
[OK  ] Frontend hanya menerima referensi kunci
[OK  ] Inventaris model memiliki jejak verifikasi/discovery
[OK  ] Anggaran terbaca dari server
[OK  ] Catatan pemakaian terbaca
[OK  ] Guru membaca pustaka dokumen
[OK  ] Kompetensi untuk generator tersedia
[OK  ] Generator gagal jujur pada data invalid
[OK  ] Draf palsu tidak dibuat
[OK  ] Jumlah draf tidak berubah
[OK  ] CSRF wajib pada generator
[OK  ] Siswa hanya membaca tutor sendiri
[OK  ] Guru tidak bisa masuk tutor siswa
[OK  ] Siswa tidak bisa membaca dokumen guru
[OK  ] Siswa tidak bisa membaca draf guru
[OK  ] Percakapan siswa lain tidak dapat diakses
[OK  ] RAG menjawab lewat API
[OK  ] RAG mengakui data tidak tersedia
[OK  ] Tutor menolak input kosong
[OK  ] Tutor tidak mengarang jawaban
[OK  ] CSRF wajib pada tutor
```

Probe juga memastikan permintaan tulis tanpa `X-CSRF-Token` ditolak 403, siswa tidak bisa memasuki endpoint guru, dan guru tidak bisa memasuki tutor siswa.

## 5. Alur antarmuka yang tersedia

Halaman Fase 4 Terdaftar di `src/App.tsx` dan tautannya di `AppShell`:

| Peran | Halaman | Menyalur |
|---|---|---|
| Administrator | **Penyedia AI** (`/ai-providers`) | `GET /ai/catalog`, `GET/PUT /ai/budget`, `GET/PATCH /ai/providers`, discovery, verifikasi model, uji koneksi, `GET /ai/usage` |
| Administrator, Guru | **Dokumen AI** (`/ai-documents`) | unggah multipart, indeks, hapus dokumen |
| Administrator, Guru | **Generator AI** (`/ai-generator`) | daftar kompetensi sekolah, buat draf, setujui, publikasikan, tolak |
| Semua peran | **Tanya Dokumen** (`/ai-ask`) | `POST /ai/rag/ask` dengan sitasi dan bukti pencarian |
| Siswa | **AI Tutor** (`/ai-tutor`) | daftar percakapan, `POST /ai/tutor/chat` dengan `client_id`, riwayat pesan |

`DashboardPage` mengambil `GET /ai/status` sungguhan dan menampilkan jumlah penyedia/model serta sisa token; teks status berubah bila administrator belum memverifikasi model.

### 5.1 Pemeriksaan manual browser sungguhan (sudah dijalankan)

Alur berikut dijalankan di browser sungguhan pada `http://localhost:5173` dengan backend dan Ollama lokal berjalan:

1. Login `admin` → **Penyedia AI** → ubah batas token harian `50000` ↔ `60000` → **Simpan anggaran** → toast sukses; `GET /ai/budget` mengembalikan nilai terbaru. Nilai dikembalikan ke `50000` setelah uji.
2. **Temukan model** pada `Ollama (lokal)` menemukan dua model dari `GET /api/tags` (`llama3:latest`, `qwen2.5:7b`). Model dipilih administrator lewat API/UI, bukan hardcoded. `qwen2.5:7b` dipakai untuk uji generatif karena `llama3:latest` berhenti dengan `token repeat limit` pada prompt generator. Timeout penyedia lokal dinaikkan menjadi `180` detik melalui **Ubah**; ini konfigurasi server nyata, bukan fallback diam-diam.
3. Login `guru1` → **Dokumen AI** → unggah `data\fase2_upload_demo.txt` dengan judul `Fotosintesis — uji RAG guru` → **Indeks** → status `indexed_lexical` dengan satu potongan (Ollama mengembalikan `501` untuk `/api/embed`, sehingga aplikasi jujur memakai retrieval leksikal). **Tanya Dokumen** menampilkan jawaban dan sitasi `[1] Fotosintesis — uji RAG guru · bagian 1 · skor 0.492366`. Pertanyaan tanpa potongan relevan menampilkan status `data_tidak_tersedia` dan pesan `Data tidak tersedia dalam dokumen yang diizinkan untuk akun ini.`
4. **Generator AI** sebagai guru: pilih mapel Matematika, topik `Fungsi kuadrat dan grafiknya`, klik **Buat draf** → toast `Draf question dibuat … Draf belum dipublikasikan`; status awal `draft`. Tombol **Setujui** mengubah status menjadi `approved` tanpa publikasi. Draf admin tidak terlihat di daftar guru (scoping `created_by`).
5. Live API sebagai guru juga memverifikasi: draf materi dapat dipublikasikan setelah **Publikasikan** (`published`, `published_ref_id` ada) dan draf baru dapat **Tolak** (`rejected`). Sebelum perbaikan, endpoint tolak salah menolak draf baru karena status diubah sebelum pengecekan; sekarang draf baru ditolak dan draf yang sudah ditinjau tetap ditolak dengan alasan yang benar.
6. Login `siswa1` → **AI Tutor** → kirim `Jelaskan singkat apa itu persamaan kuadrat.` → jawaban sungguhan dari `qwen2.5:7b` muncul di percakapan siswa itu sendiri; `POST /ai/tutor/chat` dan `GET /ai/tutor/conversations/{id}` keduanya `200`. Tanpa model terverifikasi, jalur yang sama sudah diuji lewat transport palsu mengembalikan alasan `belum tersedia`.
7. `DashboardPage` menampilkan status live `Layanan AI: siap digunakan`, `1 penyedia aktif · 2 model terverifikasi`, dan sisa token harian. Error koneksi sesekali muncul hanya saat backend baru direstart; setelah reload data dan status kembali normal.
8. ProtectedRoute terverifikasi: `/ai-providers` sebagai siswa/guru dialihkan ke dashboard, `/ai-tutor` sebagai guru dialihkan ke dashboard. Tidak ada halaman AI admin yang terbuka untuk peran lain.

## 6. Build frontend dan audit dependensi

```bat
cd frontend
npm run build
npm audit --audit-level=moderate
```

Hasil terverifikasi: TypeScript + Vite berhasil membangun 77 modul (bundel JS 349,36 kB / 99,66 kB gzip) dan `found 0 vulnerabilities`.

## 7. Batasan yang tetap dijaga

- Tidak ada kunci API di browser. Field yang dikirim frontend hanyalah **nama** environment variable server; respons hanya berisi `has_key` dan petunjuk terselubung.
- Tidak ada ID model hardcoded. Model masuk ke inventaris hanya dari API penyedia (`discover`) atau verifikasi eksplisit administrator.
- Tanpa penyedia aktif + model enabled, tutor/RAG/generator mengembalikan alasan nyata; generator tidak membuat draf palsu.
- Biaya dilaporkan `unknown` bila administrator belum mengisi harga token. Anggaran dihitung dari catatan pemakaian nyata.
- RAG memakai embedding bila tersedia; bila tidak, retrieval leksikal dipakai dan diberi label `indexed_lexical`/`lexical`. Tidak ada klaim semantic search tanpa embedding model.
- Hasil generator selalu berupa draf guru; tidak ada publikasi otomatis.
- Prediksi dropout tetap tidak aktif sampai dataset tervalidasi tersedia.
- Generator meminta Ollama memakai `format: json` hanya untuk pembuatan draf, bukan untuk tutor/RAG; draf tanpa judul/isi/opsi yang sah ditolak, jadi tidak ada draf kosong yang dipaksakan.
- Verifikasi browser Fase 4 sudah dijalankan, tetapi uji coba terbatas dengan guru sekolah masih tertunda, jadi status “selesai” di sini tetap berarti verifikasi teknis lokal.
