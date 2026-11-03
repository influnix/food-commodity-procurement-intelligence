# Day 5 불확실성 사전 설계

2026-10-29 Asia/Seoul. 실제 Day 5 validation 구간과 점수를 확인하기 전에 설정과 아래 규칙을 고정했습니다. Day 4 point 사양과 결과, split은 변경하지 않습니다. 새 의존성 없이 기존 statsmodels 0.14.6 / LightGBM 4.6.0을 재사용합니다. 실행 결과는 [비교 보고서](UNCERTAINTY_COMPARISON.md)에 분리합니다.

Historical OOF는 마지막 Train 완전 vector origin(Train 끝−3개월=2021-03)에서 거슬러 올라간 60개월, **2016-04~2021-03**입니다. target은 2016-05~2021-06으로 전부 Train 내부입니다. 최근 5년의 계절 주기를 포함하고 계산량을 제한하는 달력 선택이며 점수 최적화가 아닙니다. 최초 raw 이력 675개월, mature feature 행 659개/horizon으로 Day 4 최소 120을 충족합니다. 가격 기반으로 기간을 바꾸지 않습니다. 모델 사양 자체는 이미 Day 4 validation에 사용한 상태이므로 독립 사전등록 OOF라고 주장하지 않습니다.

- SARIMAX는 동일 사양 refit 후 `get_forecast(steps=4, signal_only=False).conf_int(alpha=.2)`의 2/3/4-step을 사용합니다. 관측 가격의 Gaussian model-native prediction interval이며 계수 confidence interval과 구분합니다. forecast mean=median, q10/90=해당 양끝입니다. 파라미터 추정 불확실성을 모두 적분한 분포는 아닙니다. Day 4 점예측과 평균을 키별 대조합니다.
- LightGBM은 같은 15개 특징·성숙 TrainingBatch·100 rounds·seed/thread/복잡도에서 objective만 quantile, alpha=.1/.5/.9로 바꾼 9개 direct 모델입니다. L2 점예측도 같은 batch에서 별도로 재현해 Day 4와 대조합니다. q50과 L2를 같다고 취급하지 않습니다. Crossing은 저장·invalid 처리하며 재정렬하지 않습니다.
- 원본 가격 경계와 분위수는 clip하지 않습니다. 음수/0 경계는 별도 validity flag와 개수로 공개합니다. 비유한 값은 null과 실패로 기록합니다. Crossing·역전·누락 구간은 Coverage·폭 평가 불가이며, 유한한 개별 quantile Pinball은 분모를 따로 기록합니다.
- 모델·horizon마다 최근 **60개 성숙 OOF**를 사용하고 최소 **24개**가 필요합니다. score=`max(L−y,y−U,0)`로 **확장만** 하는 rolling conformal 형태입니다. `k=ceil((n+1)*.8)`의 k번째 order statistic이며 보간하지 않습니다. `k>n`도 부족으로 처리합니다. 부족하면 raw 구간을 유지하되 `insufficient_raw_fallback`으로 표시하고 보정 성공으로 세지 않습니다. Raw fitting 실패에는 예측 대체가 없습니다.
- residual은 해당 origin보다 이른 walk-forward 예측이어야 하고 target<=t−1, 실제 publication<=decision_at(t)를 모두 만족해야 합니다. Historical과 성숙 validation OOF만 편입하고 bridge/holdout은 차단합니다. 학습 당시 cutoff·마지막 label·최대 공표 timestamp를 proof로 저장합니다. In-sample fitted residual은 사용하지 않습니다.
- 첫 validation 2021-06의 최대 후보 수는 h1/2/3=60/60/59개입니다. 마지막 historical h3 target 2021-06은 2021-07 말까지 제외됩니다. 역사적 최소 24개가 처음 가능해지는 시점은 h1=2018-05, h2=2018-06, h3=2018-07입니다. 실제 모델 실패나 공표 지연이 있으면 늦어질 수 있습니다.
- OOF 데이터는 달력 순서로 생성하고 매 origin마다 공개분만 release합니다. 같은 model+h에서는 target 중복을 거부합니다. horizon 간 같은 target은 의존성으로 기록하며 pooling하지 않습니다. expanding model들이 달라지고 시계열 상관/비정상성이 있어 일반 split conformal의 exchangeability 기반 유한표본 보장을 주장하지 않습니다.
- 보정 결과는 interval-only입니다. 확장된 양끝이 주변 10/90% quantile이라는 근거가 없으므로 보정 행의 q10/q50/q90는 null, 원본 분위수는 base_q10/base_q50/base_q90로 보존합니다. 보정 방법의 Pinball은 NA이며 원본 quantile에만 계산합니다.
- Schema 키는 `(model_name, forecast_origin, horizon, uncertainty_method)`입니다. Raw는 sarimax_native / lightgbm_quantile, calibrated는 각각의 이름+`_rolling_conformal`입니다. logical forecast_asof_at=d_t이며 실제 실행 시각은 manifest에 별도 저장합니다. point_prediction은 Day 4 SAR 평균/LGB L2, q50은 별도입니다. calibration_cutoff는 사용 잔차의 최신 target이며 최대 공표 timestamp도 저장합니다.
- 위험 신호는 마지막 공개가격 P_(t−1)×1.10보다 raw q90이 큰지입니다. 보정 upper 초과 신호는 별도입니다. 세 분위수에서 사건 확률을 만들지 않고 SAR 분포 확률도 오늘은 산출하지 않습니다. 비용절감·품절확률이 아닙니다. 폭>마지막 공개가격인 구간을 사전 고정 wide flag로 기록합니다.

