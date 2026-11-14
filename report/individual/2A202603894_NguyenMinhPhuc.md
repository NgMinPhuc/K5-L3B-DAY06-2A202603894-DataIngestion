# Báo cáo cá nhân — Day 6

**Học viên:** Nguyễn Minh Phúc · **MSSV:** 2A202603894 · **Chủ đề:** Pháp luật lao động Việt Nam

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  - 3 văn bản, 4 file PDF có lớp text (chi tiết: `starter/data/manifest.json`):

    | source_id | Văn bản | Nguồn | Trang vật lý / tính |
    |---|---|---|---|
    | `blld-2019` | Bộ luật Lao động 45/2019/QH14 | Bản sao trên website ĐH Ngân hàng TP.HCM | 47 / 46 |
    | `blld-2012` | Bộ luật Lao động 10/2012/QH13 (đã hết hiệu lực) | Bản sao trên website ĐH Kinh tế & QTKD – ĐH Thái Nguyên | 68 / 67 |
    | `nd-145-2020-cb1203` | Nghị định 145/2020/NĐ-CP (phần 1) | Công báo chính thức, congbao.chinhphu.vn | 95 / 94 |
    | `nd-145-2020-cb1205` | Nghị định 145/2020/NĐ-CP (phần 2) | Công báo chính thức | 47 / 14 |
    | **Tổng** | | | **257 / 221** |

  - **Quyền sử dụng:** văn bản quy phạm pháp luật không thuộc đối tượng bảo hộ quyền tác giả (Điều 15 Luật Sở hữu trí tuệ), nên được xử lý và chia sẻ.
  - **Quy tắc tính trang:** chỉ tính trang có nội dung Điều/Khoản. Trang có dưới 200 ký tự sau chuẩn hóa NFC bị loại tự động. Phụ lục mẫu biểu (NĐ 145 phần 2, trang 15–47) bị loại thủ công, có ghi lý do từng trang. Script đếm trang: `scripts/build_manifest.py`.
  - **Thay nguồn BLLĐ 2012:** bản đầu tiên tải về (vnuf.edu.vn, 34 trang) chỉ có tên khoảng 86 Điều mà không có nội dung, ví dụ Điều 97. Mình phát hiện khi tìm evidence và đã thay bằng bản đầy đủ 68 trang.

- **Chuẩn hóa, lỗi và giới hạn:**
  - `normalize_text` thực hiện:
    - Chuẩn hóa NFC.
    - Đổi `ƣ` (U+01A3) thành `ư`. Đây là lỗi font của PDF 2012.
    - Bỏ dòng tiêu đề `CÔNG BÁO/Số …` lặp lại ở mọi trang NĐ 145, và bỏ dòng chỉ có số trang.
    - Gộp khoảng trắng trong từng dòng nhưng **giữ xuống dòng**, để còn nhận ra đầu Điều và Khoản.
  - `results/ingest_errors.log` ghi lại 36 trang bị bỏ qua. Cả 36 đều là trang manifest đã loại. Không có trang nào lỗi khi trích text hoặc trống ngoài dự kiến.
  - **Lỗi chưa sửa:** PDF chèn khoảng trắng vào giữa âm tiết, ví dụ "nhà n ước", "Đi ều". Không có quy tắc sửa an toàn nên mình giữ nguyên. Có hai hệ quả:
    - Khi chấm, evidence được so khớp sau khi bỏ hết khoảng trắng.
    - Regex tiêu đề Điều phải chấp nhận khoảng trắng trong số Điều. Bản 2012 có "Điều 1 45." và "Điều 20 0.". Ban đầu regex bỏ sót 4 Điều (145, 195, 200, 227). Sau khi sửa, regex nhận đủ 242/242 Điều của bản 2012, 220/220 của bản 2019 và 115/115 của NĐ 145.
  - Lỗi khoảng trắng này có thể làm giảm chất lượng embedding. Mình chưa đo được mức ảnh hưởng.

