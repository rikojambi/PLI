# Arsitektur PLI — Fase 1 + Fase 2 + Fase 3 + Fase 4 + Fase 5 + Fase 6

## Prinsip

1. **Fungsional sebelum tampilan.** Setiap tombol pada antarmuka memanggil API nyata.
2. **Modular.** Backend memisahkan konfigurasi, keamanan, model data, skema, endpoint, dan layanan. Frontend memisahkan API client, state autentikasi, penyimpanan lokal, komponen, dan halaman.
3. **Ringan.** SQLite + FastAPI + React+Vite dapat berjalan pada satu laptop sekolah.
4. **Aman secara default.** Password Argon2id, session cookie httpOnly, CSRF double-submit, RBAC, tenant scope per sekolah, rate limit, audit log.
5. **Jujur tentang data.** Analitik Fase 2, profil Fase 3, dan dashboard Fase 5 dihitung dari jawaban yang benar-benar tersimpan. BKT adalah model probabilistik transparan, bukan klaim AI generatif. Tidak ada prediksi dropout aktif tanpa dataset berlabel tervalidasi; indikator peninjauan guru bukan vonis otomatis. Fase 4 tidak menyimpan ID model tebakan atau kunci API di browser: tanpa penyedia aktif dan model terverifikasi, tutor/RAG/generator menyatakan tidak tersedia daripada mengarang jawaban. Fase 6 tidak menyimpan kunci sesi/backup mentah di database atau frontend dan tidak menjalankan aksi destruktif tanpa konfirmasi eksplisit.

## Alur autentikasi

```
Browser ──POST /api/v1/auth/login──▶ FastAPI
        ◀── Set-Cookie: pli_session=<random> (httpOnly, SameSite=Lax)
        ◀── { csrf_token, user }

Setiap request POST/PATCH/PUT/DELETE:
  Cookie pli_session -> hash SHA-256 -> tabel sessions
  Header X-CSRF-Token harus sama dengan sessions.csrf_token
  User aktif + sesi belum kedaluwarsa -> diproses
```

Token sesi tidak disimpan apa adanya di database (hanya hash SHA-256). Logout mencabut sesi. Ganti password mencabut sesi lain. Akun terkunci 15 menit setelah 5 kegagalan login.

## Hak akses & isolasi data

| Peran | Aturan |
|---|---|
| Administrator | Akses penuh **di sekolahnya sendiri** (`users.school_id`), termasuk parameter mesin dan konfigurasi penyedia/model AI |
| Guru | Hanya kelas pada `teacher_classes`; endpoint `/portal/teacher/*`, `/learning/*`, `/intelligence/*`, dan `/ai/documents|generated|generate` menolak kelas/siswa lain dengan 403 |
| Siswa | Hanya `class_members` miliknya; `/learning/attempts`, `/results`, `/notes`, profil BKT, rekomendasi, indikator, dan `/ai/tutor/*` hanya untuk dirinya; bank soal, dokumen, dan draf guru ditolak 403 |

`assert_school_scope()` mencegah administrator mengubah data sekolah lain. Seluruh query daftar memakai filter `school_id`. `_assert_class_access()` memakai `teacher_classes` untuk guru dan `assert_school_scope()` untuk admin. `_resolve_students()` pada Fase 3/Fase 5 menolak `student_id` milik siswa lain dengan `403` atau `404` (service menyamarkan data di luar cakupan), serta membatasi guru pada siswa di kelas yang diampunya. Fase 4 menambah filter `school_id` pada `ai_providers`, `ai_provider_models`, `documents`, `generated_contents`, `ai_usage_logs`, dan `tutor_conversations`; `TutorConversation` dan `TutorMessage` juga dibatasi pada `user.id` pemiliknya (404 bila percakapan siswa lain diminta). Fase 6 membatasi `/ops/status`, `/privacy/*`, dan resolusi konflik sesuai peran: admin saja untuk operasional/privasi, guru/admin untuk resolusi, siswa hanya membaca konflik dan menarik perubahan dirinya.

## Database

**39 tabel aplikasi** dibuat dari model SQLAlchemy (pemeriksaan `sqlite_master` melaporkan 40 termasuk `alembic_version`). Foreign key aktif pada SQLite (`PRAGMA foreign_keys=ON`), WAL diaktifkan, indeks pada kunci asing dan kolom yang sering difilter. Head Alembic saat ini: `b6d1f7a9c2e4` (migrasi Fase 6). Rantai: `e1f2f3696565` → `e1c9acd1e994` → `c4f7a91d3e02` → `f4a6d8b1c3e7` → `b6d1f7a9c2e4`.

