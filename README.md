# Day 06 · Data Ingestion — Pháp luật lao động Việt Nam

**Học viên:** Nguyễn Minh Phúc · **MSSV:** 2A202603894 · Thông tin nộp bài: [STUDENT.md](STUDENT.md) · Báo cáo: [report/individual/2A202603894_NguyenMinhPhuc.md](report/individual/2A202603894_NguyenMinhPhuc.md)

Bài làm biến 3 văn bản luật lao động thành kho tri thức truy xuất được. Bài so sánh 3 chiến lược chuẩn bị dữ liệu trên cùng một bộ 200 câu hỏi.

| | |
|---|---|
| Corpus | BLLĐ 2019, BLLĐ 2012 (đã hết hiệu lực), Nghị định 145/2020/NĐ-CP: 4 file PDF, **221 trang nội dung** |
| Benchmark | **200 câu** (160 dev / 40 test), 59 câu có metadata filter, mọi evidence đã kiểm chứng trên PDF |
| Embedding | OpenAI `text-embedding-3-small` (1536 chiều) |
| Vector store | PostgreSQL 16 + pgvector 0.8.7, cosine exact search |
| Chiến lược | **A** chunk cố định 800/100 · **B** chunk theo Điều (≤1500 ký tự) · **C** = B + lọc `year`/`document_id` |

## Kết quả chính

| Strategy | Dev Hit@1 | Dev Hit@3 | Test Hit@1 | Test Hit@3 | Coherence /2 | Grounding /2 |
|---|---|---|---|---|---|---|
| A | 41/160 | 80/160 | 10/40 | 17/40 | 1,0 | 1,2 |
| B | 79/160 | 120/160 | 20/40 | 28/40 | 1,8 | 1,6 |
| **C** (chọn theo dev) | **91/160** | **128/160** | **22/40** | **29/40** | 1,8 | 2,0 |

Tổng chi phí embedding khoảng **$0,0125**. Phân tích chi tiết, ví dụ lỗi và giới hạn nằm trong báo cáo.

## Cấu trúc

```text
starter/
├── data/                  4 PDF + manifest.json (nguồn, quyền, số trang, ký tự/trang)
├── benchmark/questions.json   200 câu: question, expected_answer, gold_source_id,
│                              gold_page, evidence_quote, filter, alt_gold
├── scripts/
│   ├── check_setup.py         kiểm tra Postgres + pgvector
│   ├── build_manifest.py      đếm trang/ký tự, sha256 -> manifest.json
│   └── verify_benchmark.py    kiểm chứng evidence nằm đúng trang PDF
├── src/
│   ├── ingestion.py           đọc PDF, chuẩn hóa (NFC, 'ƣ'->'ư', bỏ header Công báo)
│   ├── chunking.py            fixed_size (A), by_article (B/C)
│   ├── build_chunks.py        bước 3: xuất chunks_A/B.jsonl + thống kê
│   ├── embeddings.py          adapter OpenAI (không fallback sang vector giả)
│   ├── store.py               pgvector: schema, upsert theo chunk_id, filter, search
│   ├── ingest.py              bước 4: embed + nạp (bỏ qua chunk không đổi)
│   ├── evaluation.py          Hit@1 / Evidence Hit@3, trace
│   ├── run.py                 bước 5: chạy A/B/C, metrics, file audit
│   ├── search.py              tra cứu thử 1 câu
│   └── config.py              cấu hình, giả thuyết, tiêu chí chọn (chốt trước khi chạy)
└── results/               chunks, trace_{A,B,C}.jsonl, metrics.json, ingest_runs.jsonl,
                           audit_*_labeled.csv, audit_summary.json, ingest_errors.log
artifacts/experiment_log.csv   cấu hình + giả thuyết + Hit dev/test của A/B/C
report/individual/2A202603894_NguyenMinhPhuc.md
```

## Cài đặt

Cần Docker, Python 3.11+ và một OpenAI API key.

```bash
cd starter
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # điền OPENAI_API_KEY, EMBEDDING_MODEL=text-embedding-3-small
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py # kỳ vọng: Setup OK
```

`.env` nằm trong `.gitignore` và không được commit.

## Chạy pipeline

Các lệnh chạy trong `starter/`, theo đúng thứ tự:

```bash
python scripts/build_manifest.py     # 1. thống kê trang -> data/manifest.json
python scripts/verify_benchmark.py   # 2. kiểm chứng 200 evidence (kỳ vọng: OK)
python -m src.build_chunks           # 3. chunk A (788) và B (714)
python -m src.ingest                 # 4. embed + nạp pgvector (~$0,012)
python -m src.ingest                 #    chạy lại: phải embed 0, số dòng không đổi
python -m src.run                    # 5. benchmark A/B/C -> results/, experiment_log.csv
```

Tra cứu thử một câu:

```bash
python -m src.search "Theo Bộ luật Lao động 2012, tuổi nghỉ hưu của nam và nữ là bao nhiêu?" --strategy C --filter year=2012
```

**Lưu ý khi tái lập:** `src.run` sinh thêm các file mẫu `results/audit_*.csv` để trống (đã xóa khỏi repo vì là bản trống). Nhãn đã chấm nằm trong `results/audit_*_labeled.csv` và không bị ghi đè. Kết quả có thể lệch nhẹ nếu OpenAI cập nhật model.

## Dữ liệu và quyền sử dụng

Văn bản quy phạm pháp luật không thuộc đối tượng bảo hộ quyền tác giả (Điều 15 Luật Sở hữu trí tuệ), nên được xử lý và chia sẻ. URL nguồn, ngày tải, sha256 và các trang bị loại kèm lý do được ghi trong [starter/data/manifest.json](starter/data/manifest.json). NĐ 145 là bản Công báo chính thức. Hai Bộ luật là bản sao đăng trên website trường đại học.

## Sử dụng AI

Bài làm dùng Claude (Claude Code) để hỗ trợ:

- tìm nguồn và viết code,
- soạn câu hỏi benchmark từ câu trích trong corpus,
- chấm nhãn audit,
- soạn báo cáo.

Evidence được kiểm chứng tự động trên PDF gốc. Chi tiết cách dùng và cách kiểm tra nằm trong báo cáo.

## Đề bài gốc

Hướng dẫn lab: [GUIDE.md](GUIDE.md) · [BENCHMARK.md](BENCHMARK.md) · [RUBRIC.md](RUBRIC.md) · [RULES.md](RULES.md) · [SUBMISSION.md](SUBMISSION.md) · [CHECKPOINTS.md](CHECKPOINTS.md) · [starter/README.md](starter/README.md)