- **Embedding model, vector store, metric, lệnh chạy và chi phí:**
  - **Embedding:** OpenAI `text-embedding-3-small`, 1536 chiều, SDK `openai` 2.54.0. Câu hỏi và chunk được embed giống nhau, không thêm tiền tố.
  - **Vector store:** PostgreSQL 16.16 + pgvector 0.8.7 (Docker Compose của starter). Tìm theo cosine (`<=>`) kiểu **exact**, không dùng chỉ mục xấp xỉ HNSW/IVF. Cả A, B, C dùng chung store và metric.
  - **Lệnh chạy** (trong `starter/`):

    ```bash
    python scripts/build_manifest.py
    python scripts/verify_benchmark.py
    python -m src.build_chunks
    python -m src.ingest
    python -m src.run
    ```

  - **Chi phí:**
    - Ingest: 615.811 token, khoảng $0,0123 (A: $0,0065; B: $0,0058), mất 20 giây.
    - Truy vấn 200 câu: 8.530 token, khoảng $0,00017.
    - Giá tính theo bảng giá OpenAI $0,02 / 1 triệu token.
  - **Lỗi nhà cung cấp:** lần ingest đầu tiên lỗi `401 expired_secret_key` do API key hết hạn. Sau khi thay key, mình chạy lại. Lần lỗi không ghi dữ liệu nào vào DB, và code không tự chuyển sang vector giả.

- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:**
  - **Bắt buộc:** `document_id`, `source_id` (từng file), `source` (đường dẫn), `page`, `page_end` (chunk có thể vắt qua 2 trang).
  - **Trường lọc:**
    - `year` (int). Lấy từ năm ban hành ghi trong số hiệu văn bản, lưu trong manifest.
    - `document_id` (text). Dùng chung cho 2 file của NĐ 145.
    - `document_type` (`bo_luat` / `nghi_dinh`).
  - **Lý do chọn:** BLLĐ 2012 và 2019 có nhiều Điều gần như giống hệt nhau về chữ nhưng khác con số. Ví dụ: tuổi nghỉ hưu, số giờ làm thêm mỗi tháng (30 so với 40), số ngày nghỉ Quốc khánh (1 so với 2). Vì vậy `year` là trường lọc có giá trị phân biệt thật.
  - **Trường phụ:** `chapter` và `article`, lấy từ tiêu đề gần nhất trước vị trí đầu chunk.

## Cấu hình và benchmark

- **A / B / C:**
  - **A:** chunk cố định 800 ký tự, chồng lấn 100. Điểm cắt lùi về khoảng trắng gần nhất trong phạm vi 40 ký tự để không cắt giữa từ. Không lọc. Có 788 chunk, độ dài median 797.
  - **B:** mỗi Điều một chunk. Điều dài hơn 1500 ký tự thì tách theo Khoản, rồi theo điểm, và chunk con được gắn lại dòng tiêu đề "Điều N. …". Không lọc. Có 714 chunk, median 756, có 3 chunk vượt 1500 ký tự (tối đa 2222) vì một điểm duy nhất đã dài quá giới hạn.
  - **C:** dùng **đúng index và vector của B**. Chỉ khác ở chỗ áp `filter` (`year` hoặc `document_id`) khi câu hỏi có filter. Câu không có filter chạy y như B. Như vậy B–C chỉ khác đúng một yếu tố là filter.
  - Cả ba dùng cùng corpus, cùng model và cùng bộ câu hỏi. A và B có cùng bộ trường metadata, nên A–B chỉ khác cách chia chunk.

- **Bộ câu hỏi:**
  - **Số lượng:** 200 câu, file `starter/benchmark/questions.json`. Chia **160 dev / 40 test trước khi chạy thử**.
  - **Cách chia:** theo Điều. Câu test lấy từ các Điều không dùng cho câu dev.
  - **Loại câu:** 81 trực tiếp, 16 diễn đạt lại, 44 có điều kiện hoặc ngoại lệ, 59 cần filter (46 dev / 13 test).
  - **Nguồn thay thế:** khi BLLĐ 2012 và 2019 cùng chứa câu trả lời đúng, mình ghi cả hai trong `alt_gold`. Ví dụ q003 có ghi chú vì sao bản 2012 *không* phải nguồn hợp lệ: bản 2012 bắt báo trước 3 ngày.
  - **Kiểm chứng evidence:** `scripts/verify_benchmark.py` kiểm tra mọi `evidence_quote` và `alt_gold` đều nằm ở đúng trang PDF sau chuẩn hóa. Kết quả: 200/200 câu khớp. Script cũng kiểm tra số câu dev/test, số câu có filter, và giá trị filter có tồn tại trong manifest.

