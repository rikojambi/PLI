# Fase 6 — Pengujian Offline-first, Keamanan, Retensi, dan Operasional

Fase 6 melengkapi sinkronisasi dua arah, konflik yang awet, rotasi kunci, backup terenkripsi, retensi/penghapusan data, monitoring, dan kesiapan PostgreSQL. Pengujian lokal tidak mengklaim UAT sekolah atau lingkungan produksi yang belum tersedia.

## 1. Migrasi dan skema

Head Alembic: `b6d1f7a9c2e4` (`down_revision = f4a6d8b1c3e7`).

Rantai: `e1f2f3696565` → `e1c9acd1e994` → `c4f7a91d3e02` → `f4a6d8b1c3e7` → `b6d1f7a9c2e4`.

Tabel baru: `sync_conflicts`, `deletion_requests`, `secret_rotations`. Tidak ada kolom yang menyimpan kunci API/kunci sesi mentah; yang ada hanya `key_hint`.

```bat
cd backend
python -m alembic current
python -m alembic upgrade head
cd ..
python scripts\fase3_clean_check.py
```

Clean check memakai database SQLite sementara, tidak menimpa `data/pli.db` maupun `data/demo_credentials.txt`. Pemeriksaan meliputi head migrasi, keberadaan tiga tabel baru, dan tidak adanya kolom `secret`/`api_key` pada `secret_rotations`.

## 2. Pengujian otomatis

```bat
cd backend
python -m pytest
```

Fase 6 menambah `tests/test_fase6.py` (6 pengujian) untuk:

1. **Konflik awet dan dapat diselesaikan.** Jawaban lama dari perangkat menulis `SyncConflict`; guru memilih versi klien sebelum upaya dikumpulkan; replay identik setelah resolusi tetap idempoten dan tidak memunculkan konflik baru.
2. **Retensi & penghapusan.** Pratinjau menghitung data kedaluwarsa; `purge` tanpa `confirm=true` ditolak 400; penghapusan siswa menghasilkan sertifikat dengan `student_ref` hash dan `method=hard_delete_with_audit`; log audit tetap ada.
3. **Rotasi secret.** `rotate_secret(...)` dengan berkas `.env` sementara menulis `PLI_SECRET_KEY` baru, memindahkan kunci lama ke `PLI_SECRET_KEY_PREVIOUS`, mengembalikan petunjuk saja, dan tetap memverifikasi hash legacy.
4. **RBAC.** Endpoint rotasi dan status operasional hanya admin; guru/siswa ditolak.
5. **Backup terenkripsi.** `create_backup()` menghasilkan `.db.enc` + metadata dengan checksum ciphertext; restore sukses dengan kunci benar, gagal dengan kunci salah/checksum tidak cocok/metadata hilang.
6. **Health & metrik.** `/api/health`, `/api/health/live`, `/api/health/ready`, `/api/metrics`, header `X-Request-ID`, dan `/api/v1/ops/status` mengembalikan informasi tanpa kunci rahasia.

`tests/test_dashboard.py` (Fase 5) ikut dijalankan dalam suite penuh.

## 3. Probe langsung

Dengan backend berjalan:

```bat
python scripts\smoke_test.py
python scripts\fase2_probe.py
python scripts\fase3_probe.py
python scripts\fase4_probe.py
python scripts\fase5_probe.py
python scripts\fase6_probe.py
```

Probe Fase 6 **tidak** menjalankan aksi destruktif: tidak memutar kunci, tidak menghapus data, tidak membersihkan log. Ia hanya:

- memeriksa endpoint terdaftar di `openapi.json`;
- memeriksa health live/ready, metrik, dan request ID;
- membaca status ops sebagai admin dan memastikan tidak ada string `secret_key` dalam respons;
- memastikan `purge` dan rotasi tanpa `confirm` ditolak 400;
- memastikan guru tidak bisa membaca status ops/retensi;
- memastikan guru melihat konflik dalam cakupan dan siswa bisa `/sync/pull`;
- memastikan strategi konflik menyebut `client_updated_at`.

Jalankan probe berurutan dengan jeda: pembatas laju login adalah 10 percobaan/5 menit per IP. Bila menerima 429, tunggu atau restart backend untuk proses pengujian lokal.

## 4. Backup dan restore terenkripsi

```bat
python scripts\backup.py
python scripts\restore.py backups\pli-YYYYMMDD-HHMMSS.db.enc
```

- Kunci berasal dari `PLI_BACKUP_ENCRYPTION_KEY` di `.env` server.
- Backup ditulis sebagai `pli-*.db.enc`; metadata `pli-*.db.meta.json` memuat checksum SHA-256 ciphertext, waktu, dan ukuran.
- Restore memerlukan sidecar metadata dan kunci yang sama. Kunci salah, checksum tidak cocok, atau metadata hilang ditolak.
- Backup plaintext lama dengan `.sha256` masih dapat dipulihkan untuk migrasi, tetapi backup baru tidak lagi plaintext.
- Hentikan backend sebelum restore.

## 5. Antarmuka Fase 6

- **Sinkronisasi** (`/sync`) — tersedia untuk ketiga peran. Siswa melihat konfliknya sendiri bersifat read-only; guru/admin dapat memilih `server` atau `client` dan menulis catatan keputusan. Versi klien hanya diterapkan bila upaya masih berlangsung.
- **Operasional** (`/operations`) — admin saja. Menampilkan status migrasi/metrik, pratinjau retensi, riwayat permintaan penghapusan, dan tombol rotasi kunci. Setiap aksi destruktif membuka modal dengan ketikan konfirmasi persis (`BERSIHKAN`, `AJUKAN`, `HAPUS`, `ROTASI`) dan melaporkan hasil API via toast.

## 6. Kesiapan produksi (bukan bukti produksi)

Lihat [`FASE6_DEPLOYMENT.md`](FASE6_DEPLOYMENT.md) untuk PostgreSQL, HTTPS/SSL, variabel lingkungan, monitoring, dan prosedur rotasi. Lingkungan produksi sekolah belum disediakan, sehingga verifikasi yang dilakukan adalah lokal: pytest, clean check, probe, build frontend, audit npm, dan browser pada instalasi lokal.

## 7. Batasan yang jujur

- PostgreSQL dan reverse proxy HTTPS belum diuji pada server sekolah nyata; `psycopg2-binary` dideklarasikan tetapi koneksi produksi belum tersedia.
- Ollama lokal memakai `qwen2.5:7b` dengan timeout 180 detik; generasi pada CPU lokal ≈107 detik. Penyedia cloud belum diuji tanpa kunci API.
- RotasiSecret mempertahankan kunci lama satu siklus agar sesi aktif tidak langsung putus; sesi lama kedaluwarsa tetap dihapus oleh retensi.
- Audit log sengaja dipertahankan sebagai bukti; penghapusan permanen menyimpan sertifikat berbasis hash, bukan identitas siswa mentah.
- UAT dengan guru/siswa sekolah nyata **belum dilakukan** dan tidak dinyatakan selesai oleh pengujian teknis ini.
