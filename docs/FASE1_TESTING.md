# Protokol Pengujian Fase 1

## A. Pengujian otomatis

```bat
cd backend
python -m pytest -v
```

Daftar pengujian (`backend/tests/test_auth_rbac.py`):

| No | Pengujian | Harapan |
|---|---|---|
| 1 | `test_health` | `/api/health` mengembalikan `status: ok` |
| 2 | `test_login_me_and_logout` | Login → `/auth/me` → logout → `/auth/me` = 401 |
| 3 | `test_wrong_password_is_rejected` | Password salah = 401 |
| 4 | `test_csrf_required_for_writes` | POST tanpa header CSRF = 403 |
| 5 | `test_student_cannot_use_admin_endpoints` | Siswa = 403 pada endpoint admin & guru |
| 6 | `test_teacher_only_sees_assigned_classes` | Guru hanya melihat kelasnya; kelas lain = 403 |
| 7 | `test_student_only_sees_own_classes` | Siswa hanya melihat kelasnya sendiri |
| 8 | `test_admin_can_create_class_and_user` | User & kelas tersimpan, anggota terhubung, audit bertambah |
| 9 | `test_validation_rejects_bad_academic_year` | Tanggal akhir < mulai = 422 |
| 10 | `test_password_change_revokes_other_sessions` | Ganti password berhasil dan sesi lain dicabut |

Hasil pada saat Fase 2 diverifikasi: **21 passed, 1 warning** (10 pengujian Fase 1 di bawah ini + 11 pengujian Fase 2). Setelah Fase 3, total gabungan menjadi **34 passed, 1 warning**; lihat [`FASE3_TESTING.md`](FASE3_TESTING.md). Warning hanya berasal dari `starlette.testclient` tentang `httpx2`. Rincian Fase 2: [`FASE2_TESTING.md`](FASE2_TESTING.md).

### Pengujian terhadap server yang sedang berjalan

```bat
python scripts\smoke_test.py
```

Skrip ini membaca `data/demo_credentials.txt`, login sebagai admin/guru/siswa, memeriksa pembatasan peran, CSRF, dan pencabutan sesi. Hasil terakhir: **semua pemeriksaan lulus**. Untuk endpoint Fase 2, jalankan juga `python scripts\fase2_probe.py` (lihat [`FASE2_TESTING.md`](FASE2_TESTING.md)).

### Verifikasi antarmuka browser

Login admin, navigasi ke halaman Pengguna, dan membuat pengguna baru melalui formulir sudah diverifikasi di browser sungguhan: data tersimpan, daftar bertambah, dan pesan sukses muncul. Tombol tutup dialog diperbaiki agar tidak bertipe `submit` (mencegah penutupan dialog mengirim formulir).

## B. Pengujian manual fungsional

### B1. Instalasi bersih

1. Hapus folder `.venv`, `node_modules`, `data/pli.db` (opsional, hanya untuk simulasi instalasi baru).
2. Jalankan `scripts\setup-windows.bat`.
3. Pastikan `data/demo_credentials.txt` dibuat dan berisi 4 akun dengan password berbeda.
4. Pastikan tidak ada error merah pada terminal.

### B2. Admin

| Langkah | Hasil yang diharapkan |
|---|---|
| Login `admin` | Dashboard menampilkan jumlah pengguna, guru, siswa, kelas |
| Pengaturan → ubah nama sekolah | Toast sukses; nama berubah di header setelah segarkan |
| Pengaturan → tambah tahun ajaran & semester | Data muncul di daftar |
| Pengguna → tambah siswa | Siswa muncul di daftar, akun perlu ganti password |
| Pengguna → reset password | Toast sukses |
| Pengguna → nonaktifkan akun | Status berubah menjadi Nonaktif |
| Kelas → ubah anggota | Jumlah siswa pada kartu kelas berubah |
| Mapel → tambah mapel & kompetensi | Kompetensi muncul di kartu mapel |
| Log audit | Aksi-aksi di atas tercatat dengan waktu |

### B3. Guru

| Langkah | Hasil yang diharapkan |
|---|---|
| Login `guru1` | Hanya melihat XII RPL 1 dan 2 siswa |
| Buka URL `/users` secara manual | Dialihkan ke dashboard (403 di API) |
| Buka `/my-classes`, pilih kelas | Daftar siswa sesuai kelas |
| Coba `http://localhost:8000/api/v1/admin/users` di tab baru | 403 |

### B4. Siswa

| Langkah | Hasil yang diharapkan |
|---|---|
| Login `siswa1` pada HP | Tampilan bottom navigation nyaman, tombol mudah disentuh |
| Buka `/my-classes` | Hanya kelas sendiri |
| Coba endpoint guru/admin | 403 |
| Ubah password melalui menu Password | Toast sukses; password lama tidak bisa dipakai |

### B5. PWA & offline

1. `npm run build`, lalu `npm run preview` (service worker hanya aktif pada build produksi).
2. Buka alamat preview di Chrome/Edge.
3. Jika tombol **Pasang** muncul, klik dan konfirmasi. Jika tidak muncul, gunakan menu browser → **Save and share / Install app** (tergantung browser).
4. Putuskan internet atau matikan backend.
5. Muat ulang halaman yang sudah pernah dibuka → shell aplikasi tetap tampil (offline fallback).
6. Indikator status berubah menjadi **Offline**. Saat backend kembali, klik **Segarkan** → status kembali **Online**.
7. Pastikan tidak ada permintaan tulis yang dikirim ulang otomatis oleh service worker.

### B6. Backup & restore

1. `python scripts\backup.py` → file `backups/pli-*.db` dan `.sha256` dibuat.
2. Hentikan backend.
3. `python scripts\restore.py backups\<file>.db` → sukses, salinan lama dibuat.
4. Nyalakan backend, login dengan akun demo → data masih ada.

## C. Pengujian yang belum tersedia di Fase 1

Fitur-fitur berikut baru akan diuji pada fase terkait: asesmen & autosave (**sudah diuji di Fase 2**), BKT, adaptive engine, prediksi ML, AI Tutor, RAG, ekspor laporan, dan sinkronisasi dua arah penuh. Antrean IndexedDB untuk jawaban sudah dipakai Fase 2, tetapi belum menjadi sinkronisasi dua arah penuh.

## D. Kriteria lulus Fase 1

- [x] Semua 10 pengujian otomatis lulus
- [x] `npm run build` berhasil dan `npm audit` = 0 kerentanan
- [x] `alembic upgrade head` berhasil pada database kosong
- [x] Login tiga peran berfungsi pada browser
- [x] Isolasi data guru/siswa teruji
- [x] PWA dapat dipasang pada browser yang mendukung
- [x] Backup/restore berhasil
- [ ] Uji coba terbatas dengan guru sekolah (menunggu pengguna)
