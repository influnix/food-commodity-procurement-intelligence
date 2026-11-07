# 데이터 및 시점별 정보 가용성 계약

가격의 관측월과 그 가격을 알 수 있는 날짜는 다릅니다. 월평균 가격이 5월 행에 기록돼 있어도 6월 말에 공개되지 않았다면 그날의 발주에 쓸 수 없습니다. 그래서 월 라벨, 공개 시각, 공개 시각의 근거, 수집본 식별자를 분리해 저장합니다.

## 공식 원천과 데이터 구조

가격의 출처는 World Bank Pink Sheet입니다. 당시 수집한 파일의 크기는 586,099bytes이고, 수집시각은 2026-10-24T01:29:17.500704Z입니다. Snapshot `20261024T012917500704Z_ea1c35082787`과 SHA-256 `ea1c350827878ea3bbe30e3cda16a13fd3bd5b409b8458940dc94a36b5a33154`는 당시 저장한 사본을 식별하는 기록입니다. [World Bank Commodity Markets](https://www.worldbank.org/en/research/commodity-markets) · [CMO-Historical-Data-Monthly.xlsx](https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx)

워크북 시트는 Mismatch Details(hidden), Monthly Prices, Monthly Indices, Description, Index Weights입니다. 가격 헤더는 5행, 단위는 6행, 데이터는 7..807행입니다. 날짜는 Excel 일련번호가 아닌 `1960M01` 형식의 텍스트이며 확인된 스키마에는 71개 계열이 있습니다.

미국 Gulf 수출 기준의 HRW를 대표 계열로 골랐습니다. 명목 USD/metric tonne 단위이고, 기존 감사에서 1960-01..2026-09의 801개월에 결측·중복·월 누락이 없었습니다. 별도 US SRW는 1979-01부터 573개 유효 관측과 초기 228개월 결측이 있습니다. Canada CWRS는 설명만 있고 가격 열이 없습니다. 산지와 등급이 다른 가격을 섞으면 발주 정책에서 어떤 지수를 정산 기준으로 보는지 불명확해지므로 HRW 한 계열을 그대로 사용했습니다.

Parser는 `…`, `...`, `..`, 빈 값을 명시적 결측 token으로 보존하며 알 수 없는 문자열·수식·스키마 변경을 거부합니다. 원단위 `($/mt)`는 `USD_per_metric_tonne`로 정규화하며 인플레이션·환율 변환은 하지 않습니다. 월 라벨은 월초 거래가격을 뜻하지 않습니다.

| 필드 | 의미 |
|---|---|
| `date` / `observation_month` | 월평균 관측의 월초 기준 정규 월 라벨 |
| `price` | 추출 결과의 nullable 숫자, 실제·시나리오 가격은 유한한 양수 |
| `commodity`, `unit`, `source_series`, `source_unit` | 정규화한 원재료·단위와 정확한 원계열 식별자 |
| `raw_price`, `source_sheet`, `source_cell`, `is_missing` | 원래 token·셀·결측 상태, 자동 0 대체·보간 없음 |
| `available_at`, `availability_basis` | 확인 가능한 공표 근거 또는 명시적인 다음 달 말 UTC 가정 |
| `vintage_id` | 수집한 수정 Snapshot 식별자, 과거 최초 발표 Vintage가 아님 |

## 사후 수정과 가격 정의 변경

기록된 워크북 갱신일은 2026년 10월 02일입니다. HTTP Last-Modified, 내부 수정시각, 수집시각, 페이지 최초 게시일은 각각 파일이나 페이지의 상태를 설명합니다. 이 정보로 개별 가격의 최초 공표시각을 정할 수는 없습니다. 워크북의 2023/2024 SRW·phosphate 수정과 grain 서식 정정 기록은 같은 가격표도 나중에 수정될 수 있음을 보여줍니다. 과거 최초 발표본은 확보되지 않았으므로 최신 Snapshot과 다음 달 말 UTC 가용 가정으로 재현한 평가는 pseudo-real-time에 해당합니다.

HRW는 2020-06까지 no.1, 2020-07부터 no.2 기준입니다. 확인된 사실은 등급 정의가 달라진 시점입니다. 이후 차이가 품질 때문인지, 통계적 구조단절이 있었는지는 별도 검증이 필요합니다. 경계는 메타데이터에 표시하고 모든 관측을 유지했습니다. 기존 개발 감사에서 사전 20% 절대변동 기준을 넘은 7개월도 그대로 남겼습니다.

완전 벡터의 경계 교차는 `o−1 < 2020-07 ≤ o+3`이며 2020-04..07의 4개 origin입니다. 변경 전후 또는 교차 표본 제외는 별도 민감도 가정이며, 임의의 넓은 구간을 제거하는 누수 방지 규칙으로 혼동하지 않습니다.

## 평가 달력과 타깃 성숙

| 계약 | 기간 |
|---|---|
| Train target |1960-01..2021-06, 첫 Validation 학습에는 2021-05까지만 사용 |
| Validation origin |2021-06..2024-05, 36개 origin×3horizons |
| Validation target·구매 원장 |2021-07..2024-08, 38개 고유 월, Active35/Runoff3 |
| Bridge |2024-09, 선택·채점에서 제외 |
| 최종 계획 origin |2024-09..2026-06, 22개 |
| 잠긴 최종 원장 |2024-10..2026-09, 24개월, Active21/Runoff3 |

월말 의사결정 `d_t`의 정보집합은 `m≤t−1`, `available_at(m)≤d_t`인 관측만 포함합니다. 납품 Horizon `h=1,2,3`의 target은 `t+h`이며 최신 관측 기준 model step 2,3,4입니다. 완전 벡터 학습 조건은 다음과 같습니다.

```math
o<t,\qquad o+3\le t-1,\qquad \max_h available\_at(P_{o+h})\le d_t.
```

`o≤t−4`는 달력상 필요한 조건입니다. 마지막 label이 그보다 늦게 공개되면 해당 사례는 더 기다려야 합니다. 정적 분할의 target 집합은 서로 분리하고, 한 fold 안에서도 학습과 채점 target을 분리합니다. 과거 Validation label은 고정 사양 아래 성숙한 뒤 후속 expanding 학습에 들어갈 수 있습니다. 시간 순서와 공표 조건으로 학습 범위를 정하므로 Random Split·전체 표본 전처리·불필요한 대칭 embargo는 사용하지 않습니다. 서로 다른 origin에서 같은 달을 예측하는 Validation의 target 공유는 그 평가 구조에서 생깁니다.

## Legacy와 현재 실행의 증거

저장된 archive는 모델별 Historical60(2016-04..2021-03)+Validation36으로, 192개 model-origin batch·576개 예측입니다. 기존 558개 잔차와 이미 발행된 예측의 추가 target 연결 18개를 과거에 감사했습니다. 미발행 2024-06..08 예측을 보충하지 않습니다.

`LegacyReconstructedForecast`는 RECONSTRUCTED_ASOF로 유지하며 원래 ID·row/file/manifest/model/snapshot hash를 보존합니다. 당시 실시간 발행·원래 Native 입력 bytes·세션 증거는 없습니다. `NativeIssuedForecast`는 현재 실행 publisher 등록과 성공한 실제 백엔드 학습 증거를 요구합니다. Native 이력 hash는 현재 메모리 입력을 설명하며 과거 World Bank 원천 bytes를 입증하지 않습니다. 합성 Legacy/Native 통과를 실제 원천 검증으로 승격하지 않습니다.

## 실제 접근 제한과 배포 범위

별도로 제공돼야 하는 비Holdout Export는 1960-01..2024-08의 776개월이며, observation_month/price/unit/source_series/available_at/availability_basis/vintage_id 7열입니다. 제안 경로는 `data/approved_exports/final/wheat_history_through_202408.csv`입니다. 경로·목적·범위의 명시 승인, CSV byte hash, 생성 Manifest 원본 파일 byte hash·canonical content hash, 독립적인 생성·원천 연결 증거가 필요합니다.

순수 validator는 제공된 bytes의 계약만 검사하며 접근 권한을 부여하지 않습니다. 출처 증거 부족은 PROVENANCE_INCOMPLETE, 승인 부재는 ACCESS_APPROVAL_REQUIRED입니다. 별도 권한 없이 801개월 혼합파일을 읽거나 필터링·재해시해 Export를 만들지 않습니다.

실제 Bridge/Holdout과 학습·평가는 계속 금지됩니다. 가정상 성숙 Threshold 2026-10-31T23:59:59Z는 역사적 실제 공표 증거나 사용자 권한과 별개입니다. 실제 Source Export·Seed Runtime은 NOT_VERIFIED입니다.

과거 출처 기록은 [World Bank 이용조건](https://data.worldbank.org/summary-terms-of-use)과 [라이선스 안내](https://datacatalog.worldbank.org/public-licenses)를 인용했습니다. CC BY4.0·기본 조건에 추가 조건이나 제3자 예외가 있을 수 있습니다. 저장소는 코드와 선별 집계만 제공하고 원천·파생 가격 행은 배포하지 않습니다. 소유자를 대신해 코드 라이선스를 선택하지 않으며 World Bank의 보증을 암시하지 않습니다.
