# Day17 제한 원천 검증 범위

2026-11-01 Asia/Seoul. **실제 데이터 접근 승인은 없습니다. REAL_SOURCE_NOT_VERIFIED / ACCESS_APPROVAL_REQUIRED**입니다. Export 파일을 생성하거나 원천 CSV를 열지 않았습니다. Bridge·Holdout·실제 학습/구매평가·Unlock은 계속 금지입니다.

## 접근 분리

| 범위 | 현재 허용/실행 |
|---|---|
| A 기존 저장 evidence | 기존 pin/기간이 확인된 Day5 forecast·OOF·fit log, Day9 Validation evidence, Day16 audit, manifest·설정·코드만 읽음 |
| B 제안 Source export |1960-01~2024-08·776개월 HRW·nominal USD/t. 생성·읽기 미승인, 실제 파일 검증 없음 |
| C Bridge/Holdout |2024-09 및2024-10~2026-09 실제가격 미접근. 실제 Reader/평가 CLI 비활성 |

제안 경로는 `data/approved_exports/final/wheat_history_through_202408.csv`입니다. 경로가 있다는 이유로 파일이 존재하거나 읽기 승인됐다고 가정하지 않습니다. 기존801개월 혼합 CSV를 로딩한 뒤 걸러내거나 전체 재해시하지 않습니다.

## Restricted Source Validator

구현은 [restricted_source.py](../src/food_procurement_intelligence/data/restricted_source.py)입니다. 별도로 취득한 bytes를 검사하는 **순수 검증 함수**이며 실제 파일 loader/승인 발급 API가 없습니다. `require_real_source_verification`은 exists/open/hash 전에 항상 ACCESS_APPROVAL_REQUIRED로 거부합니다.

검사 항목은 정확한 제안 경로, World Bank HRW identity·단위,776개 고유·연속·오름차순 월,1960-01/2024-08 경계, 누락/중복, 숫자·유한·양수 price, 정확한7개 열, series·snapshot/vintage·가정 available_at, export SHA, 외부에 pin한 generation-manifest SHA, 생성 근거/생성자와 기존 원천 metadata 연결입니다. 모든 날짜 범위를 확인한 뒤 price를 숫자로 해석합니다. Bridge/Holdout 혼입·열/기간 확장·잘못된 공표 가정을 거부합니다.

Export SHA는 전달받은 CSV bytes의 SHA-256입니다. 순수 함수의 manifest pin은 `json.dumps(manifest, sort_keys=True, ensure_ascii=False)`를 UTF-8로 인코딩한 canonical JSON content SHA-256입니다. 아직 존재하지 않는 manifest 파일의 byte SHA를 오늘 확인했다는 뜻이 아닙니다. 실제 제공 단계에는 canonical content pin과 별도로 원본 manifest 파일 byte hash/생성 근거를 기록해야 합니다.

허용 열은 observation_month, price, unit, source_series, available_at, availability_basis, vintage_id입니다. available_at은 관측 다음 달 말 UTC라는 기존 가정이며 첫 발표 timestamp의 증거가 아닙니다. latest snapshot ID와 실제 과거 vintage를 구분합니다.

Day1 extraction manifest는 기존 day2 설정의 SHA로 검사하며, 그 안의 raw snapshot ID·기록된 raw SHA·raw manifest 경로를 export-generation manifest와 연결합니다. 원래 raw manifest/혼합 가격 byte를 새로 확인한 것은 아닙니다. Manifest SHA의 일치는 무결성이지 생성자의 사실 주장·권한을 자동 보증하는 서명이 아닙니다. 실제 검증에는 승인된 생성 근거와 외부 pin이 필요합니다.

합성776개월 schema fixture는 메모리에서만 만들고 제안 data 경로에는 쓰지 않습니다. Fixture의 source/series/snapshot은 검증할 참조 metadata이며 가격은 명시적인 toy100+i/100입니다. Fixture의 고정 generated_at은 테스트 시각이며 실제 source 수집/승인 시각이 아닙니다. 정책 실험 world로 사용하지 않습니다. 통과 결과도 REAL_SOURCE_NOT_VERIFIED를 유지합니다.

## Access Approval Request Specification

정확한 명세는 `artifacts/day17/access_approval_request.json` 및 정본 bundle에 있습니다.

- 원래 혼합 파일: `data/processed/world_bank/20261024T012917500704Z_ea1c35082787__20261024T013704254799Z/wheat_us_hrw.csv`.
- 제안 결과: `data/approved_exports/final/wheat_history_through_202408.csv`,1960-01~2024-08·776개월·위7열만 포함.
- 생성 방식: 데이터 소유자가 별도로 승인받은 범위에서 준비한 비Holdout 전용 export와 생성 manifest를 제공. 이번 코드가 혼합801행을 읽어 필터링하지 않음.
- 목적: source identity·초기 이력·seed/source 연결과 실제 fit input을 제한된 범위에서 독립 확인.
- 확인할 새 hash: export byte SHA-256, 생성 manifest SHA-256, 생성 코드/방법 증거와 기존 extraction manifest SHA. 아직 없는 export/manifest hash는 null로 남기며 만들어 채우지 않음.
- 이전 기록만 활용하는 hash: raw XLSX `ea1c350827878ea3bbe30e3cda16a13fd3bd5b409b8458940dc94a36b5a33154`, 혼합 CSV `f5bc6a5a859285f0dd0ece5cea03d820a37efff157484fd31b45242cc4946025`. 오늘 재해시하지 않음.
- B 범위 승인은 C Bridge/Holdout·실제 평가/fit 승인으로 확대되지 않음.

Historical Vintage, Actual Historical Release Timestamp, Contemporaneous Live Forecast Issuance는 NOT_VERIFIED, available_at은 ASSUMED_PUBLICATION_TIME, latest snapshot은 previously documented source입니다. 실제 export가 확인돼도 과거 vintage가 자동 검증되지 않습니다. 한계를 명시적으로 수용한 pseudo-real-time historical simulation과 모든 역사 출처의 PASS 판정은 다릅니다.