Tabel inti Fase 1: `schools`, `roles`, `users`, `sessions`, `academic_years`, `semesters`, `classes`, `class_members`, `teacher_classes`, `subjects`, `competencies`, `learning_objectives`, `audit_logs`, `ai_providers`.

Tabel yang **aktif dipakai Fase 2**: `learning_materials`, `questions`, `question_options`, `assessments`, `assessment_questions`, `student_attempts`, `student_answers`, `assessment_results`, `student_notes`.

Tabel yang **aktif dipakai Fase 3**: `student_competency_mastery`, `bkt_history`, `learning_recommendations`, `adaptive_practices`, `engine_configs`. Kolom `questions.gap_category` menyimpan label kategori celah dari guru. `bkt_history.evidence_id` merujuk ke `student_answers.id` atau `adaptive_practices.id` dan memiliki constraint unik `(student_id, competency_id, evidence_id)` agar replay tidak menggandakan bukti.

Nilai `assessment_results.mastery_percent` kini berasal dari probabilitas BKT pada kompetensi terkait, bukan dari nilai mentah asesmen.

Tabel yang **aktif dipakai Fase 4**: `ai_providers` (unik per `(school_id, name)`), `ai_provider_models`, `ai_usage_logs`, `tutor_conversations`, `tutor_messages`, `documents`, `document_chunks`, dan `generated_contents`. `ai_providers` hanya menyimpan nama environment variable kunci (`api_key_env`), bukan kunci API. `ai_provider_models` sengaja kosong setelah seed: model masuk hanya dari discovery atau verifikasi administrator. `tutor_messages.client_id` unik per `(conversation_id, client_id)` untuk idempotensi pengiriman pesan. `documents` memiliki `status` `uploaded`/`indexed`/`indexed_lexical`/`error`, sedangkan `generated_contents` menyimpan draf guru yang terkait `school_id`, `reviewed_by`, dan `published_ref_id` (hanya diisi setelah persetujuan dengan publikasi).

Fase 5 tidak menambah tabel: seluruh agregasi dibaca dari tabel Fase 2/Fase 3. Fase 6 menambah `sync_conflicts` (versi server/klien + alasan + resolusi + siapa memutuskan), `deletion_requests` (permintaan, jatuh tempo, sertifikat hash), dan `secret_rotations` (waktu, `key_hint`, `previous_key_hint`, admin yang memutar). Tidak ada kolom kunci mentah: rotasi memakai HMAC dengan kunci aktif + kunci sebelumnya satu siklus, sedangkan hash legacy SHA-256 tetap diterima untuk verifikasi sesi lama.

Migrasi:

```bat
cd backend
python -m alembic upgrade head
python -m alembic current
python -m alembic revision --autogenerate -m "nama_perubahan"
```

## Modul pembelajaran Fase 2

Semua endpoint berada di `/api/v1/learning/*` (19 jalur terdaftar di OpenAPI). Penulisan tetap memakai cookie sesi + header `X-CSRF-Token`.

| Kelompok | Endpoint utama | Catatan |
|---|---|---|
| Materi | `GET/POST/PATCH/DELETE /materials`, `POST /uploads`, `GET /files/{stored_name}` | Unggah disimpan di `data/uploads/` dengan nama acak; ekstensi dan ukuran divalidasi server |
| Bank soal | `GET/POST/PATCH/DELETE /questions` | 10 tipe soal; `QuestionIn` membuang `options` sisa draft untuk tipe non-objektif; `gap_category` divisinya |
| Asesmen | `GET/POST/PATCH /assessments`, `GET /assessments/{id}`, `POST /assessments/{id}/start` | `AssessmentOut.question_ids` dipakai saat edit agar pilihan soal tidak hilang |
| Upaya & jawaban | `GET /attempts/{id}`, `PUT /attempts/{id}/sync`, `POST /attempts/{id}/submit`, `GET /attempts/{id}/answers` | Autosave idempotent per `client_id`; konflik dikembalikan dalam `conflicts` |
| Koreksi & hasil | `PATCH /answers/{id}/grade`, `GET /results` | Hanya `essay`/`stepped_essay`/`project` yang boleh dikoreksi manual; nilai dihitung ulang dan profil BKT dibangun ulang |
| Catatan & analitik | `GET/POST /notes`, `PATCH /notes/{id}/read`, `GET /analytics` | Catatan hanya untuk penerima; analitik dari data nyata dengan `evidence` |
| Impor | `POST /import-students?class_id=...` | CSV UTF-8 atau XLSX ≤ 5 MB; duplikat username dilewati, tidak ditimpa |

