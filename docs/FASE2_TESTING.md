# Protokol Pengujian Fase 2 — Pembelajaran

Dokumen ini mencatat bukti bahwa Fase 2 **benar-benar dijalankan dan diuji**, bukan sekadar tampilan statis. Semua angka di bawah berasal dari database lokal proyek ini pada saat verifikasi.

## A. Perintah otomatis dan hasil terakhir

Jalankan dari root proyek, dengan backend sudah berjalan di `127.0.0.1:8000` untuk probe/smoke:

```bat
cd backend
python -m pytest
python -m alembic current
cd ..
python scripts\fase2_probe.py
python scripts\smoke_test.py
cd frontend
npm run build
npm audit --audit-level=moderate
```

| Perintah | Hasil yang diamati |
|---|---|
| `python -m pytest` dari `backend` | `21 passed, 1 warning in 6.02s`. Warning hanya `StarletteDeprecationWarning` dari `fastapi.testclient` tentang `httpx2`; bukan kegagalan aplikasi. |
| `python -m alembic current` dari `backend` | `e1c9acd1e994 (head)` |
| Instalasi bersih pada database kosong sementara: `python -m alembic upgrade head` lalu `python -m app.db.init_db` | Migrasi `e1f2f3696565 → e1c9acd1e994` berhasil; seed 4 akun; `DB_VERSION=e1c9acd1e994 TABLES=33 USERS=4 STUDENT_NOTES=True` (33 termasuk tabel `alembic_version`, jadi 32 tabel aplikasi). Ini membuktikan `scripts\setup-windows.bat` menghasilkan database yang sudah bermigrasi sebelum seed. |
| `python scripts\fase2_probe.py` | 5 baris `OK`: 19 jalur `/api/v1/learning/*` terdaftar; admin/guru/siswa baca 200; tulis tanpa sesi ditolak 401; bank soal siswa ditolak 403; `AssessmentOut.question_ids` hadir. |
| `python scripts\smoke_test.py` | Semua pemeriksaan Fase 1 lulus (login 3 peran, RBAC, CSRF, pencabutan sesi). |
| `npm run build` dari `frontend` | `✓ built in 4.29s`, output `assets/index-B5JGztn8.js` dan `assets/index-DgLiohPK.css`. |
| `npm audit --audit-level=moderate` | `found 0 vulnerabilities`. |

> **Catatan:** angka di atas adalah bukti pada saat Fase 2 selesai. Head Alembic saat ini sudah `c4f7a91d3e02` dan total pengujian 34 setelah Fase 3; lihat [`FASE3_TESTING.md`](FASE3_TESTING.md).
>
> Jalankan `smoke_test.py` dan `fase2_probe.py` **berurutan**, bukan bersamaan. Keduanya melakukan login untuk tiga peran; jika digabung dengan banyak login browser dalam jendela 5 menit, rate limiter login (10 percobaan/5 menit per IP) dapat mengembalikan 429. Saat itu terjadi, cukup mulai ulang backend untuk mengosongkan rate limiter memori, lalu jalankan ulang berurutan.

## B. Daftar pengujian otomatis

Fase 1 tetap 10 pengujian di `backend/tests/test_auth_rbac.py`. Fase 2 menambahkan 11 pengujian di `backend/tests/test_learning.py`:

