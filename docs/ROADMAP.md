# Roadmap PLI

Aturan: setiap fase harus menghasilkan aplikasi yang bisa dijalankan dan diuji. Fase berikutnya tidak dimulai bila fase sebelumnya memiliki error kritis yang belum terselesaikan.

## FASE 1 — Fondasi ✅ SELESAI (implementasi awal)

Struktur proyek, 31 tabel database (Fase 2 menambah `student_notes` menjadi 32), migrasi Alembic, backend FastAPI, autentikasi session+CSRF, RBAC admin/guru/siswa, isolasi kelas, frontend React+Vite+Tailwind, PWA dasar, IndexedDB, audit log, seed demo, backup/restore, 10 tes otomatis, dokumentasi.

## FASE 2 — Pembelajaran ✅ SELESAI (terverifikasi lokal)

- [x] API materi pembelajaran & unggah file (ekstensi `.pdf/.txt/.md/.docx/.pptx/.png/.jpg/.jpeg/.webp`, maksimal 5 MB, nama tersimpan acak)
- [x] Bank soal 10 tipe soal + opsi/rubrik, divalidasi server; kunci disembunyikan dari siswa sebelum pengumpulan
- [x] Asesmen: durasi, jendela waktu, acak soal/opsi, bobot, izinkan lanjut, izinkan offline, publikasi, edit dengan `question_ids` terjaga
- [x] Autosave jawaban dengan `client_id`, `client_updated_at`, antrean IndexedDB, dan laporan konflik tanpa menimpa jawaban server diam-diam
- [x] Penilaian objektif otomatis; uraian/proyek masuk antrean koreksi guru dan nilai dihitung ulang setelah koreksi
- [x] Tanda anomali (fokus/halaman tersembunyi) sebagai **indikator untuk ditinjau**, bukan vonis kecurangan atau pengurangan nilai otomatis
- [x] Catatan belajar guru→siswa dengan pembatasan kepemilikan dan status dibaca
- [x] Analitik kelas dari `assessment_results + student_answers` beserta bukti perhitungan; ambang batas 70 dapat ditinjau
- [x] Impor siswa CSV/XLSX; duplikat username tidak ditimpa; password di-hash
- [x] 11 pengujian otomatis Fase 2; probe API langsung; alur browser admin/guru/siswa terverifikasi

Bukti dan perintah verifikasi: [`FASE2_TESTING.md`](FASE2_TESTING.md). Catatan: uji coba terbatas dengan guru sekolah masih tertunda, sehingga status “selesai” mencakup verifikasi teknis lokal, bukan UAT pengguna.

## FASE 3 — Intelligence Engine ✅ SELESAI (terverifikasi lokal)

- [x] Student Knowledge Profile per kompetensi dari jawaban nyata (`bkt_history`, `student_answers`, `adaptive_practices`)
- [x] Bayesian Knowledge Tracing dengan replay deterministik dari awal; parameter server-side via `engine_configs` + default `.env`, dapat diubah administrator dan tercatat di log audit
- [x] Validasi parameter BKT: nilai 0–1, bukan `NaN`/`inf`, dan `p_slip + p_guess < 1`
- [x] Adaptive Question Engine: memilih kompetensi terendah, hanya soal objektif yang dapat dijawab tanpa kunci, kunci/rubrik tidak dikirim ke siswa, idempotent per `client_id`
- [x] Learning Gap Analysis dengan kategori dari label guru (`konsep`, `prosedur`, `hitungan`, `membaca_soal`, `aplikasi`); tidak menebak kategori otomatis
- [x] Dashboard penguasaan siswa/guru, rekomendasi remedial berbasis bukti, dan halaman evaluasi yang jujur
- [x] Prediksi ketertinggalan **tidak diaktifkan**: endpoint mengembalikan `evaluasi_tidak_tersedia` sampai manifest tervalidasi + berkas metrik tersedia; indikator peninjauan guru ditandai `is_prediction: false`
- [x] 12 pengujian otomatis Fase 3 (total 34 pengujian), probe API langsung, dan alur browser admin/guru/siswa terverifikasi

Bukti dan perintah verifikasi: [`FASE3_TESTING.md`](FASE3_TESTING.md). Status “selesai” hanya berarti verifikasi teknis lokal; uji coba terbatas dengan guru sekolah masih tertunda.

## FASE 4 — AI ✅ SELESAI (terverifikasi lokal)