Aturan penilaian: `multiple_choice`, `true_false`, `image_based`, `multiple_response`, `short_answer`, dan `fill_blank` dinilai di server saat pengumpulan lewat `app/services/grading.py`. `matching` juga objektif pada asesmen, tetapi **tidak** dipakai pada latihan adaptif karena `match_key` tidak dikirim ke siswa. `essay`, `stepped_essay`, dan `project` berstatus `pending_manual` sampai guru memberi poin.

Sinkronisasi jawaban memakai aturan: pengiriman ulang dengan `client_id` + `client_updated_at` yang sama diakui tanpa duplikat; `client_updated_at` lebih baru menang; versi lebih lama/sama ditolak dan dilaporkan. `focus_loss_count` dan `page_hidden_count` hanya menambah `anomaly_flags` (`focus_loss_review`, `page_hidden_review`) untuk ditinjau guru dan tidak memengaruhi `score_percent`.

## Modul intelijen Fase 3

Semua endpoint berada di `/api/v1/intelligence/*` (8 path / 9 operasi). Penulisan tetap memakai cookie sesi + header `X-CSRF-Token`.

| Endpoint | Peran | Fungsi |
|---|---|---|
| `GET /mastery` | admin, guru, siswa | Profil penguasaan per kompetensi. Siswa hanya menerima `mode: student` untuk dirinya; guru/admin menerima `mode: class` sesuai cakupan kelas |
| `GET /gaps` | admin, guru, siswa | Skor celah dan kategori dominan berdasarkan label guru pada soal |
| `POST /adaptive/next-question` | siswa | Memilih soal objektif dari kompetensi terendah; kunci/rubrik tidak dikirim |
| `POST /adaptive/answer` | siswa | Menilai jawaban, mencatat `adaptive_practices`, membangun ulang BKT, idempotent per `client_id` |
| `GET /recommendations` | admin, guru, siswa | Daftar rekomendasi remedial dari bukti yang tersimpan |
| `POST /recommendations/refresh` | admin, guru, siswa | Membuat ulang rekomendasi untuk **satu** siswa dalam cakupan |
| `GET /dropout-evaluation` | admin, guru, siswa | Status evaluasi + indikator advisory; bukan prediksi |
| `GET/PUT /bkt-params` | baca semua peran, ubah admin | Parameter BKT beserta definisi, sumber nilai, dan opsi hitung ulang |

### Bayesian Knowledge Tracing

`app/services/intelligence.py` mengumpulkan observasi nyata dari `student_answers` yang sudah disubmit dan `adaptive_practices`, diurutkan secara deterministik oleh waktu, sumber, dan `evidence_id`. Setiap perubahan jawaban atau koreksi guru memicu `rebuild_mastery()`: riwayat BKT dihapus hanya untuk cakupan terkait, lalu seluruh observasi direplay dari `p_init`. Pendekatan ini membuat hasil idempoten, aman setelah regrade, dan setiap baris riwayat dapat ditelusuri ke buktinya.

Parameter: `p_init`, `p_transit`, `p_slip`, `p_guess`, `mastery_threshold`. Nilai default dibaca dari environment `PLI_BKT_*`; administrator dapat menyimpan override di `engine_configs`. Validasi menolak nilai di luar 0–1, `NaN`/`inf`, parameter tidak dikenal, dan `p_slip + p_guess >= 1`. Setiap perubahan tercatat di `audit_logs`; opsi `recompute` membangun ulang profil seluruh siswa di sekolah administrator.

### Adaptive Question Engine

Kandidat dibatasi pada soal publik dengan tipe `ADAPTIVE_TYPES = OBJECTIVE_TYPES - {"matching"}`. Sistem mengecualikan soal yang sudah dikerjakan siswa, memilih kompetensi dengan probabilitas terendah, dan menyesuaikan kesulitan (`easy`/`medium`/`hard`) dengan penguasaan saat ini. Respons soal memakai skema publik yang sama dengan bank soal siswa, sehingga `is_correct`, `match_key`, dan rubrik tidak pernah dikirim sebelum jawaban masuk. Pengiriman ulang dengan `client_id` yang sama mengembalikan hasil tersimpan tanpa observasi baru.

### Learning Gap Analysis & rekomendasi

