# Panduan verifikasi Fase 3 — Intelligence Engine

Dokumen ini membuktikan bahwa Fase 3 berjalan sebagai fitur nyata, bukan prototipe statis. Semua perintah dijalankan dari folder proyek `E:\VIBE CODING\open19` kecuali dinyatakan lain.

## 1. Prasyarat

1. Selesaikan instalasi Fase 1/Fase 2 sesuai `README.md`.
2. Pastikan Alembic sudah menerapkan semua migrasi:

```bat
cd backend
python -m alembic upgrade head
python -m alembic current
```

Hasil terverifikasi: `c4f7a91d3e02 (head)`.

3. Jalankan backend dan frontend:

```bat
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bat
cd frontend
npm run dev
```

## 2. Pengujian otomatis backend

```bat
cd backend
python -m pytest --disable-warnings
```

Hasil terverifikasi: **34 passed, 1 warning dalam 13,13 detik**. Warning berasal dari `starlette.testclient` dan bukan kegagalan aplikasi.

Cakupan Fase 3 (12 pengujian) mencakup:

- rumus BKT dan validasi parameter (termasuk penolakan `NaN`, `inf`, nilai di luar 0–1, dan `p_slip + p_guess >= 1`);
- replay dari awal bersifat idempoten dan dapat ditelusuri melalui `evidence_id`;
- penilaian ulang guru mengubah profil BKT secara konsisten;
- `mastery_percent` pada hasil asesmen berasal dari BKT, bukan nilai mentah;
- isolasi siswa/guru: siswa tidak bisa membaca profil atau rekomendasi siswa lain;
- pemilihan soal adaptif, pengiriman jawaban, dan idempotensi `client_id`;
- kategori celah belajar hanya memakai label guru;
- endpoint dropout menolak klaim prediksi tanpa dataset tervalidasi dan metrik uji;
- parameter BKT hanya dapat diubah administrator;
- penolakan permintaan tanpa sesi/CSRF.

Satu pengujian regresi tambahan memastikan berkas kredensial demo ditulis di samping database aktif. Ini mencegah pemeriksaan instalasi bersih pada database sementara menimpa `data/demo_credentials.txt` milik database utama.

## 3. Instalasi bersih

Skrip pemeriksaan membuat database SQLite sementara di luar `data/`, menjalankan Alembic, lalu menjalankan `init_db`:

```bat
python scripts\fase3_clean_check.py
```

Hasil terverifikasi:

```text
DB_VERSION= c4f7a91d3e02
TABLES= 35
USERS= 4
DB_VERSION= True
USERS= True
ADAPTIVE_PRACTICES= True
ENGINE_CONFIGS= True
QUESTION_GAP_CATEGORY= True
BKT_EVIDENCE_ID= True
TEMP_CREDENTIALS= True
CANONICAL_CREDENTIALS_UNCHANGED= True
```

Skrip juga memastikan berkas kredensial demo ditulis di samping database sementara dan checksum `data/demo_credentials.txt` tidak berubah. Setelah pemeriksaan, kredensial database utama tetap cocok (`admin`, `guru1`, `siswa1`, `siswa2` lolos verifikasi hash password).

## 4. Probe API langsung

Jalankan **berurutan** untuk menghindari pembatasan laju login 10 percobaan/5 menit per IP:

```bat
python scripts\smoke_test.py
python scripts\fase2_probe.py
python scripts\fase3_probe.py
```

Hasil terverifikasi:

- `smoke_test.py`: semua pemeriksaan auth, RBAC, CSRF, dan sesi lulus.
- `fase2_probe.py`: 5 pemeriksaan lulus (19 jalur pembelajaran terdaftar, akses baca per peran, penolakan tulis tanpa sesi).
- `fase3_probe.py`: 11 pemeriksaan lulus:

```text
[OK  ] Kredensial demo lengkap
[OK  ] Endpoint Fase 3 terdaftar
[OK  ] Path inti tersedia
[OK  ] Parameter BKT terbaca
[OK  ] Guru membaca profil penguasaan
[OK  ] Guru membaca celah belajar
[OK  ] Evaluasi dropout jujur (belum tersedia)
[OK  ] Siswa hanya melihat mode sendiri
[OK  ] Siswa ditolak mengakses siswa lain
[OK  ] Latihan adaptif memilih soal
[OK  ] CSRF wajib untuk penulisan
```

Putaran Fase 3 terdaftar pada OpenAPI: 8 path/9 operasi (`mastery`, `gaps`, `adaptive/next-question`, `adaptive/answer`, `recommendations`, `recommendations/refresh`, `dropout-evaluation`, `bkt-params`).

## 5. Alur browser sungguhan

Browser internal OpenCode dipakai pada `http://localhost:5173` dengan backend `http://127.0.0.1:8000`.

### Siswa (`siswa1`)

