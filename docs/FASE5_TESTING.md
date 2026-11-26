# Fase 5 — Pengujian Analitik, Grafik, Profil, dan Ekspor

Fase 5 tidak membuat angka contoh. Semua nilai berasal dari `assessment_results`, `student_answers`, `student_attempts`, `bkt_history`, `student_competency_mastery`, rekomendasi, dan catatan yang benar-benar tersimpan. Filter dan cakupan dihitung di server, bukan di peramban.

## 1. Endpoint yang diuji

| Metode | Path | Fungsi |
|---|---|---|
| GET | `/api/v1/dashboard/filters` | Daftar periode, kelas, mapel, kompetensi, dan siswa yang **boleh dilihat oleh akun yang login** |
| GET | `/api/v1/dashboard/overview` | Ringkasan plus deret nilai dan penguasaan harian |
| GET | `/api/v1/dashboard/progress` | Deret nilai/BKT dan jumlah bukti untuk filter aktif |
| GET | `/api/v1/dashboard/students/{student_id}/profile` | Profil per siswa: penguasaan, hasil, rekomendasi, catatan, sumber bukti |
| GET | `/api/v1/dashboard/export?format=xlsx\|pdf` | Berkas yang dibuat server-side dari data yang sama dengan filter |

Filter yang didukung: `period=7d|30d|90d|all|custom`, `date_from`, `date_to`, `class_id`, `subject_id`, `competency_id`, `student_id`.

## 2. Pengujian otomatis

Dari folder `backend`:

```bat
python -m pytest tests/test_dashboard.py -q
```

Yang diverifikasi:

1. Administrator, guru, dan siswa menerima daftar filter yang berbeda sesuai cakupannya.
2. Guru hanya menerima kelas yang diampunya; siswa hanya menerima dirinya sendiri.
3. `overview.result_count` sama dengan `progress.result_count` untuk filter yang identik.
4. Grafik nilai dan BKT berisi angka dari hasil asesmen/observasi nyata.
5. Filter rentang `2001-01-01` sampai `2001-01-02` menghasilkan `result_count == 0` (bukan data diam).
6. Profil siswa memuat identitas, kompetensi, hasil, rekomendasi, catatan, dan `evidence`.
7. Ekspor XLSX diawali tanda `PK` dan PDF diawali `%PDF`, keduanya dikirim sebagai lampiran.
8. Siswa mendapat `403`/`404` saat meminta profil siswa lain atau mengekspor dengan `student_id` orang lain.

## 3. Probe langsung

Dengan backend berjalan dan kredensial demo tersedia:

```bat
python scripts\fase5_probe.py
```

Probe hanya membaca data. Ia memeriksa keberadaan kelima endpoint di `openapi.json`, konsistensi angka, penyaringan tanggal, tanda tangan berkas XLSX/PDF, dan penolakan akses lintas siswa. Probe tidak mengubah data dan tidak memanggil penyedia AI.

## 4. Verifikasi antarmuka

Frontend memakai komponen `DashboardFilterBar` dan `Charts` (SVG tanpa library grafik tambahan). Halaman:

- **Dashboard** (`/`): filter, kartu statistik, dua grafik garis, ringkasan bukti, tombol ekspor Excel/PDF, dan status AI dari server.
- **Perkembangan** (`/progress`): pilih siswa dalam cakupan, grafik nilai dan penguasaan, tabel kompetensi/hasil, rekomendasi, catatan, serta tombol ekspor.

Unduhan memakai `apiDownload(...)` dengan cookie sesi dan CSRF yang sama seperti API lain. Toast menampilkan keberhasilan atau pesan error dari server; tidak ada tombol yang hanya berubah tampilan tanpa memanggil API.

```bat
cd frontend
npm run build
npm audit --audit-level=moderate
```

## 5. Batasan yang jujur

- Grafik menampilkan data historis, bukan prediksi masa depan.
- `mastery_percent` adalah probabilitas BKT yang diterjemahkan ke persentase; status kompetensi adalah indikator peninjauan guru.
- Teks profil menyatakan secara eksplisit bahwa ini **bukan prediksi dropout**. Prediksi tetap tidak aktif tanpa dataset berlabel tervalidasi.
- Jika tidak ada hasil asesmen pada rentang filter, grafik menampilkan pesan kosong dan ekspor tetap menghasilkan berkas berisi penjelasan tersebut.
- Semua angka dibatasi oleh cakupan sekolah/kelas; administrator tidak dapat melihat sekolah lain dalam instalasi multi-tenant di masa depan karena query selalu memakai `school_id` akun.
