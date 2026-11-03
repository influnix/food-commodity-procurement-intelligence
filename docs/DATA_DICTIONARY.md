# 데이터 사전 및 출처 상태

Day 1 가격 CSV, Day 2 sample calendar, Day 3 validation 특징/점예측 CSV가 구현됐습니다. 그 밖의 quantile·운영·기상 표는 예정 스키마입니다. `month`는 `YYYY-MM`, timestamp는 timezone-aware UTC, 수량은 metric tonne(t), 운영비용은 USD, fraction은 0~1입니다.

## 원천과 확인 범위

| 원천 | 용도와 오늘 확인한 범위 | 미확정 / 다음 확인 |
|---|---|---|
| [World Bank Commodity Markets](https://www.worldbank.org/en/research/commodity-markets) | 공식 월별 XLSX 확보. Monthly Prices 71개 가격/지수 계열 열, 1960-01~2026-09의 801개 월 행. Wheat 가격 열 HRW/SRW 확인 | snapshot별 출처·품질·정의 변경은 [출처 기록](WORLD_BANK_SOURCE.md) 참조. 과거 최초 발표 버전과 개별월 공표 timestamp는 미확보 |
| [NASA POWER Daily API 문서](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) | 일별 기상 서비스와 시간 기준 설명만 읽음; API 미호출 | 생산지역·좌표, 파라미터명/단위, 집계법, 가용 지연, 결측 플래그, vintage |

확인일: 2026-10-24 Asia/Seoul. 대표 계열은 `Wheat, US HRW`, 원단위 `($/mt)`, 정규화 단위 `USD_per_metric_tonne`입니다. `Monthly Prices!A2:A3`의 nominal US dollars 설명을 함께 검증하므로 통화 추측 없이 항등 변환합니다. `Soybean oil`은 Z5의 실제 헤더/단위만 확인했으며 추출·분석하지 않았습니다. 날씨 값은 미확보입니다.

## Day 1 CSV: 현재 구현된 가격 관측표

파일은 계열별 하나이며, 키는 `(commodity, source_series, observation_month, vintage_id)`입니다. 다른 Wheat 계열을 혼합하지 않습니다. 전체 801개 월 라벨을 유지하므로 SRW는 초기 228개 행의 price가 null입니다.

| 필드 | Python 타입 / CSV 표현 | 의미 |
|---|---|---|
| `date` | `date` / ISO `YYYY-MM-01` | 월초를 사용한 월 라벨. 실제 월초 체결가격 아님 |
| `observation_month` | `str`, `YYYY-MM` | 원본 `YYYYMmm`과 대응하는 관측월 |
| `price` | `float` 또는 `None` / 숫자 또는 빈 필드 | 해당 월 nominal USD/t, 유효값은 finite·양수. 변환/보간으로 누락값 생성 안 함 |
| `commodity` | `str` | 내부 그룹 ID `wheat`; 단독으로 서로 다른 Wheat의 유일키가 아님 |
| `unit` | `str` | `USD_per_metric_tonne` |
| `source_series`, `source_unit` | `str` | 실제 헤더 `Wheat, US HRW` 또는 `Wheat, US SRW`, 원단위 `($/mt)` |
| `source_sheet`, `source_cell` | `str` | `Monthly Prices`와 `AL7` 등의 원본 위치 |
| `raw_price` | `str` 또는 `None` | XML literal 원문. missing token도 그대로 유지 |
| `is_missing` | `bool` / `True`·`False` | 빈 가격 필드와 원문 token을 함께 해석할 때 사용 |
| `available_at` | ISO UTC `str` | 관측월 다음 달 말 23:59:59, 실제 발표 timestamp가 아닌 보수적 모델 가정 |
| `availability_basis` | `str` | `assumed_observation_month_plus_one_month_end` |
| `vintage_id` | `str` | 다운로드 snapshot ID. 당시 최초 공표 vintage라는 의미가 아님 |

원본 결측 표현은 실제 셀에서 관찰한 `…` (U+2026), `...`, 빈 셀을 지원합니다. `Description!B130`에 설명된 `..`도 명시적으로 지원하지만 이번 Wheat 셀에서는 관찰되지 않았습니다. SRW의 초기 228개 결측은 모두 U+2026입니다. 알 수 없는 문자열·Excel 오류·0·음수·비유한 가격은 변환 실패로 처리합니다. CSV에는 타입 정보가 없으므로 재로딩 시 `price`를 nullable numeric, `date`를 월 라벨, `is_missing`을 boolean으로 명시적으로 해석해야 합니다.

`data/processed/world_bank/<run_id>/`에 두 CSV를 보관하고, `artifacts/day1/<run_id>/extraction_manifest.json`에 파일별 해시·설정 사본·parser 코드 해시·Python 버전을 저장합니다. 같은 원본/설정으로 재추출하면 CSV 바이트가 재현되며 run timestamp만 달라집니다. 과거/새 run을 덮어쓰지 않습니다.

## 실제 자료

### Source snapshot manifest

키: `snapshot_id`. 필드: `source`, `landing_url`, `download_url`, `local_path`, `retrieved_at_utc`, `sha256`, `vintage_id`, `license_url`, `license_status`, `parser_version`, `publication_timestamp` (불명 시 null), `notes`.

`data/raw/<source>/<snapshot_id>/`에 원본과 manifest를 같이 보관합니다. 원본 변경 금지. null은 불명이고 0은 실제 수치입니다. 다운로드와 다운로드 실패를 구분합니다.

### 통합 Price observations: Day 2 이후 확장할 설계

키: `(commodity_id, observation_month, vintage_id)`.

| 필드 | 의미 / 검증 |
|---|---|
| `commodity_id`, `source_series_name` | 내부 ID, 원천의 정확한 헤더; 여러 Wheat 계열을 합치지 않음 |
| `observation_month`, `price_value`, `source_unit` | 원천의 월평균 가격과 원단위; 파싱 전후 비교 |
| `price_usd_per_tonne`, `conversion_rule` | 검증된 변환 결과와 공식; 근거 없으면 null/실행 차단 |
| `available_at`, `availability_basis` | 실제 발표일 또는 `assumed_month_lag`; 최신 파일의 과거 정보 한계 명시 |
| `vintage_id`, `snapshot_id`, `is_missing` | 출처 연결과 결측 표시; 가격 보간으로 타깃을 만들어내지 않음 |

검증: 월 순서, 월 빈도·누락, 양수 가격, 키 유일성, 원단위 일관성, 공표월 모순, 시작/종료월, 이상치 사유. 전체 시계열 통계로 특징을 표준화하지 않습니다.

### Weather observations (MVP 기본 비활성)

키: `(region_id, observation_date, parameter, vintage_id)`.
필드: `latitude`, `longitude`, `time_standard`, `value`, `unit`, `available_at`, `availability_basis`, `snapshot_id`, `is_missing`. 집계표는 `observation_month`, `aggregation` (기온 평균/강수 합 등), `valid_days`, `expected_days`, `available_at`, `regional_weight_basis`를 추가합니다. 결측 플래그를 0 강수량으로 변환하지 않습니다. 한 좌표를 세계 생산량의 대표값으로 단정하지 않습니다.

## 예측 및 의사결정 입력

### Day 2 sample calendar: 현재 구현된 날짜 metadata

`artifacts/day2/<run_id>/sample_calendar.csv`는 가격을 포함하지 않습니다. 키는 `(origin_month, horizon)`입니다. 다음 필드를 저장합니다.

| 필드 | 의미 |
|---|---|
| `origin_month`, `decision_at` | 월 라벨, 해당 UTC 월말 decision timestamp |
| `feature_cutoff_month` | `origin_month-1`; 가격 이력은 실제 availability도 추가 검사 |
| `horizon`, `target_month` | business horizon 1/2/3, `origin+horizon` |
| `steps_from_latest_observation` | 기본 1개월 공표 지연에서 2/3/4 |
| `evaluation_history_ready` | 해당 origin에 최소 120개월의 원시 과거 이력이 있는지 표시. 과거 학습 후보의 일괄 삭제 조건이 아님 |
| `target_partition` | `train`, `validation`, `bridge`, `holdout`; vector 단위 완전 포함 여부는 별도 마스크로 확인 |
| `crosses_definition_boundary` | `feature_cutoff < 2020-07 <= target_month`. 감사 메타데이터이며 기본 모델 특징/삭제 조건이 아님 |

calendar 자체는 실제 값/모델 입력이 아닌 **구조적 후보 목록**입니다. 실제 값은 `load_development_store(...).history_as_of(origin)` 등에서 t-1 및 공표 timestamp를 검사해 읽습니다. bridge와 holdout 값은 개발 API에서 숨깁니다. 분할 설정·후보 비교·수학적 범위는 [분할 설계](SPLIT_DESIGN.md), 실제 기본 품질 결과는 [데이터 감사](DATA_AUDIT.md)를 따릅니다.

### Day 3 Validation 특징·점예측: 현재 구현

`validation_features.csv`의 키는 `(forecast_origin,horizon)`이며 108행입니다. 기본 metadata는 `forecast_origin`, `feature_asof_at`, `information_cutoff`, `target_month`, `horizon`, `price_unit`입니다. 별도 15개 feature 열은 [Day 3 명세](FEATURES_AND_BASELINE.md)를 따릅니다. `feature_provenance.json`은 각 feature의 원천 월과 가장 늦은 공표시각, known-in-advance calendar 목록을 같은 키에 연결합니다. 실제 현재 생성 시각은 run manifest의 UTC 시각이고 `feature_asof_at`은 과거 결정 시점의 모의 정보 시각입니다.

`validation_predictions.csv`의 키도 `(forecast_origin,horizon)`입니다. `target_month` 단독은 중복이 정상입니다.

| 필드 | 의미 |
|---|---|
| `forecast_origin`, `information_cutoff`, `target_month`, `horizon` | 월 라벨 t, t-1, t+h, business horizon |
| `forecast_asof_at`, `steps_from_latest_observation` | 모의 정보 시각 d_t, 2/3/4 step |
| `predicted_price`, `actual_price`, `unit` | point forecast, validation actual, nominal USD/t |
| `error`, `absolute_error` | actual-predicted, 그 절댓값 |
| `reference_month`, `reference_available_at`, `model_name` | target-12, 참조 관측의 공표시각, `seasonal_naive_12` |
| `mase_scale`, `mase_scale_status`, `scaled_error` | 해당 origin의 as-of scale, 상태, abs_error/scale |
| `fixed_initial_scale`, `fixed_initial_scaled_error` | 첫 fold 가용 이력으로 고정한 보조 scale과 ratio |
| `actual_available_at`, `assessed_at` | 정답의 공표시각, 별도 evaluator의 2024-09 말 채점 clock |

`fold_audit.csv`는 36행으로 history 길이/최신 월, 성숙한 학습 후보 수, 마지막 성숙 origin, 두 scale·상태·seasonal pair 수를 저장합니다. Seasonal Naive의 `supervised_model_fit`은 false입니다. `metrics.json`은 전체/horizon/origin별 MAE·MASE·정의 개수·누락 키를 보유합니다. 실패는 `failures.json`에 별도 기록합니다. 숫자는 CSV 로딩 시 명시적으로 변환하며 undefined scale/ratio는 빈 필드 또는 JSON null입니다. 이번 실제 결과는 108쌍 모두 정의됐습니다.

모든 actual은 고정 validation 범위에 속합니다. bridge/holdout actual을 포함하는 행은 생성하지 않았습니다. Day 1 raw/processed 가격 CSV와 Day 2 날짜 catalog는 변경하지 않았습니다.

### 통합 Forecasts: 추가 모델·quantile용 예정 스키마

Day 4 point prediction 구현: 신규 두 모델은 `forecasting/common.py`의 ModelPrediction에 origin/cutoff/target/horizon/predicted_price/model_name/unit을 보유하고 record에 forecast_asof_at와 step을 추가합니다. Seasonal Naive는 기존 schema와 adapter를 유지합니다. 신규 모델에 target-12 참조 필드를 억지로 채우지 않습니다. 확장 metadata는 `fold_fit_log.json`의 train_n/범위/경고/수렴/시간/설정 및 mask로 분리합니다. 아래의 quantile/run 통합 계약은 여전히 후속 확장입니다.

`artifacts/day4/<model_run>/predictions.csv`는 validation 정답과 Day 3와 동일한 오차/scale 열을 갖습니다. 키는 (model_name,forecast_origin,horizon)이고 실패 키는 metrics의 missing_keys에 남깁니다. `model_comparison.csv`와 `common_success_comparison.csv`는 모델별 성공 집합과 전 모델 공통 성공 교집합을 구분합니다. 비교 개선율은 baseline과 같은 키/scale/actual에서만 허용합니다.

키: `(run_id, model_id, commodity_id, decision_at, target_month, quantile)`; 점예측은 별도 `forecast_kind=point`와 null quantile로 구별합니다.
필드: `last_observed_month`, `delivery_offset_months`, `steps_from_last_observation`, `predicted_price_usd_per_tonne`, `trained_through_available_at`, `training_snapshot_ids`, `calibration_id`.

`target_month > decision_month`, `trained_through_available_at <= decision_at`; q10<=q50<=q90, 가격>0을 검사합니다. 위반 시 사전 정의된 fold-local 교정/실패 규칙을 적용하고 빈도를 보고합니다.

### Demand beliefs와 policy context

`(issued_at, target_month)`별 `expected_demand_tonnes`, 선택적 수요분포 ID, `knowledge_type=simulated_forecast`를 저장합니다. 실제 수요와 다른 테이블입니다.

context에는 `decision_at`, `on_hand_tonnes`, 알려진 `open_orders`, `supplier_contracts`, `demand_beliefs`, 해당 origin `forecasts`, `information_cutoff`만 포함합니다. 실제 외생 scenario, 미래 actual, 최종 평가 seed는 포함하지 않습니다.

## 가상 자료와 거래 ledger

| 테이블 / 키 | 필수 필드 | 단위·경계 |
|---|---|---|
| supplier_contracts / `(supplier_id, valid_from)` | premium, base lead, capacity, 알려진 delay distribution, valid_to | 무차원, 월, t/발주월; 값은 가상 |
| scenario_paths / `(scenario_id, month, supplier_id)` | realized demand, order-month delay, price multiplier, seed streams | 실제 기본가격은 별도 참조; 충격 경로는 synthetic 표시 |
| orders / `order_id` | policy_id, decision_at, supplier, quantity, expected_receipt_month, contract_version | t; 미래 실제 수령월은 정책 출력에 없음 |
| receipts / `receipt_id` | order_id, actual_receipt_month, quantity, index_month, realized_unit_cost | t, USD/t; 엔진이 기록 |
| inventory_ledger / `(run_id, policy_id, scenario_id, month)` | opening, arrivals, demand, served, lost_sales, disposal, closing, procurement_cost, holding_cost, shortage_cost, disposal_cost | t, USD; 재고 보존 및 비용 합계 검사 |
| policy_metrics / `(run_id, policy_id, scenario_id)` | cost components, terminal_cost, total_cost, unmet_ratio, fill_rate, stockout_month_ratio, cost_cvar | 모든 정책 동일 기간·회계 정의 |

실제 가격 경로에 `price_multiplier`를 곱한 스트레스 가격은 `stressed_price`라는 파생 합성 경로입니다. 실제 시장 관측표를 덮어쓰지 않습니다. 주문량이 달라도 같은 공급업체·발주월 지연 추첨을 참조합니다.

## 실행 manifest

`run_id`, `created_at_utc`, `code_commit_or_source_hash`, `python_version`, `package_versions`, `config_copy`, `config_sha256`, `snapshot_ids`, `data_hashes`, `split_dates`, `origin_list`, `seed_streams`, `scenario_ids`, `solver_statuses`, `holdout_access_status`, `vintage_mode`, `warnings`를 기록합니다.

원본/실험 대용량 결과는 Git에 넣지 않습니다. 검증된 작은 최종 보고서·집계표를 공개할 때는 출처·가정·라이선스와 재현 경로를 함께 담습니다. Day 0에는 `.gitkeep`만 존재했고, Day 1에는 별도 snapshot과 추출 run이 추가됐습니다. 기본 원본 크기·해시 등 공개 가능한 요약은 [출처 기록](WORLD_BANK_SOURCE.md)에도 보존합니다.

## Day 5 별도 불확실성 계약

[필드 표와 정의](DAY5_UNCERTAINTY_DESIGN.md)의 `UncertaintyPrediction`을 사용합니다. 기존 Day 4 `ModelPrediction`을 변경하지 않습니다. run 내부 유일 키는 `(model_name, forecast_origin, horizon, uncertainty_method)`이며 nominal USD/metric tonne와 논리 forecast_asof_at을 보존합니다. Raw SARIMAX 평균과 LightGBM L2는 point_prediction, LightGBM q50은 별도 출력입니다. 보정 행은 q10/q50/q90를 null로 두고 원본을 base_q10/base_q50/base_q90에 남깁니다.

`all_oof_forecasts.csv`는 Train/validation의 원본 예측과 학습 proof를 저장하며 미래 실제값은 없습니다. `historical_oof_calibration.csv`, `validation_oof_calibration.csv`는 마지막 validation clock까지 실제 공표된 오차만 담습니다. 아직 성숙하지 않은 validation 오차는 `pending_oof_metadata.json`에 날짜만 남기고 보정 표에는 넣지 않습니다. 잔차 표에는 source_model/source_method, residual_forecast_origin/target_month/horizon, residual_actual_available_at, residual_value, calibration_score, actual_price, fit proof, first_released_at_origin, phase가 있습니다. Audit의 calibration_origin/선택 잔차 키와 결합해 각 시점의 보정 입력을 재현합니다.

실제 validation 채점 열은 모델·보정 결과가 모두 생성된 후 추가합니다. 원본 구간 두 파일과 보정 구간 파일에는 같은 validation actual이 있으며 bridge/holdout label은 없습니다. Calibration residual_value는 actual−point이고 사용 score는 `max(lower−actual, actual−upper,0)`입니다. 원본 fitting residual이 아닙니다. `risk_signals.csv`의 event_probability는 빈 값이며 세 분위수에서 확률을 추측하지 않습니다.

## Day 6 공동 경로·가상 거래 계약

`joint_price_scenarios.csv`의 키는 `(purpose, source_model, forecast_origin, scenario_id, horizon)`입니다. 같은scenario_id는 세h에 같은 source_oof_origin·probability를 공유합니다. 확률 합은h행 전체가 아니라 경로별로 한 번씩 계산합니다. 필드는 target_month·price·unit·seed·method·pool_sha256·논리asof·information_cutoff·knowledge_type이며, 가격은 실제 target 관측이 아닌 경험적 시뮬레이션입니다.

`joint_oof_vectors.json`은 construction_origin별 선택pool과 과거source origin·모델·3개target·공표 timestamp·fit proof·point·공개actual·signed error·양수ratio를 저장합니다. 동일과거vector가 여러현재pool에 반복될 수 있어 record 수가 독립 표본 수는 아닙니다. Availability audit는 incomplete/future/immature와window 전후 개수를, diagnostics는population divisor n의평균·분산·상관과유효성을 담습니다.

`Supplier`는 premium·lead·월capacity·MOQ·multiple·명목/최대delay·운송단가를 갖는 가상 계약입니다. 수량은metric tonne, 시장/납품단가는USD/t, 비용은USD입니다. `ToyWorld`는 공개시각이 있는 인공 가격·월별 실현수요·발주월/업체별delay를 보유하며 엔진 전용입니다. `DecisionContext`는 현재 재고·수요계획·공개계약·promised/overdue pipeline·공표가격만 갖습니다. 미래 실제 경로나 ledger 단가/비용을 포함하지 않습니다.

Toy의 `*_orders.csv`는 발주 ID·업체·발주월·수량·promised·초기pipeline 여부를, `*_receipts.csv`는 실제수령월·수량·납품월시장가격·premium단가·매입/운송비·비용귀속시각·가격공표시각을 기록합니다. `*_ledger.csv`는 월초재고·기존미착량·입고·available·실현/충족/미충족수요·폐기·월말재고·신규발주·기말미착·비용구성·총비용을 저장합니다. Lost sales와폐기·종료비는구분하며미착량은재고가아닙니다.

가상 공급 가정과 Toy 입력은 `data/synthetic/day6/<run>/`에 버전·단위·합성label과 함께 둡니다. 실제원본/processed와 Day 5 결과는 변경하지 않았습니다. [Day 6 설계와 손계산](DAY6_DESIGN.md)이 정확한 가정과 수식의 기준입니다.

## Day 7 계획과 확정 발주

`PlanResult`의status·accepted는구분됩니다. objective는USD, q/I/U/R/W와deviation은t, components는신규변동비·기존pipeline상수·보관/부족/폐기/계획말기비를분리합니다. Diagnostics는제약수·iteration·수량위반·목적함수재구성·VerifySolution·deferred pipeline을포함합니다. `.lp`는변수/제약/목적함수의실제모델표현이며시간은별도파일입니다.

`*_rolling_plans.json`은origin·현재재고·공개pipeline·현재발행point·전체미래계획·현재executed_orders·수치정규화량을저장합니다. 미래q는확정orders가아닙니다. 실제입고/재고/비용은기존Day6ledger형식을그대로씁니다. `forecast_adapter_smoke.json`은실제Forecast point와가상상태계획만갖고actual target·실제구매성과는없습니다. 모델source연결해시와code/config/solver extension해시는manifest에있습니다.