| No | Pengujian | Yang dibuktikan |
|---|---|---|
| 1 | `test_question_validation_requires_single_correct_answer` | Pilihan ganda harus memiliki tepat satu kunci; rubrik isian singkat wajib ada |
| 2 | `test_objective_assessment_end_to_end` | Mulai upaya, simpan jawaban, kumpulkan, nilai objektif, dan hasil muncul |
| 3 | `test_sync_is_idempotent_and_reports_conflicts` | Pengiriman ulang tidak duplikat; `client_updated_at` lebih lama/sama tidak menimpa jawaban server |
| 4 | `test_anomaly_flags_are_advisory_only` | Flag fokus/halaman tersembunyi tidak menurunkan nilai |
| 5 | `test_essay_manual_grade_recalculates_result` | Koreksi guru uraian mengubah `AssessmentResult` |
| 6 | `test_student_cannot_access_other_student_attempt_or_teacher_assessment` | Siswa tidak bisa membuka upaya siswa lain atau asesmen guru |
| 7 | `test_notes_are_scoped_to_owner` | Catatan hanya tampil untuk guru pembuat dan siswa penerima |
| 8 | `test_analytics_uses_real_results_only` | Analitik dihitung dari `assessment_results + student_answers`, bukan data simulasi |
| 9 | `test_import_students_csv` | CSV membuat 2 siswa, duplikat `admin` dilewati, bukan ditimpa |
| 10 | `test_import_students_xlsx` | XLSX dibaca dengan `openpyxl`, siswa dibuat, `errors` kosong |
| 11 | `test_upload_rejects_unsupported_extension` | Ekstensi di luar daftar yang diizinkan ditolak |

## C. Verifikasi antarmuka browser sungguhan

Browser: tab aplikasi pada `http://localhost:5173`, backend `http://127.0.0.1:8000`. Kredensial dibaca dari `data/demo_credentials.txt`.

### C1. Admin — materi, soal, asesmen

1. Login sebagai `admin`.
2. **Materi** → buat materi `Pengantar operasi hitung` → materi tampil di daftar (POST 201).
3. **Materi** → buat materi `Materi dengan lampiran TXT` dan unggah `data\fase2_upload_demo.txt` → `POST /uploads` 200, kartu materi menampilkan tautan `Unduh ff219eab0e3746e88f3a452a0c8c491a.txt ↗` (nama penyimpanan acak dari server).
4. **Soal** → buat:
   - Pilihan ganda `Berapa hasil dari 2 + 3?` dengan kunci `B. 5` → tersimpan (POST 201).
   - Uraian `Jelaskan langkah-langkah penjumlahan bilangan bulat beserta contohnya.` tanpa opsi → awalnya gagal 422 karena draft menyisipkan opsi kosong. Setelah `QuestionIn.drop_unused_options` ditambahkan, create ulang berhasil dan soal tampil (POST 201).
5. **Asesmen** → buat `Latihan Fase 2 — Bilangan Bulat` untuk XII RPL 1, pilih kedua soal, centang **Publikasikan** → POST 201, asesmen tampil dengan `2 soal · 20 poin · 45 menit`.
6. Klik **Ubah** → modal menampilkan kembali **Terpilih: 2 soal**. Ini membuktikan perbaikan `AssessmentOut.question_ids` bekerja di UI.

### C2. Siswa — mengerjakan dan mengumpulkan

1. Logout, login sebagai `siswa1`.
2. Dashboard menampilkan modul Fase 2 sebagai aktif.
3. **Asesmen** → `Latihan Fase 2 — Bilangan Bulat` → **Kerjakan**.
4. Soal 1 (uraian) diisi; indikator berubah menjadi **1 jawaban tersimpan** (autosave nyata ke `PUT /attempts/{id}/sync`).
5. Berpindah ke soal 2, memilih `B.5`, lalu **Kumpulkan jawaban**.
6. Layar akhir: **Nilai 50%**, **Poin 10/20**, **Otomatis 1**, **Menunggu guru 1**.
7. **Hasil** → riwayat menampilkan hanya upaya siswa tersebut dengan status penilaian otomatis.

Catatan kecil saat verifikasi: tombol **Berikutnya** sempat tampak tidak berpindah karena ref browser sudah usang; setelah snapshot diambil ulang, tombol **Ke soal 2** berfungsi. Tidak ada perubahan kode yang diperlukan untuk kasus ini.

### C3. Guru — koreksi dan analitik