Kategori celah (`konsep`, `prosedur`, `hitungan`, `membaca_soal`, `aplikasi`) berasal dari `questions.gap_category` yang ditetapkan guru; sistem tidak menebak kategori. Skor celah menggabungkan probabilitas penguasaan dan akurasi observasi. Rekomendasi `adaptive_practice` dan `remedial_focus` dibuat oleh server dari profil terendah, dengan teks penjelas yang menyertakan angka dan sumbernya.

### Evaluasi dropout yang jujur

`app/services/dropout.py` sengaja tidak menyediakan model aktif. Tanpa `data/datasets/dropout/manifest.json` berisi `validated: true`, berkas metrik dengan checksum cocok, serta precision/recall/F1 dan confusion matrix pada data uji terpisah, endpoint mengembalikan:

```json
{"available": false, "status": "evaluasi_tidak_tersedia"}
```

`evaluate_dropout_dataset()` adalah harness offline untuk evaluasi baseline logistic regression yang hanya boleh dipakai setelah sekolah memastikan persetujuan dan kualitas label. Indikator pada UI diberi penanda `Prediksi: tidak` dan dinyatakan untuk peninjauan guru.

## Modul AI Fase 4

Semua endpoint berada di `/api/v1/ai/*` (26 operasi terdaftar di OpenAPI). Penulisan tetap memakai cookie sesi + header `X-CSRF-Token`. Tabel berikut merangkum pembagian peran:

| Kelompok | Endpoint utama | Peran | Catatan |
|---|---|---|---|
| Katalog & status | `GET /catalog`, `GET /status`, `GET/PUT /budget`, `GET /usage` | baca semua peran, ubah anggaran admin | `status.available` hanya `true` bila ada penyedia aktif **dan** model terverifikasi; biaya `unknown` bila harga belum diisi |
| Penyedia & model | `GET/POST /providers`, `PATCH /providers/{id}`, `POST /providers/{id}/discover`, `GET/POST /providers/{id}/models`, `PATCH /models/{id}`, `POST /providers/{id}/test` | admin saja | `discover` memanggil API penyedia; `POST models` adalah verifikasi manual. Tidak ada ID model bawaan |
| Dokumen | `GET/POST /documents`, `POST /documents/{id}/index`, `DELETE /documents/{id}` | admin, guru | Unggah multipart dengan `title`/`subject_id`; ekstraksi PDF/DOCX/PPTX/TXT/MD; siswa ditolak 403 |
| RAG | `POST /rag/ask` | semua peran | Hanya dokumen pada sekolah + cakupan kelas/kepemilikan akun; sitasi berisi judul dokumen; tanpa potongan relevan → `Data tidak tersedia` tanpa memanggil model |
| Tutor | `GET /tutor/conversations`, `GET /tutor/conversations/{id}`, `POST /tutor/chat` | siswa saja | Percakapan milik sendiri; `client_id` unik untuk idempotensi; prompt memakai profil penguasaan/rekomendasi siswa itu sendiri |
| Generator | `GET /competencies`, `POST /generate`, `GET /generated`, `POST /generated/{id}/approve`, `POST /generated/{id}/reject` | baca admin/guru; tulis guru | Draf tidak otomatis dipublikasikan; `approve(publish=True)` membuat `Question`/`LearningMaterial` |

### Provider Manager dan kerahasiaan kunci

`app/services/provider_manager.py` menyimpan daftar adapter dan `ADAPTER_INFO` (termasuk kebutuhan kunci). Baris `ai_providers` hanya memuat `api_key_env`, yaitu **nama** variabel lingkungan server (misalnya `PLI_AI_GEMINI_API_KEY`). `GET /providers` mengembalikan `api_key_env`, `has_key`, dan `key_hint` yang terselubung; tidak pernah mengembalikan nilai kunci. `app/services/ai_client.py` membaca `os.environ[name]` sesaat sebelum memanggil penyedia dan menyaring pesan error agar query string kunci tidak terekam di log. Kolom lama `encrypted_api_key` sengaja tidak dipakai; tidak ada kunci mentah yang disimpan di database.

`discover` memakai endpoint standar tiap adapter (`/models`, `/v1beta/models`, atau `/api/tags`) dan mengisi `ai_provider_models` dengan kemampuan/model id hasil API. Administrator dapat pula memverifikasi satu model manual bila penyedia tidak mendukung discovery. Router hanya memilih model yang `is_enabled=True` dan sesuai kapabilitas (`chat`/`embedding`).