- **Tiêu chí chọn chiến lược, chốt trước khi chạy** (ghi trong `src/config.py`):
  - Chọn Hit@3 dev cao nhất. Hòa thì xét Hit@1 dev, rồi grounding thủ công, cuối cùng là chi phí và thời gian.
  - Test chỉ dùng để báo cáo, không dùng để chọn. Mẫu chấm tay cũng được cố định trước: 5 câu test đầu (q016–q020) và 10 trang chia đều trong corpus.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 41/160 (25,6%) | 80/160 (50,0%) | 788 | ingest 12,1s · truy vấn 200 câu 5,5s | ingest $0,0065 |
| A | test | 10/40 (25,0%) | 17/40 (42,5%) | | | |
| B | dev | 79/160 (49,4%) | 120/160 (75,0%) | 714 | ingest 7,9s · truy vấn 5,3s | ingest $0,0058 |
| B | test | 20/40 (50,0%) | 28/40 (70,0%) | | | |
| C | dev | **91/160 (56,9%)** | **128/160 (80,0%)** | 714 (dùng chung B) | ingest 0 (dùng lại B) · truy vấn 5,0s | $0 thêm |
| C | test | 22/40 (55,0%) | 29/40 (72,5%) | | | |

Embed 200 câu hỏi, dùng chung cho cả A/B/C: 2,8 giây, khoảng $0,00017. Thời gian chia chunk dưới 0,03 giây. Đọc PDF mất khoảng 16 giây. Tất cả đo trên laptop, mỗi số chỉ từ 1 lần chạy.

**Câu có filter (Hit@3):**

| Strategy | Dev | Test |
|---|---|---|
| A | 16/46 | 4/13 |
| B | 32/46 | 8/13 |
| C | 40/46 | 9/13 |

**Câu có top-3 đúng văn bản yêu cầu:**

| Strategy | Dev | Test |
|---|---|---|
| A | 3/46 | 0/13 |
| B | 5/46 | 0/13 |
| C | 46/46 | 13/13 |

**Evidence bị cắt ngang ranh giới chunk** (chunk chứa một phần đầu hoặc cuối của evidence, đếm trong top-3 của cả 200 câu): A 22 lần, B 0, C 1. Kiểm tra riêng trên chunk (`chunk_stats.json`): evidence của câu dev nằm trọn trong 1 chunk ở A là 157/160 (bị tách: q026, q038, q135), ở B là 160/160.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 1,0 (n=10: 1×0, 8×1, 1×2) | 15/15 | 0/2 câu (0/6 bản ghi) | 2 / 0 / 3, TB 1,2 |
| B | 1,8 (n=10: 0×0, 2×1, 8×2) | 15/15 | 0/2 câu (1/6 bản ghi) | 1 / 0 / 4, TB 1,6 |
| C | 1,8 (dùng chung chunk B) | 15/15 | 2/2 câu (6/6 bản ghi) | 0 / 0 / 5, TB 2,0 |

**Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**
- Trace top-3 đầy đủ: `starter/results/trace_{A,B,C}.jsonl`.
- Chỉ số: `starter/results/metrics.json`.
- Chunk: `starter/results/chunks_{A,B}.jsonl`, thống kê `chunk_stats.json`.
- Lịch sử ingest: `starter/results/ingest_runs.jsonl`. Lần 2 embed 0 chunk, số dòng DB không đổi (788/714), chứng minh nạp lại không trùng.
- Nhãn thủ công: `starter/results/audit_{metadata,grounding,coherence}_labeled.csv`, tổng hợp ở `audit_summary.json`.
- **Mẫu chấm tay:**
  - Metadata và grounding: 5 câu test đầu theo id (q016–q020, có 2 câu có filter) × top-3.
  - Coherence: 10 trang chia đều trên 221 trang. Mốc là 60 ký tự ở giữa trang. Chunk được chấm là chunk chứa mốc đó.