1. Logout, login sebagai `guru1`.
2. **Koreksi** → pilih upaya `Siswa Contoh / Latihan Fase 2` → jawaban uraian menampilkan teks siswa dan status **Menunggu koreksi**.
3. Isi **Poin (maks 10)** = `8` dan catatan `Penjelasan sudah tepat; perbaiki istilah penjumlahan bilangan berbeda tanda.` → **Simpan nilai** → toast sukses.
4. Segarkan: daftar koreksi menunjukkan **90%** (naik dari 50%). Ini membuktikan `PATCH /answers/{id}/grade` menghitung ulang `AssessmentResult`.
5. **Analitik** → `SISWA 2`, `UPAYA 1`, `RATA-RATA NILAI 90%`, `LULUS (≥70) 1`, blok `BUKTI PERHITUNGAN` dengan `source: assessment_results + student_answers` dan catatan “bukan vonis otomatis”.

### C4. Catatan belajar

1. Masih sebagai `guru1`, buka **Catatan**.
2. Pilih kelas XII RPL 1 → daftar siswa termuat → pilih `Siswa Contoh (siswa1)` → jenis `Dorongan` → judul `Pertahankan konsistensi belajar` → isi catatan → **Kirim catatan**.
3. Catatan tampil di daftar guru dengan waktu `25/11/2026, 05.22.44`.
4. Logout, login `siswa1` → **Catatan** → catatan yang sama tampil → klik **Tandai dibaca** → status “Baru” hilang.

Catatan kecil saat verifikasi: klik pertama pada tombol **Kirim catatan** salah mengenai tautan navigasi bawah karena ref browser usang setelah perubahan daftar siswa. Pengisian ulang dengan snapshot terbaru berhasil; geometri tombol tidak tertutup navigasi (`button.top=264`, `nav.top=512` pada viewport 800×573), sehingga tidak ada perbaikan layout yang diperlukan.

### C5. Impor siswa

1. Logout, login `guru1`, buka **Impor**.
2. Unggah `data\fase2_import_demo.csv` (satu baris: `siswa_import`) ke kelas XII RPL 1.
3. **Impor siswa** → **Hasil impor: Dibuat: 1, Ditambahkan: 0, Dilewati: 0**.
4. Jalur XLSX tidak diuji lewat browser, tetapi dibuktikan oleh `test_import_students_xlsx` dengan file `.xlsx` yang dibuat `openpyxl` pada saat pengujian.

## D. Alur yang sengaja tidak diklaim selesai

- BKT, adaptive question engine, learning gap analysis, prediksi ketertinggalan, AI Tutor, dan RAG (Fase 3–4).
- Sinkronisasi dua arah penuh dan resolusi konflik otomatis (Fase 6).
- Ekspor Excel/PDF dan dashboard lengkap (Fase 5).
- Uji coba terbatas dengan guru sekolah: belum dilakukan karena tidak ada pengguna eksternal.

## E. Data contoh yang dibuat saat verifikasi

Data berikut ada di database lokal `data/pli.db` dan dapat dihapus sebelum produksi:

- Materi: `Pengantar operasi hitung` dan `Materi dengan lampiran TXT` (lampiran `data/fase2_upload_demo.txt` tersimpan sebagai `ff219eab0e3746e88f3a452a0c8c491a.txt`)
- Soal: `Berapa hasil dari 2 + 3?` (PG, kunci B) dan `Jelaskan langkah-langkah penjumlahan bilangan bulat beserta contohnya.` (uraian)
- Asesmen: `Latihan Fase 2 — Bilangan Bulat` (XII RPL 1, dipublikasikan, 2 soal)
- Satu upaya `siswa1` dengan nilai akhir 90% setelah koreksi
- Satu catatan dorongan dari `guru1` untuk `siswa1`
- Akun `siswa_import` dari `data/fase2_import_demo.csv` (password lokal: `Impor-2026!Demo`)

File `data/fase2_import_demo.csv` berisi password plaintext untuk keperluan demonstrasi lokal. Jangan menyalin file ini ke lingkungan produksi.