- [x] AI Provider Manager untuk 8 adapter: Gemini, Groq, OpenRouter, Hugging Face Router, Cerebras, Mistral, OpenAI-compatible, dan Ollama; penyedia diskop per `school_id`
- [x] Kunci API hanya berupa **nama environment variable server**, tidak pernah dikirim ke browser; respons hanya `has_key` dan petunjuk terselubung
- [x] Inventaris model dari discovery API penyedia atau verifikasi administrator; **tidak ada ID model hardcoded**. Tanpa model aktif, status dan fitur AI jujur menyatakan tidak tersedia
- [x] Model Router dengan primary/fallback, pembatasan token harian & biaya bulanan dari server, serta catatan pemakaian nyata (`ai_usage_logs`)
- [x] AI Tutor khusus siswa: memakai profil penguasaan/rekomendasi siswa itu sendiri, `client_id` idempotent, dan hanya dokumen yang diizinkan
- [x] RAG: ekstraksi PDF/DOCX/PPTX/TXT/MD, chunking, embedding bila tersedia (label jujur `indexed_lexical`/`lexical` bila tidak), retrieval, sitasi, dan jawaban `Data tidak tersedia`
- [x] Generator soal/materi menghasilkan draf guru; publikasi ke `questions`/`learning_materials` hanya setelah `approve(publish=True)`
- [x] 10 pengujian otomatis Fase 4 (total 45 pengujian), 28 pemeriksaan probe API, instalasi bersih, build/audit frontend, dan alur browser admin/guru/siswa terverifikasi

Bukti dan perintah verifikasi: [`FASE4_TESTING.md`](FASE4_TESTING.md). Status “selesai” hanya berarti verifikasi teknis lokal: generatif live teruji dengan Ollama lokal dan model hasil discovery administrator; penyedia cloud belum teruji tanpa kunci API, dan uji coba terbatas dengan guru sekolah masih tertunda.

## FASE 5 — Dashboard ✅ SELESAI (terverifikasi lokal)

- [x] Filter periode (termasuk rentang custom), kelas, mapel, kompetensi, dan siswa dari daftar yang diizinkan server
- [x] Grafik perkembangan nilai dan penguasaan BKT dari `assessment_results`/`bkt_history`, SVG tanpa library tambahan
- [x] Profil perkembangan per siswa: kompetensi, hasil asesmen, rekomendasi, catatan, dan sumber bukti
- [x] Ekspor Excel (`.xlsx`) dan PDF dibuat server-side dari data yang sama dengan filter; unduhan terautentikasi
- [x] Scoping ketat: siswa hanya profil sendiri; pelanggaran menghasilkan `403`/`404`
- [x] 2 pengujian otomatis Fase 5 (total 47 sebelum Fase 6), probe API, build frontend, dan verifikasi browser lokal

Bukti: [`FASE5_TESTING.md`](FASE5_TESTING.md). Angka adalah data historis, bukan prediksi; dropout tetap `evaluasi tidak tersedia`.

## FASE 6 — Produksi ✅ SELESAI (terverifikasi lokal)

- [x] Sinkronisasi dua arah: `client_id` idempotent, server→klien delta via `/sync/pull` dengan cursor, konflik tersimpan di `sync_conflicts`
- [x] Strategi konflik jelas: `client_updated_at` terbaru menang, keputusan guru/admin (`server`/`client`) tercatat di log audit; versi klien hanya sebelum upaya dikumpulkan
- [x] Rotasi kunci sesi server-side dengan `PLI_SECRET_KEY_PREVIOUS` satu siklus; frontend hanya menerima petunjuk kunci
- [x] Backup database terenkripsi Fernet + metadata checksum; restore menolak kunci/checksum tidak valid
- [x] Retensi/pratinjau/pembersihan dengan konfirmasi eksplisit, permintaan & penghapusan siswa, sertifikat hash, log audit dipertahankan
- [x] Health/live/ready, `X-Request-ID`, metrik, dan `/ops/status` admin-only; konfigurasi PostgreSQL, HTTPS, dan panduan deployment
- [x] 6 pengujian otomatis Fase 6 (total 53 pengujian), probe API, instalasi bersih head `b6d1f7a9c2e4`, build/audit frontend, dan verifikasi browser lokal
- [x] Dokumentasi deployment, privasi, informed consent, dan retensi

Bukti: [`FASE6_TESTING.md`](FASE6_TESTING.md), [`FASE6_DEPLOYMENT.md`](FASE6_DEPLOYMENT.md), [`PRIVACY_CONSENT_RETENTION.md`](PRIVACY_CONSENT_RETENTION.md). Status “selesai” hanya berarti verifikasi teknis lokal: PostgreSQL/HTTPS produksi dan UAT guru/siswa sekolah nyata belum dilakukan.

## DI LUAR RUANG LINGKUP (menunggu data/keputusan sekolah)

- Prediksi dropout: memerlukan dataset berlabel tervalidasi, consent, dan metrik yang dipublikasikan.
- Penyedia AI cloud: memerlukan kunci API server dan verifikasi administrator.
- Kalibrasi BKT per siswa/mapel/kompetensi serta pembatas laju bersama untuk multi-worker.