- **Tiêu chí metadata "đủ và đúng":** `source_id`, `document_id`, `page`–`page_end` và `year` khớp PDF và manifest. Cách kiểm tra: dùng script tìm text của chunk trên đúng trang đó. `article` là trường phụ, lỗi được ghi chú nhưng không trừ điểm. Ở A có 4/15 bản ghi mà `article` chỉ đúng với Điều ở đầu chunk, không đúng với Điều chứa evidence.
- **Người chấm:** Nhãn chấm theo tiêu chí trong GUIDE.md, mỗi dòng có lý do.

## Phân tích và kết luận

- **So sánh A–B (chỉ đổi cách chia chunk):**
  - Hit@3 dev tăng từ 80 lên 120/160. Trên cả 200 câu, B đúng thêm 64 câu so với A nhưng sai 13 câu mà A đúng.
  - Coherence tăng từ 1,0 lên 1,8. Evidence bị cắt ngang giảm từ 22 xuống 0.
  - Chunk cố định thường mất đúng chi tiết quan trọng: P07 mất "15 ngày làm việc", P10 mất "5%". P08 bị vỡ bảng công thức thành mỗi dòng một từ.
  - B rẻ hơn khoảng 11% token vì không có phần chồng lấn.
  - **Đánh đổi:** chunk theo Điều dài và gom nhiều ý, nên với câu hỏi nhắm vào một điểm nhỏ trong Điều dài, embedding bị loãng.

- **So sánh B–C (chỉ thêm filter):**
  - C đúng thêm 9 câu và không sai câu nào mà B đúng. Điều này hợp lý vì filter chỉ áp cho câu có filter.
  - Câu có filter ở dev: Hit@3 tăng từ 32 lên 40/46. Top-3 đúng văn bản tăng từ 5/46 lên 46/46. Grounding trên mẫu tăng từ 1,6 lên 2,0.
  - Không tốn thêm chi phí và thời gian ingest.
  - Lọc đúng văn bản **không đảm bảo tìm đúng Điều**: C vẫn sai 10/59 câu có filter.

- **Ví dụ sai:**
  1. **q003 (dev):** "trả lương trễ thì có được nghỉ ngay không cần báo trước?". Gold là BLLĐ 2019 trang 8, Điều 35 khoản 2.
     - A tìm đúng ở #1: chunk cố định tình cờ chứa khoản 2.
     - B sai: top-3 là Điều 97 (2019), Điều 96 và 95 (2012), đều nói về *kỳ hạn trả lương*.
     - Nguyên nhân: Điều 35 dài nên bị tách thành chunk con, và từ khóa "trả lương" kéo câu hỏi về các Điều về tiền lương. Đây là trường hợp chunk theo cấu trúc thua chunk cố định.
  2. **q012 (dev) và q016 (test):** câu hỏi theo BLLĐ 2012.
     - B trả về toàn bản 2019: Điều 169 tuổi nghỉ hưu 62/60; Điều 112 "Quốc khánh: 02 ngày".
     - Grounding của B cho q016 bằng 0, và còn có thể dẫn đến câu trả lời *sai*.
     - C lọc `year=2012` nên tìm ra Điều 187 (trang 52) và Điều 115 (trang 33). Cả hai đều trúng.
  3. **q124 (dev, có filter `year=2012`):** gold là BLLĐ 2012 trang 12, Điều 37 (báo trước 3 ngày làm việc).
     - C lọc đúng văn bản nhưng #1 là Điều 95 (kỳ hạn trả lương).
     - Chunk Điều 38 trang 12 lọt top-3 nhưng không chứa evidence.
     - Filter chỉ thu hẹp phạm vi tìm kiếm, không sửa được lỗi xếp hạng.

- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:**
  - Chọn **C** theo tiêu chí đã chốt: Hit@3 dev cao nhất (128/160). Test xác nhận cùng thứ tự A < B < C.
  - Tuy vậy, trên test C chỉ hơn B đúng 1 câu (29 so với 28/40), nên không đủ để kết luận C hơn B trên tập test.
  - **Điều kiện áp dụng:** C chỉ có lợi khi người dùng hoặc ngữ cảnh *nêu rõ* văn bản hay năm. Trong benchmark, filter được lấy từ chính câu hỏi. Ở ứng dụng thật cần một bước trích filter tự động, và bước đó có thể sai.
  - Nếu câu hỏi không nêu văn bản, C giống hệt B, và vẫn có rủi ro trả về điều khoản của luật đã hết hiệu lực. Một mặc định hợp lý là ưu tiên văn bản còn hiệu lực.

- **Hạn chế của dữ liệu, nhãn, test nhỏ, đo thời gian và chi phí:**
  - **Dữ liệu:**
    - BLLĐ 2019 và 2012 là bản sao trên website trường đại học, không phải bản Công báo.
    - Corpus dùng **nguyên văn 2019**, chưa có các sửa đổi sau này (đã có văn bản hợp nhất 125/VBHN-VPQH năm 2025). NĐ 145 cũng đang có dự thảo sửa đổi năm 2026.
    - Lỗi khoảng trắng trong âm tiết chưa được sửa.
  - **Bộ câu hỏi:**
    - Câu hỏi và đáp án được soạn với hỗ trợ của AI (Claude) từ các câu trích trong corpus.
    - Evidence được kiểm chứng tự động bằng script. `expected_answer` soạn từ evidence.
    - 41/200 câu có `alt_gold`. Phần lớn câu là dạng tra cứu số liệu, ít câu suy luận nhiều bước.
    - Một số câu test nằm cùng Chương với câu dev, nên vẫn có rủi ro rò rỉ.
  - **Nhãn thủ công:**
    - Mẫu nhỏ: 5 câu, 10 vị trí. Một câu test tương đương 2,5 điểm phần trăm.
    - Grounding 2,0 của C trên 5 câu không có nghĩa là C luôn đủ bằng chứng.
  - **Tiêu chí Hit:** yêu cầu chunk chứa *trọn* evidence. Với chunk lớn (B) điều kiện này dễ thỏa hơn với chunk nhỏ, nên chỉ số có phần thiên vị chunk dài.
  - **Đo đạc:** thời gian đo 1 lần trên laptop. Chi phí tính theo bảng giá niêm yết, chưa đối chiếu hóa đơn.

- **Nếu làm lại hoặc mở rộng:**
  1. **Tìm theo khoản, trả theo Điều (parent-child):** embed ở mức khoản hoặc điểm để khớp sát câu hỏi, rồi trả về cả Điều làm ngữ cảnh. Cách này nhắm vào các lỗi kiểu q003.
  2. **Hybrid BM25 + dense:** giúp với câu chứa con số hoặc thuật ngữ cụ thể. Chỉnh trọng số trên dev.
  3. **Tự trích filter từ câu hỏi:** nhận ra "BLLĐ 2012", "Nghị định 145". Mặc định ưu tiên văn bản còn hiệu lực, và đo riêng độ chính xác của bước trích.
  4. **Sửa khoảng trắng trong âm tiết bằng từ điển âm tiết tiếng Việt,** rồi đo lại để xem ảnh hưởng tới embedding.
  5. **Dùng văn bản hợp nhất mới nhất** và thêm metadata `effective_date` / `status` để lọc theo hiệu lực.

## Sử dụng AI và kiểm tra

- **Công cụ:** Claude (Claude Code) hỗ trợ:
  - Tìm và tải nguồn.
  - Soạn bộ câu hỏi từ câu trích trong corpus.
- **Cách kiểm tra:**
  - Evidence được kiểm chứng bằng `verify_benchmark.py` trên PDF gốc.
  - Metadata được đối chiếu với trang PDF bằng script.
  - Học viên tự chạy toàn bộ lệnh và rà lại nhãn thủ công cùng đáp án.
