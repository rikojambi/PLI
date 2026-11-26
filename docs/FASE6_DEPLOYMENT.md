# Fase 6 — Panduan Deployment Sekolah

Panduan ini menjelaskan konfigurasi produksi yang disiapkan kode Fase 6. Instalasi lokal Windows (`scripts\setup-windows.bat`, `run-all.bat`) tetap menjadi jalur pengujian; langkah di bawah untuk server sekolah yang sebenarnya.

## 1. Prasyarat

- Python 3.11+ dan Node.js 20+.
- PostgreSQL 14+ bila memakai banyak klien; SQLite hanya disarankan untuk satu komputer/uji coba.
- Reverse proxy HTTPS (Nginx/Apache) di depan Uvicorn bila aplikasi diakses lewat jaringan.
- `cryptography` dan `psycopg2-binary` terpasang (`pip install -r requirements.txt`).

## 2. Variabel lingkungan

Salin `.env.example` ke `.env` pada folder proyek, lalu isi minimal:

```ini
PLI_ENVIRONMENT=production
PLI_DEBUG=false
PLI_DATABASE_URL=postgresql+psycopg2://pli:PASSWORD@127.0.0.1:5432/pli
PLI_SECRET_KEY=<string acak panjang, minimal 32 karakter>
PLI_SECRET_KEY_PREVIOUS=
PLI_SESSION_TTL_HOURS=12
PLI_COOKIE_SECURE=true
PLI_COOKIE_SAMESITE=lax
PLI_CORS_ORIGINS=https://pli.sekolah.example
PLI_DEMO_MODE=false
PLI_BACKUP_ENCRYPTION_KEY=<Fernet key, berbeda dari PLI_SECRET_KEY>
PLI_RETENTION_DAYS=365
PLI_AI_LOG_RETENTION_DAYS=90
PLI_AUDIT_LOG_RETENTION_DAYS=365
PLI_METRICS_ENABLED=true
```

Buat kunci backup di server, jangan pernah di frontend atau repository:

```bat
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Kunci API penyedia AI (bila dipakai) juga hanya berupa variabel server `PLI_AI_*`. Nama variabel disimpan di tabel `ai_providers`; frontend hanya menerima petunjuk terselubung dan status model terverifikasi.

## 3. Database dan migrasi

```bat
cd backend
python -m alembic upgrade head
python -m app.db.init_db
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
```

Hanya jalankan `init_db` saat seed awal. Verifikasi:

```bat
python -m alembic current
```

Head harus `b6d1f7a9c2e4 (head)`. Endpoint `/api/health/ready` mengembalikan `503` bila database tidak dapat diakses atau folder `data/` tidak dapat ditulis.

> Catatan: `data/` tetap diperlukan untuk unggahan dan metadata backup walau database memakai PostgreSQL. Pastikan direktori tersebut dapat ditulis oleh proses backend dan tidak diekspos langsung oleh web server.

## 4. HTTPS / SSL

Contoh Nginx (ganti nama host dan sertifikat):

```nginx
server {
    listen 443 ssl http2;
    server_name pli.sekolah.example;

    ssl_certificate     /etc/letsencrypt/live/pli.sekolah.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pli.sekolah.example/privkey.pem;

    client_max_body_size 30m;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy same-origin always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_http_version 1.1;
    }
}
```

Frontend produksi dibangun dengan `npm run build` dan disajikan sebagai berkas statis pada origin yang sama atau origin yang terdaftar di `PLI_CORS_ORIGINS`. Set `PLI_COOKIE_SECURE=true` saat HTTPS aktif.

## 5. Monitoring

| Endpoint | Pemakaian |
|---|---|
| `GET /api/health` | Pemeriksaan dasar |
| `GET /api/health/live` | Liveness probe (proses hidup) |
| `GET /api/health/ready` | Readiness probe (database + direktori data) |
| `GET /api/metrics` | Metrik Prometheus-like: request, status, durasi, error |
| `GET /api/v1/ops/status` | Detail migrasi/tabel/check untuk admin saja |

Setiap respons memiliki header `X-Request-ID` untuk menelusuri log. Endpoint ops dan metrik tidak mengembalikan kunci API maupun kunci sesi. Batasi akses `/api/metrics` di reverse proxy ke jaringan monitoring sekolah.

## 6. Backup terenkripsi

```bat
python scripts\backup.py
python scripts\restore.py backups\pli-YYYYMMDD-HHMMSS.db.enc
```

- Simpan `PLI_BACKUP_ENCRYPTION_KEY` secara terpisah dari berkas backup (misalnya pengelola rahasia sekolah). Kehilangan kunci berarti backup tidak dapat dipulihkan.
- Metadata `.meta.json` berisi checksum ciphertext; jangan dipisahkan dari berkas `.db.enc`.
- Jadwalkan backup harian, simpan salinan di lokasi berbeda, dan uji restore secara berkala.
- Hentikan backend sebelum restore; salinan database lama dibuat otomatis di `data/pli.before-restore.db`.

## 7. Rotasi kunci sesi

1. Pastikan `PLI_BACKUP_ENCRYPTION_KEY` tidak ikut berubah saat rotasi sesi.
2. Login sebagai admin, buka **Operasional → Putar kunci sesi**, ketik `ROTASI`, isi catatan, kirim.
3. Server menulis `PLI_SECRET_KEY` baru dan memindahkan kunci lama ke `PLI_SECRET_KEY_PREVIOUS` untuk satu siklus verifikasi.
4. Frontend tidak pernah menerima kunci; hanya petunjuk (`key_hint`) yang ditampilkan dan dicatat di log audit.
5. Setelah semua sesi lama kedaluwarsa, `PLI_SECRET_KEY_PREVIOUS` boleh dikosongkan oleh administrator server.

Opsi rotasi API (butuh CSRF): `POST /api/v1/privacy/secret/rotate` dengan `{"confirm": true, "note": "..."}`.

## 8. Retensi dan penghapusan

- Pratinjau: `GET /api/v1/privacy/retention/preview` (admin).
- Pembersihan: `POST /api/v1/privacy/retention/purge` dengan `{"confirm": true}`.
- Permintaan penghapusan siswa dan eksekusi permanen tersedia di halaman **Operasional** atau endpoint `/api/v1/privacy/students/{id}/delete(-request)`.
- Log audit sengaja dipertahankan; sertifikat penghapusan memakai `student_ref` hash.
- Sebelum penghapusan permanen, pastikan kewajiban administrasi sekolah terpenuhi dan informed consent tercatat. Lihat [`PRIVACY_CONSENT_RETENTION.md`](PRIVACY_CONSENT_RETENTION.md).

## 9. Verifikasi setelah deployment

```bat
python scripts\fase3_clean_check.py
python scripts\smoke_test.py
python scripts\fase5_probe.py
python scripts\fase6_probe.py
cd frontend && npm run build && npm audit --audit-level=moderate
```

UAT dengan guru dan siswa sekolah nyata tetap menjadi tahapan terpisah dan belum dinyatakan selesai oleh dokumen ini.