### Router, fallback, dan anggaran

`app/services/ai_router.py` mengurutkan penyedia aktif berdasarkan `is_primary`, `priority`, dan waktu dibuat; penyedia gagal dicatat lalu dilanjutkan ke fallback. Setiap percobaan menghasilkan `ai_usage_logs` berisi `request_id`, `purpose`, model, token, latensi, status, dan alasan gagal (tersaring). Biaya dihitung hanya bila administrator mengisi harga per juta token; bila tidak, `cost_source="unknown"` dan batas biaya tidak mengklaim akurasi. Anggaran harian/30 hari dihitung dari log nyata `school_id`, bukan dari perkiraan. Bila tidak ada penyedia/model yang lolos, router melempar `AIUnavailable` dengan alasan yang ditampilkan UI—bukan jawaban statis.

### Tutor, RAG, dan generator

- `app/services/tutoring.py` membuka/membuat percakapan milik siswa, membatasi riwayat dari `PLI_TUTOR_MAX_HISTORY`, lalu menyuntik ringkasan penguasaan/rekomendasi milik siswa tersebut ke prompt. Pengiriman ulang dengan `client_id` yang sama mengembalikan pesan tersimpan.
- `app/services/rag.py` memecah teks hasil ekstraksi menjadi potongan `PLI_RAG_CHUNK_SIZE`/`PLI_RAG_CHUNK_OVERLAP`. Bila ada model embedding terverifikasi, vektor disimpan di `document_chunks.embedding_json`; bila tidak, retrieval leksikal dipakai dan dokumen diberi status `indexed_lexical` serta `evidence.method="lexical"`. `answer()` hanya memanggil model bila ada potongan relevan, dan menyertakan `citations` serta bukti `document_count`.
- `app/services/content_generator.py` menghasilkan draf `question`/`material` ke `generated_contents` dengan status `draft`. `approve(publish=True)` membuat `Question` atau `LearningMaterial` yang sudah dipublikasikan dan menyimpan `published_ref_id`; `reject` menolak draf yang belum ditinjau. Tidak ada publikasi otomatis.

## Modul dashboard Fase 5

Endpoint berada di `/api/v1/dashboard/*`: `filters`, `overview`, `progress`, `students/{student_id}/profile`, dan `export?format=xlsx|pdf`. `app/services/dashboard.py` menerima `user` eksplisit dan memakai `resolve_students()` sebelum query apa pun, sehingga cakupan sekolah/kelas tidak bisa dielakkan lewat parameter URL. Filter periode mencakup `7d`, `30d`, `90d`, `all`, dan `custom` (`date_from`/`date_to`) plus `class_id`, `subject_id`, `competency_id`, `student_id`.

`overview` dan `progress` memakai sumber yang sama: `assessment_results` untuk nilai dan `bkt_history` untuk penguasaan. Setiap respons memuat `evidence` berupa sumber dan catatan, termasuk pernyataan bahwa prediksi dropout tidak tersedia. `profile` merangkai identitas, penguasaan, hasil, rekomendasi, catatan, dan deret tren untuk satu siswa dalam cakupan.

`app/services/export.py` memakai `openpyxl` dan `reportlab` di server. Berkas dikirim sebagai lampiran lewat `apiDownload()` di frontend; tidak ada generator sisi klien yang bisa dimanipulasi untuk melihat data di luar cakupan. Grafik frontend memakai komponen SVG dependency-free (`Charts.tsx`).

## Modul Fase 6 — sinkronisasi, privasi, dan operasional

| Kelompok | Endpoint utama | Peran | Catatan |
|---|---|---|---|
| Sinkronisasi | `GET /sync/conflicts`, `POST /sync/conflicts/{id}/resolve`, `GET /sync/pull` | konflik: semua peran; resolusi: guru/admin; pull: siswa | Konflik disimpan saat `client_updated_at` lebih lama/sama; replay persis tetap idempoten setelah resolusi. Pull mengembalikan delta jawaban + cursor + konflik belum selesai |
| Retensi | `GET /privacy/retention/preview`, `POST /privacy/retention/purge` | admin | `purge` hanya berjalan bila `confirm=true`; log audit tidak dihapus |
| Penghapusan | `POST /privacy/students/{id}/delete-request`, `POST /privacy/students/{id}/delete`, `GET /privacy/deletion-requests` | admin | Hard delete + sertifikat `student_ref` hash; keputusan tercatat |
| Rotasi | `POST /privacy/secret/rotate` | admin | Menulis `.env` server, mengembalikan petunjuk kunci saja |
| Operasional | `GET /ops/status` | admin | Status migrasi/checklist tanpa secret |
| Health | `GET /api/health`, `/api/health/live`, `/api/health/ready`, `GET /api/metrics` | publik/internal | `X-Request-ID` pada respons; metrik Prometheus-like |

