# Day15 Raw Forecast 유효성 계약

2026-10-31 Asia/Seoul. CR-02 수정의 공용 구현은 [validity.py](../src/food_procurement_intelligence/uncertainty/validity.py), 적용점은 [UncertaintyPrediction](../src/food_procurement_intelligence/uncertainty/contracts.py)과 [NativeForecastPublisher](../src/food_procurement_intelligence/forecasting/publisher.py)입니다. 모델·특징·학습 사양·q50/L2 정의는 바꾸지 않습니다.

## Stage별 규칙

| Stage | 허용·거부 계약 |
|---|---|
| Point | 숫자 Real, bool 제외, 유한·양수. USD/metric tonne, nonempty model/method, canonical origin/target/horizon과 t−1·fit/publication cutoff 검사. q50으로 대체하지 않음 |
| Raw Quantile | q10/q50/q90 존재·숫자·유한, q10≤q50≤q90. q10=raw lower, q90=raw upper. SAR mean과 LGB L2 point를 q50과 교환하지 않음 |
| Raw Interval | lower/upper 유한·순서 정상. Quantile/point가 invalid면 Calibration용으로 사용할 수 없음 |
| 유한 0·음수 통계 경계 | Day5 원칙대로 보존하고 NONPOSITIVE_BOUND_REVIEW flag. 통계 구간은 그대로 보정/평가 가능. 자동 clip 없음 |
| Native ingress | positive finite point와 finite aligned raw triple/bounds 필수. Crossing은 원본 그대로 invalid로 발행·기록 가능. 유한 비양수 통계 경계는 이제 보존·flag하므로 과거 Day12의 일괄 양수 강제와 구별 |
| Calibration | valid point/quantile/interval과 model/h별 성숙 score만 사용. 비유한 quantile을 q*=null로 옮긴 뒤 정상으로 바꾸지 않음. 보정 후 base_q*로 원본 검증 유지 |
| Joint | raw point가 finite positive, actual이 positive, 완전 vector 성숙·발행/fit/source proof 충족. Raw interval crossing만으로 Joint point-error vector를 제거하지 않음 |
| Actual / Scenario price | 언제나 finite positive. Observation·PricePath의 기존 양수 검사를 유지. 통계 구간의 음수 허용과 혼동 금지 |

`interval_usable`은 기존의 bounds 순서 검사만으로 판단하지 않고 공용 validator의 point·quantile·interval 세 조건을 모두 요구합니다. `finite_number`는 문자열 숫자/True를 숫자로 조용히 변환하지 않습니다. malformed metadata는 constructor/새 adapter에서 거부합니다. Invalid forecast는 명시 상태로 보존할 수 있지만 성공 Calibration은 불가합니다.

q50=NaN/Infinity + finite[90,110] 반례는 INVALID_QUANTILE입니다. Point=NaN/Infinity/0/음수는 INVALID_POINT입니다. lower=NaN, upper=Infinity, lower>upper는 INVALID_INTERVAL입니다. q10>q50, q50>q90, q10>q90는 QUANTILE_CROSSING이며 재정렬하지 않습니다. Raw endpoint와 quantile 불일치도 invalid입니다. Raw invalid는 보정 결과의 양끝을 null로 두고 원래 point/base quantile 및 실패 상태를 보존합니다.

## 상태 매핑

기존 저장 schema와 calibration_status를 유지하고 공용 validator가 별도의 해석 가능한 `states`를 제공합니다. 통계 경계 검토 flag는 유효성을 자동 실패로 만들지 않습니다.

| 요청한 의미 | 기존/신규 표기 | 후속 동작 |
|---|---|---|
| VALID_RAW | validity_status=valid, raw_not_requested | 적격 score에 사용 가능 |
| INVALID_POINT | missing_or_nonfinite_point / nonpositive_point | Calibration invalid, 신규 adapter 발행/Joint 입력 거부 |
| INVALID_QUANTILE | missing_or_nonfinite_quantile / quantile_interval_mismatch | raw_invalid_uncalibrated, interval 비움 |
| QUANTILE_CROSSING | quantile_crossing | 동일; 유효 point Joint는 별개 |
| INVALID_INTERVAL | missing_or_nonfinite_interval / inverted_interval | 동일; 성공 fallback 아님 |
| NONPOSITIVE_BOUND_REVIEW | nonpositive_price_boundary | 유한·비교차 통계 구간 보존·flag |
| INSUFFICIENT_CALIBRATION_POOL | insufficient_raw_fallback | valid raw만 유지; 보정 성공으로 세지 않음 |
| CALIBRATED | calibrated | interval-only 양끝 확장, q*=null, base_q* 유지 |
| JOINT_POOL_UNAVAILABLE | ValueError: insufficient/unsupported joint pool | 중단; 대체·clip·재표집 없음 |
| SOURCE_PROVENANCE_UNVERIFIED | readiness NOT_VERIFIED | 실제 실행 불가; 합성 interface PASS와 분리 |

기존 Day12 기록의 raw crossing14건은 그대로 crossing입니다. 보정335/13 기록을 소급 수정하지 않습니다. 변경 후 raw crossing validity 문자열과 발행 digest는 동일하고, 새 보정 row에는 원본 base crossing 사실이 더 명확하게 남을 수 있습니다. Current interval이 invalid라도 Joint는 유효 point만 별도로 검증합니다. Fit·Calibration invalid·Joint 실패·solver 실패를 하나의 성공적인 fallback으로 통합하지 않습니다.