평가는 동일 36 origins / 108키 / 38고유 target입니다. 예측과 시점별 보정을 모두 생성한 뒤 evaluator만 validation reader로 정답을 결합합니다. 비교표는 Coverage·Width·Pinball의 분모, invalid·crossing·음수·실패·fallback을 공개합니다. 모든 실행은 새 폴더에 설정·코드·원본·Day 4 연결 해시와 경고·시간을 저장하며, 전체 재실행의 결정적 출력과 독립 산술을 검증합니다.

향후 가격 시나리오 계약에는 `(origin, scenario_id, target_month, horizon, positive_price, probability, planning_seed_id, model_run_id)`가 필요합니다. horizon 간 잔차의 공동 의존성, 일관된 경로, planning/evaluation seed 분리를 먼저 검증해야 합니다. 독립 월별 분위수 3개를 공동 가격 경로로 간주하지 않습니다. 오늘 경로 생성·구매 시뮬레이션·최적화는 구현하지 않습니다.

API 근거: [statsmodels forecast](https://www.statsmodels.org/v0.14.6/generated/statsmodels.tsa.statespace.mlemodel.MLEResults.get_forecast.html), [LightGBM quantile/alpha](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html), [CQR 원 논문](https://arxiv.org/abs/1905.03222). 로컬 설치 소스에서도 PredictionResults.conf_int를 확인했습니다. 비음수 score·매월 refit·rolling residual 방식은 이번 프로젝트의 단순 보수적 변형이며 논문의 독립 교환가능 표본 정리를 그대로 적용하지 않습니다.

## 출력 계약과 해석

`UncertaintyPrediction`은 기존 `ModelPrediction`과 별도인 불변 dataclass입니다. 각 run 안에서 `(model_name, forecast_origin, horizon, uncertainty_method)`를 유일 키로 사용하며 `record_id`는 이 네 항목을 `|`로 연결합니다. 서로 다른 run의 같은 키는 run 경로와 manifest로 구별합니다. 월은 YYYY-MM, timestamp는 timezone이 있는 ISO8601, 가격과 폭은 nominal USD/metric tonne입니다.

| 필드 | 의미 |
|---|---|
| model_name, uncertainty_method | Day 4 모델 이름, 원본/보정 방법 이름 |
| forecast_origin, forecast_asof_at | 월말 결정의 월 라벨과 논리 시각; 실제 실행 시각은 manifest에 별도 기록 |
| information_cutoff, target_month, horizon | t−1, t+h, h∈{1,2,3}; 모델 step은 h+1 |
| point_prediction | SARIMAX 평균 또는 LightGBM L2; Day 4 validation point와 재계산 결과 대조 |
| q10, q50, q90 | 원본 모델의 분위수; 보정 구간 행에서는 null |
| base_q10, base_q50, base_q90 | 보정 행이 참조하는 원본 분위수 |
| lower_bound, upper_bound, nominal_coverage | 원본 또는 보정 구간의 양끝과 명목 0.80 |
| calibration_sample_size, calibration_cutoff | 사용한 같은 모델·h 잔차 수, 최신 잔차 target 월 |
| calibration_max_available_at | 사용 잔차 actual의 가장 늦은 공표 timestamp |
| calibration_status, calibration_adjustment | raw_not_requested / calibrated / insufficient_raw_fallback / raw_invalid_uncalibrated, 확장량 |
| fit_information_end, fit_max_label_available_at | 해당 OOF fit의 마지막 관측/label 월과 최대 공표시각 |
| unit, validity_status, interval_usable | 단위, 원본 유효성 문제 목록, 순서가 있는 유한 구간인지 |

음수 경계라도 유한·비교차 구간이면 Coverage와 Width를 계산하되 음수/비양수 빈도를 공개합니다. 해당 구간을 양수 가격 시나리오로 바로 소비하면 안 됩니다. Crossing이면 구간 평가는 NA로 두고 개별 유한 분위수의 Pinball Loss는 분모를 별도로 계산합니다. 원본이 invalid이면 보정 행에서 구간을 비우고 `raw_invalid_uncalibrated`로 표시하므로 interval-only 행으로 바꿔 crossing을 숨기지 않습니다.

`OOFResidual`은 forecast origin/target/horizon, actual 공표 timestamp, source_model/source_method, residual_value=`actual−point`, 실제값, calibration_score, fit proof와 최초 release origin을 보존합니다. 구간 보정에는 signed point residual 자체가 아니라 구간의 비음수 초과 score를 씁니다. Audit마다 calibration_origin과 선택 잔차 키 전체를 남겨 잔차 표와 결합할 수 있습니다. 과거에 생성된 예측이라는 사실만으로 잔차를 사용하지 않으며 `target<=t−1`과 `available_at<=d_t`를 함께 검사합니다.

과거 예측 origin o의 h 잔차는 `o<t`, `o+h<=t−1`, `actual_available_at<=d_t`가 모두 참일 때만 현재 t의 보정에 쓸 수 있습니다. 기본 지연이면 `o<=t−h−1`입니다. 이는 LightGBM 학습 batch의 완전 vector 조건 `o+3<=t−1`과 구분합니다. 보정은 horizon별이므로 다른 h의 미성숙 잔차까지 기다리는 추가 간격을 만들지 않습니다. 이미 공표된 validation 오차는 이후 자동 보정에 편입하지만 현재/미래 오차로 과거 구간을 바꾸지 않습니다.

## 수식과 실패 처리

같은 모델·horizon의 공개된 잔차를 target 월 순서로 정렬한 뒤 최근 60개를 취합니다. 각 과거 원본 구간 [L_i,U_i]에서 `s_i=max(L_i−y_i,y_i−U_i,0)`를 계산합니다. `n>=24`, `k=ceil((n+1)*0.8)<=n`이면 정렬한 score의 k번째 값 δ를 이용해 `[L_t−δ,U_t+δ]`를 출력합니다. 음수가 아닌 score를 사용하므로 폭은 줄어들지 않으며 역사적 데이터가 이미 잘 포함되면 δ=0일 수 있습니다.

표본 부족은 원본 구간 유지와 명시적 상태로 처리합니다. 반면 원본 fit 실패·비수렴·누락 분위수에는 다른 모델의 예측을 넣지 않습니다. 108개 예상 키를 남기고 결측 구간 수·fit 실패 로그를 공개합니다. 모든 예측과 보정이 끝난 후 evaluator만 validation 실제값을 결합합니다. 모델 함수에는 validation reader나 calibration 실제값 표를 전달하지 않습니다.

`Pinball_q = mean((y−qhat)*(q−1[y<qhat]))`, `Coverage = mean(1[L<=y<=U])`, `Width = mean(U−L)`입니다. 각 지표는 자기 유효 표본 수와 전체 예상 키 수를 함께 저장합니다. 전체 집계는 108개 origin-horizon 쌍 동일 가중이며 독립 표본 108개라는 주장이 아닙니다. 최소 Coverage를 만족하도록 사후 조정하거나, 더 넓은 구간을 무조건 더 좋은 것으로 순위 매기지 않습니다.