`app/services/backup_crypto.py` memakai Fernet dari `cryptography` untuk menghasilkan `*.db.enc` + metadata checksum; restore menolak kunci salah, checksum tidak cocok, dan metadata hilang. `scripts/backup.py` dan `scripts/restore.py` memakai layanan tersebut. Konfigurasi produksi (PostgreSQL, HTTPS, monitoring) dan prosedur rotasi ada di [`FASE6_DEPLOYMENT.md`](FASE6_DEPLOYMENT.md); dasar persetujuan/retensi ada di [`PRIVACY_CONSENT_RETENTION.md`](PRIVACY_CONSENT_RETENTION.md).

## Frontend & offline

- Vite proxy `/api` → `http://127.0.0.1:8000`, sehingga cookie same-origin dan CSRF bekerja tanpa CORS rumit saat development.
- `src/lib/api.ts` satu-satunya jalur HTTP; CSRF diambil dari `sessionStorage`.
- `src/lib/offline.ts` membungkus IndexedDB (`kv` untuk snapshot konteks, `answerQueue` untuk antrean jawaban). `localStorage` dipakai sebagai fallback bila IndexedDB tidak tersedia.
- Service worker `public/sw.js`: network-first untuk navigasi dengan fallback ke `index.html`; **tidak** meng-cache respons `/api/`; tidak pernah mereplay request tulis.
- Manifest + ikon mendukung install pada browser yang menyediakan `beforeinstallprompt`. Tidak ada janji install identik di semua OS/browser.
- `src/App.tsx` memisahkan rute menurut peran. Fase 3 menambahkan `/mastery`, `/adaptive`, `/gaps`, `/evaluation`, dan `/engine`; Fase 4 menambahkan `/ai-providers` dan `/ai-usage` (admin), `/ai-documents` dan `/ai-generator` (admin/guru), `/ai-ask` (semua peran), serta `/ai-tutor` (siswa). Fase 5 menambahkan `/progress` (semua peran); Fase 6 menambahkan `/sync` (semua peran) dan `/operations` (admin). `AppShell` menyembunyikan tautan yang tidak sesuai peran dan `ProtectedRoute` mengalihkan akses langsung yang tidak diizinkan.
- Halaman Fase 3 berada di `src/pages/intelligence/`; Fase 4 di `src/pages/ai/`; Fase 5/6 di `src/pages/DashboardPage.tsx`, `ProgressPage.tsx`, `SyncPage.tsx`, dan `src/pages/admin/OperationsPage.tsx`. Semua tombol memanggil endpoint nyata dan menampilkan toast sukses/gagal serta `evidence` atau penjelasan status. Dashboard mengambil `GET /ai/status` sungguhan, bukan status statis.
- `apiUpload()` di `src/lib/api.ts` menerima `fields` tambahan untuk `title`/`subject_id` pada unggah dokumen; `apiDownload()` memakai cookie/CSRF yang sama untuk ekspor Fase 5; CSRF tetap berasal dari `sessionStorage`.
- Aksi Fase 6 yang destruktif memakai modal dengan ketikan konfirmasi persis (`BERSIHKAN`, `AJUKAN`, `HAPUS`, `ROTASI`). Frontend tidak pernah menerima kunci API/kunci sesi mentah; hanya petunjuk kunci dari respons server.

## Konfigurasi

