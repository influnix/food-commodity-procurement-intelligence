# 데이터 및 시점별 정보 가용성 계약

## 공식 원천과 데이터 구조

기록된 출처는 [World Bank Commodity Markets](https://www.worldbank.org/en/research/commodity-markets)의 Pink Sheet 월별 과거 원자재 가격입니다. 수집 파일은 [CMO-Historical-Data-Monthly.xlsx](https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx)이며, 수집시각은 2026-10-24T01:29:17.500704Z, 크기는 586,099bytes입니다. Snapshot은 `20261024T012917500704Z_ea1c35082787`, SHA-256은 `ea1c350827878ea3bbe30e3cda16a13fd3bd5b409b8458940dc94a36b5a33154`입니다. 이는 과거 수집 메타데이터이며 문서화 작업에서 원천 가격을 다시 열거나 해시하지 않습니다.

워크북 시트는 Mismatch Details(hidden), Monthly Prices, Monthly Indices, Description, Index Weights입니다. 가격 헤더는 5행, 단위는 6행, 데이터는 7..807행입니다. 날짜는 Excel 일련번호가 아닌 `1960M01` 형식의 텍스트이며 확인된 스키마에는 71개 계열이 있습니다.

HRW는 미국 Gulf 수출 기준의 명목 USD/metric tonne 계열입니다. 기존 감사에서 1960-01..2026-09의 801개월에 결측·중복·월 누락이 없음을 확인했습니다. 별도 US SRW는 1979-01부터 573개 유효 관측과 초기 228개월 결측이 있습니다. Canada CWRS는 설명만 있고 가격 열이 없습니다. 계열을 평균내거나 결측을 임의로 채우지 않았습니다.

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

기록된 워크북 갱신일은 2026년 10월 02일입니다. HTTP Last-Modified·내부 수정시각·수집시각·페이지 최초 게시일은 서로 다르며 각 과거 관측의 최초 공표시각을 입증하지 않습니다. 워크북에는 2023/2024 SRW·phosphate 수정과 grain 서식 정정이 기록돼 있습니다. 최신 Snapshot만으로 역사적 Vintage를 복원할 수 없습니다.

HRW는 2020-06까지 no.1, 2020-07부터 no.2 기준입니다. 모든 관측과 정의 경계 메타데이터를 유지합니다. 통계적 구조단절이나 품질의 인과적 가격효과가 입증된 것은 아닙니다. 기존 개발 감사에서 사전 20% 절대변동 기준을 넘은 7개월도 그대로 보존했습니다.

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

따라서 `o≤t−4`가 필요하지만 공표가 늦으면 추가로 제외해야 합니다. 정적 구간의 target 집합과 현재 fold의 평가 target·학습 target은 겹칠 수 없습니다. 과거 Validation label은 고정 사양 아래 성숙한 뒤에만 후속 expanding 학습에 들어갑니다. Random Split·전체 표본 전처리·불필요한 대칭 embargo는 사용하지 않습니다. Validation Horizon 간 target 공유와 의존성은 의도된 평가 구조입니다.

## Legacy와 현재 실행의 증거

저장된 archive는 모델별 Historical60(2016-04..2021-03)+Validation36으로, 192개 model-origin batch·576개 예측입니다. 기존 558개 잔차와 이미 발행된 예측의 추가 target 연결 18개를 과거에 감사했습니다. 미발행 2024-06..08 예측을 보충하지 않습니다.

`LegacyReconstructedForecast`는 RECONSTRUCTED_ASOF로 유지하며 원래 ID·row/file/manifest/model/snapshot hash를 보존합니다. 당시 실시간 발행·원래 Native 입력 bytes·세션 증거는 없습니다. `NativeIssuedForecast`는 현재 실행 publisher 등록과 성공한 실제 백엔드 학습 증거를 요구합니다. Native 이력 hash는 현재 메모리 입력을 설명하며 과거 World Bank 원천 bytes를 입증하지 않습니다. 합성 Legacy/Native 통과를 실제 원천 검증으로 승격하지 않습니다.

## 실제 접근 제한과 배포 범위

별도로 제공돼야 하는 비Holdout Export는 1960-01..2024-08의 776개월이며, observation_month/price/unit/source_series/available_at/availability_basis/vintage_id 7열입니다. 제안 경로는 `data/approved_exports/final/wheat_history_through_202408.csv`입니다. 경로·목적·범위의 명시 승인, CSV byte hash, 생성 Manifest 원본 파일 byte hash·canonical content hash, 독립적인 생성·원천 연결 증거가 필요합니다.

순수 validator는 제공된 bytes의 계약만 검사하며 접근 권한을 부여하지 않습니다. 출처 증거 부족은 PROVENANCE_INCOMPLETE, 승인 부재는 ACCESS_APPROVAL_REQUIRED입니다. 별도 권한 없이 801개월 혼합파일을 읽거나 필터링·재해시해 Export를 만들지 않습니다.

실제 Bridge/Holdout과 학습·평가는 계속 금지됩니다. 가정상 성숙 Threshold 2026-10-31T23:59:59Z는 역사적 실제 공표 증거나 사용자 권한과 별개입니다. 실제 Source Export·Seed Runtime은 NOT_VERIFIED입니다.

과거 출처 기록은 [World Bank 이용조건](https://data.worldbank.org/summary-terms-of-use)과 [라이선스 안내](https://datacatalog.worldbank.org/public-licenses)를 인용했습니다. CC BY4.0·기본 조건에 추가 조건이나 제3자 예외가 있을 수 있습니다. 저장소는 코드와 선별 집계만 제공하고 원천·파생 가격 행은 배포하지 않습니다. 소유자를 대신해 코드 라이선스를 선택하지 않으며 World Bank의 보증을 암시하지 않습니다.
