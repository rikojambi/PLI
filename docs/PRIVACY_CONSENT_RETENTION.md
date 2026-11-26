# Privasi, Persetujuan (Informed Consent), dan Retensi Data

Dokumen ini dipakai sebagai dasar pengumuman kepada siswa/orang tua dan pengaturan administrator. Teks persetujuan sebaiknya diterjemahkan/disesuaikan dengan kebijakan sekolah sebelum dipakai.

## 1. Data yang diproses

| Kategori | Contoh | Tujuan |
|---|---|---|
| Identitas akun | username, nama, kelas, sekolah | Autentikasi, cakupan hak akses, laporan |
| Hasil belajar | jawaban, nilai, upaya, durasi, catatan guru | Penilaian, koreksi, profil penguasaan BKT, laporan Fase 5 |
| Jejak adaptif | `bkt_history`, rekomendasi, latihan, celah belajar | Menentukan bahan remedial yang ditinjau guru |
| Interaksi AI | percakapan tutor, potongan dokumen RAG, log pemakaian | Menjawab pertanyaan siswa dengan konteks siswa itu sendiri |
| Konflik sinkronisasi | waktu perangkat, versi jawaban, keputusan guru | Menjaga jawaban offline tidak menimpa data server tanpa tinjauan |
| Log audit | siapa melakukan apa, kapan, alamat IP | Akuntabilitas dan bukti operasi |

Kunci jawaban, rubrik, dan kunci pencocokan **tidak dikirim ke siswa** sebelum upaya dikumpulkan. Kunci API penyedia AI tidak pernah dikirim ke peramban.

## 2. Tujuan dan batasan penggunaan

- Data digunakan untuk pembelajaran, penilaian oleh guru, dan administrasi sekolah.
- BKT adalah model probabilistik transparan; indikator penguasaan, celah, dan anomali **bukan vonis otomatis**.
- **Prediksi dropout tidak dijalankan** sampai ada dataset berlabel tervalidasi dengan persetujuan dan metrik yang dipublikasikan. Endpoint terkait mengembalikan `evaluasi tidak tersedia`.
- Soal/materi hasil generator tetap berstatus **draf guru**; hanya guru yang dapat menyetujui dan mempublikasikan.
- Tidak ada kamera, mikrofon, atau pengawasan invasif.

## 3. Persetujuan awal (contoh teks)

> Kami menggunakan data belajar Anda (jawaban, nilai, catatan guru, dan riwayat latihan) untuk membantu guru memantau penguasaan dan memberikan remedial. Data hanya dapat diakses oleh akun Anda sendiri, guru yang mengampu kelas Anda, dan administrator sekolah. Fitur AI memakai konteks belajar Anda hanya bila administrator mengaktifkan penyedia terverifikasi; bila tidak tersedia, aplikasi akan mengatakan demikian. Kami tidak menjalankan prediksi dropout. Anda/orang tua dapat meminta salinan ringkasan dan penghapusan data melalui administrator sekolah. Persetujuan ini dapat ditarik sesuai kebijakan sekolah; penarikan tidak menghapus log audit yang menjadi bukti administrasi.

Sebelum pemakaian produksi, sekolah sebaiknya mencantumkan: nama sekolah, kontak penanggung jawab data, tanggal persetujuan, dan cara menarik persetujuan.

## 4. Hak akses dan cakupan

- Siswa hanya melihat data dirinya sendiri. Permintaan profil/ekspor dengan `student_id` orang lain ditolak (`403`/`404`).
- Guru hanya melihat siswa pada kelas yang diampu.
- Administrator melihat data dalam sekolahnya; endpoint operasional dan privasi hanya untuk administrator.
- Semua query memakai `school_id` dan/atau daftar kelas yang diizinkan, bukan kepercayaan pada parameter klien.

## 5. Retensi

| Jenis data | Default | Tindakan |
|---|---|---|
| Data siswa (jawaban, nilai, profil) | 365 hari (`PLI_RETENTION_DAYS`) | Dihapus saat permintaan penghapusan disetujui/ dieksekusi; tidak dihapus otomatis tanpa keputusan sekolah |
| Log AI dan percakapan tutor | 90 hari (`PLI_AI_LOG_RETENTION_DAYS`) | Dibersihkan oleh `purge` dengan konfirmasi admin |
| Sesi kedaluwarsa | Sesuai `PLI_SESSION_TTL_HOURS` | Dibersihkan oleh `purge` |
| Konflik sinkronisasi selesai | 365 hari (`PLI_AUDIT_LOG_RETENTION_DAYS`) | Dibersihkan oleh `purge` |
| Log audit | 365 hari | **Dipertahankan** sebagai bukti; tidak dihapus oleh `purge` otomatis |

Pratinjau tersedia di `GET /api/v1/privacy/retention/preview`. Pembersihan hanya berjalan bila administrator mengirim `confirm=true` lewat halaman **Operasional** atau API.

## 6. Prosedur penghapusan

1. Admin mencatat permintaan: `POST /api/v1/privacy/students/{student_id}/delete-request` dengan `{"confirm": true, "reason": "..."}`. Status awal `pending`, jatuh tempo 30 hari.
2. Admin memverifikasi kewajiban administrasi dan informed consent.
3. Admin mengeksekusi: `POST /api/v1/privacy/students/{student_id}/delete` dengan `{"confirm": true, "reason": "..."}`.
4. Server menghapus jawaban, hasil, upaya, profil/BKT, rekomendasi, catatan, konflik, percakapan AI, keanggotaan kelas, sesi, dan permintaan terkait, lalu akun siswa.
5. Sertifikat penghapusan berisi `student_ref` (hash), `deleted_at`, `reason`, `counts`, dan `method=hard_delete_with_audit`; identitas mentah tidak disimpan dalam sertifikat.
6. Log audit tetap menyimpan bukti operasi.

Di antarmuka, semua tombol destruktif meminta ketikan konfirmasi persis dan menampilkan hasil API (sukses/gagal).

## 7. Keamanan pendukung

- Password Argon2id; sesi httpOnly + CSRF; pembatasan laju login.
- Kunci sesi server dapat diputar; kunci lama hanya berlaku satu siklus. Tidak ada kunci mentah di database atau frontend.
- Backup database dienkripsi dengan Fernet (`PLI_BACKUP_ENCRYPTION_KEY`), dilengkapi checksum ciphertext.
- Kunci API AI hanya di server; model harus ditemukan lewat API penyedia atau diverifikasi admin. Tanpa itu, fitur AI menyatakan tidak tersedia.

## 8. Kontak dan penarikan persetujuan

Isi sebelum produksi:

- Penanggung jawab data: ____________________
- Kontak: ____________________
- Alamat sekolah: ____________________
- Cara menarik persetujuan: ____________________