Semua variabel lingkungan backend memakai prefiks `PLI_` dan dibaca oleh `pydantic-settings` dari `.env`. `.env.example` **hanya berisi contoh nama** variabel kunci (`# PLI_AI_OPENAI_API_KEY=` dan sejenisnya), bukan nilai kunci. Fase 3 mendokumentasikan `PLI_BKT_P_INIT`, `PLI_BKT_P_TRANSIT`, `PLI_BKT_P_SLIP`, `PLI_BKT_P_GUESS`, dan `PLI_BKT_MASTERY_THRESHOLD`; frontend hanya menerima nilai efektif melalui `/intelligence/bkt-params`. Fase 4 menambahkan default server `PLI_AI_REQUEST_TIMEOUT_SEC`, `PLI_AI_MAX_TOKENS_PER_REQUEST`, `PLI_AI_DAILY_TOKEN_LIMIT`, `PLI_AI_MONTHLY_COST_LIMIT_USD`, `PLI_RAG_CHUNK_SIZE`, `PLI_RAG_CHUNK_OVERLAP`, `PLI_RAG_TOP_K`, dan `PLI_TUTOR_MAX_HISTORY`. Fase 6 menambahkan `PLI_SECRET_KEY_PREVIOUS` (transisi rotasi), `PLI_BACKUP_ENCRYPTION_KEY`, `PLI_RETENTION_DAYS`, `PLI_AI_LOG_RETENTION_DAYS`, `PLI_AUDIT_LOG_RETENTION_DAYS`, dan `PLI_METRICS_ENABLED`, serta jalur `PLI_DATABASE_URL=postgresql+psycopg2://...` untuk produksi. Kebijakan anggaran yang diubah administrator tersimpan di `engine_configs`, bukan di browser. Tidak ada `PLI_AI_SECRET_ENCRYPTION_KEY`: kunci mentah tidak pernah masuk database atau frontend.

## Pengujian

`tests/conftest.py` membuat engine SQLite dalam memori, menerapkan skema penuh, dan meng-override dependency `get_db`. `TestClient` memastikan cookie dan CSRF diuji seperti browser sungguhan. Total **53 pengujian**: Fase 1–4 (45, termasuk 2 regresi seed), 2 Fase 5, dan 6 Fase 6. Cakupan Fase 3 meliputi rumus dan validasi BKT, replay idempoten, regrade, asal `mastery_percent`, isolasi siswa/guru, adaptive answer + idempotensi, kategori celah, gating dropout, RBAC parameter, dan penolakan tanpa sesi/CSRF. Cakupan Fase 4 memakai transport HTTP palsu untuk menguji status tak tersedia, masking kunci, discovery/verifikasi model, fallback + pencatatan percobaan, anggaran, RAG + sitasi + `Data tidak tersedia`, tutor idempoten dengan profil siswa, alur draf→persetujuan/penolakan, validasi draf kosong, JSON mode Ollama hanya untuk generator, dan tidak bocornya kunci ke payload frontend. Cakupan Fase 5 memeriksa filter/scoping, konsistensi angka, profil, dan tanda tangan berkas XLSX/PDF. Cakupan Fase 6 memeriksa konflik awet + replay idempoten setelah resolusi, retensi/erasure, rotasi secret dengan `.env` sementara, RBAC endpoint, backup/restore terenkripsi, serta health/metrik/ops.

Selain pytest:

- `scripts/smoke_test.py` memeriksa alur auth Fase 1.
- `scripts/fase2_probe.py` memeriksa OpenAPI, RBAC baca, dan penolakan tulis tanpa sesi pada server yang berjalan.
- `scripts/fase3_probe.py` memeriksa 11 kondisi Fase 3 pada server yang berjalan.
- `scripts/fase4_probe.py` memeriksa 28 kondisi Fase 4: OpenAPI, RBAC, kunci terselubung, status jujur tanpa model, penolakan generator tanpa model, CSRF, isolasi tutor siswa, dan RAG `Data tidak tersedia`.
- `scripts/fase5_probe.py` memeriksa filter/overview/progress/profil/ekspor Fase 5 dan penolakan lintas siswa.
- `scripts/fase6_probe.py` memeriksa endpoint Fase 6, health/metrik/request ID, RBAC, penolakan aksi tanpa `confirm`, dan strategi konflik tanpa mengubah data nyata.
- `scripts/fase3_clean_check.py` memverifikasi migrasi/seed pada database sementara (head `b6d1f7a9c2e4`, 40 tabel termasuk `alembic_version`, 8 penyedia, tanpa model hardcoded, tidak ada kunci mentah di `secret_rotations`) dan memastikan kredensial database utama tidak tertimpa.

Detail: [`FASE1_TESTING.md`](FASE1_TESTING.md), [`FASE2_TESTING.md`](FASE2_TESTING.md), [`FASE3_TESTING.md`](FASE3_TESTING.md), [`FASE4_TESTING.md`](FASE4_TESTING.md), [`FASE5_TESTING.md`](FASE5_TESTING.md), dan [`FASE6_TESTING.md`](FASE6_TESTING.md).

## Keputusan teknis dan alasan