1. Login → navigasi bawah menampilkan **Latihan Adaptif** dan **Penguasaan**, tetapi tidak menampilkan menu koreksi/impor.
2. **Penguasaan** → halaman “Profil penguasaan siswa” menampilkan 1 kompetensi, probabilitas 20%, status `not started`, 0 observasi, dan bukti perhitungan dengan sumber `bkt_history + student_answers + adaptive_practices`.
3. Tombol **Segarkan** pada rekomendasi menghasilkan toast `Rekomendasi diperbarui: 1 butir` dan satu butir `remedial_focus` muncul.
4. **Latihan Adaptif** → tombol **Ambil soal** memanggil `POST /intelligence/adaptive/next-question`. Karena semua soal lama sudah pernah dikerjakan, muncul pesan jujur `Semua soal objektif yang tersedia sudah dikerjakan` dengan bukti `candidate_count: 0, excluded_count: 2`.
5. Satu soal pilihan ganda baru dibuat melalui API sebagai guru (terbit, bertanda `gap_category: konsep`). Setelah halaman dimuat ulang, **Ambil soal** menampilkan soal tersebut. Opsi hanya berisi teks; tidak ada `is_correct`, `match_key`, atau rubrik di browser.
6. Memilih opsi benar lalu **Kirim jawaban** menghasilkan `POST /api/v1/intelligence/adaptive/answer` status 200 dengan bukti:

```json
{"idempotent": false, "is_correct": true, "points_earned": 10.0,
 "mastery_before": 0.2, "mastery_after": 0.647059, "status": "developing"}
```

   UI menampilkan `Jawaban benar`, poin 10, `Sebelum 20%`, `Sesudah 65%`, status `developing`.
7. Mengirim ulang jawaban dengan `client_id` yang sama menghasilkan `idempotent: true`, toast `Jawaban sudah tercatat sebelumnya`, dan tidak menambah observasi baru.

### Guru (`guru1`)

1. **Penguasaan** → mode kelas menampilkan 3 siswa. `Siswa Contoh` memiliki 64,71% pada `BIN-K1` setelah latihan adaptif; siswa lain tetap 20% dengan 0 jawaban.
2. **Celah Belajar** → 3 siswa, 1 observasi, 1 kompetensi terdampak. `BIN-K1` memiliki skor celah 0,2604 dengan kategori dominan `Konsep` dari label guru, bukan tebakan otomatis.
3. **Evaluasi** → status `evaluasi_tidak_tersedia`, pesan `Belum ada dataset tervalidasi. Tidak ada model prediksi yang diaktifkan.`, empat persyaratan evaluasi, dan indikator peninjauan guru dengan `Prediksi: tidak`.
4. Tidak ada error konsol selain 401 yang diharapkan saat halaman login dimuat tanpa sesi.

### Administrator (`admin`)

1. Menu **Mesin Intelijen** tersedia di navigasi.
2. Halaman menampilkan lima parameter BKT, sumber `Default lingkungan` sebelum perubahan, definisi dari server, dan checkbox hitung ulang profil.
3. `PUT /api/v1/intelligence/bkt-params` dengan nilai yang sama dan `recompute: true` terverifikasi:

```json
{"params": {"p_init": 0.2, "p_transit": 0.25, "p_slip": 0.1,
            "p_guess": 0.2, "mastery_threshold": 0.8},
 "recomputed_students": 3}
```

   Setelah penyimpanan, sumber berubah menjadi `database_override`. Catatan: tab browser ditutup oleh aplikasi desktop sebelum tangkapan layar akhir, sehingga respons penyimpanan diverifikasi melalui API langsung; tampilan halaman dan kontrolnya sudah terverifikasi di browser.

## 6. Build frontend dan audit dependensi

```bat
cd frontend
npm run build
npm audit --audit-level=moderate
```

Hasil terverifikasi: build TypeScript + Vite berhasil (71 modul, bundel JS sekitar 318,84 kB / 92,40 kB gzip) dan `found 0 vulnerabilities`.

## 7. Batasan yang tetap dijaga

- **Tidak ada model dropout aktif.** Tanpa dataset berlabel dengan persetujuan, manifest `validated=true`, dan metrik precision/recall/F1 + confusion matrix pada data uji terpisah, endpoint hanya mengembalikan status evaluasi dan indikator advisory.
- BKT adalah model probabilistik transparan dengan parameter yang dapat diaudit, bukan klaim AI generatif.
- Soal `matching` sengaja tidak dipakai pada latihan adaptif karena sisi kunci jawabannya tidak boleh dikirim ke siswa.
- Rekomendasi dan celah belajar membantu guru memutuskan remedial; tidak ada keputusan otomatis terhadap siswa.
- Uji coba terbatas dengan guru sekolah belum dilakukan, jadi status “selesai” di sini berarti terverifikasi secara teknis lokal.