| Keputusan | Alasan |
|---|---|
| Session opaque di database, bukan JWT localStorage | Bisa dicabut serta-merta; tidak rentan XSS penyimpanan token di browser |
| Argon2id via `argon2-cffi` | Algoritma hashing password modern, parameter dapat disetel |
| UUID string sebagai primary key | Tidak membocorkan urutan data, memudahkan sinkronisasi offline |
| SQLite + WAL | Tanpa server database tambahan untuk instalasi sekolah kecil |
| Revisi Alembic inkremental per fase | Fase 2 dan Fase 3 dapat diverifikasi sendiri tanpa menghapus fondasi |
| React Router 7 | Versi terbaru tanpa kerentanan `npm audit` yang ditemukan pada v6 |
| Tailwind 3 (bukan 4) | Konfigurasi stabil dan kompatibel dengan toolchain saat ini |
| `client_id` + `client_updated_at` pada jawaban | Autosave bisa diulang tanpa duplikat dan konflik tidak ditutupi |
| Anomali, celah, dan indikator sebagai advisory | Menghindari vonis otomatis tanpa bukti dan persetujuan manusia |
| BKT direplay dari awal, bukan delta | Idempoten, dapat ditinjau, dan konsisten setelah koreksi guru |
| Parameter BKT di database + env, bukan frontend | Administrator dapat mengkalibrasi tanpa deploy; perubahan dapat diaudit |
| `matching` dikecualikan dari latihan adaptif | Kunci pencocokan tidak boleh dikirim ke siswa |
| Dropout evaluation gate | Mencegah klaim prediksi tanpa dataset tervalidasi dan metrik uji |
| Kunci API hanya referensi env server | Tidak ada secret di browser/database; tidak perlu modul enkripsi kunci mentah |
| Model dari discovery/verifikasi, bukan hardcoded | Nama model berubah cepat; router tidak boleh mengklaim model yang belum tersedia |
| Penyedia AI diskop per `school_id` | Konfigurasi dan biaya satu sekolah tidak bocor ke sekolah lain |
| Biaya `unknown` bila harga belum diisi | Anggaran berasal dari pemakaian nyata, bukan perkiraan yang menyesatkan |
| Retrieval leksikal berlabel jujur | Tidak mengklaim semantic search tanpa model embedding terverifikasi |
| Draf generator perlu persetujuan guru | Konten AI tidak langsung menjadi materi/soal yang dipakai siswa |
| Dashboard/ekspor memakai satu helper scope | Tidak ada jalan pintas yang bisa menampilkan data siswa lain lewat filter atau berkas |
| Konflik disimpan, bukan ditimpa diam-diam | Bukti offline tetap dapat ditinjau guru setelah perangkat hilang |
| `client_id` diubah saat resolusi klien | Replay perangkat lama tidak membuat konflik baru setelah guru memilih versi klien |
| Kunci lama sesi berlaku satu siklus | Sesi aktif tidak langsung terputus saat rotasi, tetapi tetap ada batas waktu |
| Backup Fernet + checksum metadata | Kunci/checksum salah terdeteksi sebelum database ditimpa saat restore |
| Log audit dipertahankan setelah erasure | Bukti administrasi tetap ada tanpa menyimpan jawaban siswa mentah |
| Aksi destruktif butuh ketikan konfirmasi | Mengurangi risiko klik tidak sengaja pada data produksi |

## Asumsi

- Satu sekolah per instalasi (kolom `school_id` sudah disiapkan untuk multi-sekolah).
- Gateway sekolah mengizinkan `localhost:8000` dan `localhost:5173` pada pengujian awal.
- Guru yang mengampu kelas diberi hak oleh administrator melalui `teacher_classes`; hak ini dipakai di Fase 2 dan Fase 3.
- Waktu disimpan naive UTC; konversi ke waktu lokal dilakukan di antarmuka.
- Mode offline menjamin antrean jawaban, konflik yang awet, dan pull delta server; resolusi akhir tetap memerlukan tinjauan guru/admin.
- Parameter BKT bersifat global per sekolah; kalibrasi per siswa/mapel/kompetensi belum tersedia.
- Fitur generatif Fase 4 baru aktif setelah administrator mengisi kunci API server atau menjalankan Ollama lokal serta memverifikasi minimal satu model; sampai saat itu status `belum tersedia` adalah perilaku yang disengaja. Verifikasi lokal memakai Ollama dengan model hasil discovery; penyedia cloud tetap memerlukan kunci API server.
- PostgreSQL/HTTPS/monitoring produksi dan UAT guru/siswa sekolah nyata belum dilakukan; “selesai” berarti terverifikasi secara teknis lokal.
