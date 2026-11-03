# Day 3 특징·Seasonal Naive·Validation 평가 명세

실행일: 2026-10-27 Asia/Seoul. 설정은 `configs/day3.toml`이며 Day 2의 split/config 해시를 고정했습니다. 날짜·horizon·공표 지연·정의 경계는 바꾸지 않았습니다. 모델 입력은 `load_development_store`의 as-of 접근만 사용합니다.

## 15개 특징과 정보 시점

`t`는 월말 의사결정의 월 라벨입니다. 가격 특징의 기준은 target이 아닌 **origin t**이고, 가장 최근 허용 관측은 `t-1`입니다.

| 특징 | 정의 | 단위 / 원천 |
|---|---|---|
| `lag_1, lag_3, lag_6, lag_12` | 각각 `P_(t-k)` | nominal USD/t, 과거 관측 |
| `rolling_mean_3/6/12` | `mean(P_(t-w),...,P_(t-1))` | USD/t, 해당 w개 월 모두 필요 |
| `rolling_std_3/6/12` | 같은 window의 표본 표준편차, `ddof=1` | USD/t, 분모 w-1 |
| `monthly_change_fraction` | `P_(t-1)/P_(t-2)-1` | 비율, 2개월 필요 |
| `yearly_change_fraction` | `P_(t-1)/P_(t-13)-1` | 비율, 13개월 필요 |
| `origin_calendar_month` | origin의 1~12월 | 미리 알려진 달력 |
| `target_calendar_month` | target t+h의 1~12월 | 미래 월이지만 origin에서 이미 앎 |
| `forecast_horizon` | business horizon 1/2/3 | 미리 알려진 계획 정보 |

가격 기반 12개와 달력/horizon 3개를 구분합니다. 미래 가격·날씨·수요·정의 경계 flag는 모델 입력에 추가하지 않았습니다. 특히 YoY를 `P_(t-1)/P_(t-12)`로 잘못 정의하지 않았고, centered rolling이나 전체 CSV에 대한 선행 rolling도 사용하지 않습니다.

각 `FeatureVector`는 origin, information cutoff, target month, horizon, 가격 단위와 feature 값을 보유합니다. 별도의 provenance에는 각 가격 특징이 참조한 모든 월, 그중 가장 늦은 available_at, 사전에 알려진 calendar feature 목록을 저장합니다. `feature_asof_at`은 **시뮬레이션 정보 시각 d_t**이고 실제 현재 실행 시각은 run manifest의 `created_at_utc`입니다. 과거에 실제로 생성된 예측/특징이라는 주장이 아닙니다.

`checked_history`는 Day 2의 `assert_feature_available`을 재사용해 모든 관측월 `<=t-1`, 공표시각 `<=d_t`, 월/단위/숫자 유효성을 검사합니다. 필요한 한 월이라도 누락·미공표이면 `FeatureUnavailableError`로 이유를 반환합니다. 0 대체·보간·전역 Scaling은 없습니다. 이번 validation의 108개 행은 모두 13개월 이상 이력이 있어 실패가 없었습니다.

## 향후 전처리 fit 경계

`build_training_batch`는 먼저 Day 2의 target 성숙도 규칙을 적용하고, 남은 sample의 각 **과거 origin**에서 특징을 생성합니다. label은 현재 평가 origin에서 `training_targets`로 다시 검사합니다. batch는 feature와 label의 순서를 맞추고, 미성숙 label/부족 lookback 제외 사유를 남깁니다.

향후 imputer/scaler는 이 batch에만 fit하고 validation에는 transform만 적용해야 합니다. 현재 설정은 `missing_strategy=fail_with_reason`, `scaling=none`이며 다른 전처리를 조용히 실행하지 않습니다. 실제 learner나 scaler를 만들거나 fit하지 않았습니다. Seasonal Naive는 이 batch를 학습하지 않고, 별도 feature dataset을 이후 모델에 재사용하기 위해 생성합니다.

## Seasonal Naive

```math
\widehat P_{t+h\mid\mathcal F_t}=P_{t+h-12},\qquad h\in\{1,2,3\}
```

참조 관측은 각각 `t-11`, `t-10`, `t-9`입니다. origin 기준 `lag_12` 또는 마지막 관측값을 그대로 반복하는 모델과 다릅니다. `predict`는 origin별 as-of history에서 참조월이 있는지 확인하고 Day 2 `store.feature` guard로 공표 가용성을 재검사합니다.

출력은 검증된 `Prediction`입니다. target=origin+h, cutoff=origin-1, reference=target-12, 참조 공표시각, 양수/유한 가격, 단위를 검사합니다. 필요한 참조월이 없으면 `ForecastUnavailableError`로 실패하고 다른 baseline으로 대체하지 않습니다. 모델명은 `seasonal_naive_12`, 학습 파라미터 수는 0입니다.

## Rolling-origin과 정답 경계

고정 validation origins는 2021-06~2024-05의 36개, targets는 2021-07~2024-08입니다. 3개 horizon을 모두 적용해 **108쌍**, 고유 target month는 **38개**입니다. 동일 target이 여러 origin에서 등장하는 것은 정상이며 키는 `(forecast_origin,horizon)`입니다.

실행 순서는 두 단계입니다.

1. 모든 origin에서 as-of history를 확보하고 target 성숙도 마스크·현재 fold와의 overlap을 검사합니다. 특징, Seasonal Naive 예측, fold별 scale을 먼저 생성합니다. 평가 정답 reader는 이 함수들에 전달하지 않습니다.
2. 모든 예측 생성 후 `ValidationActualsReader`를 요청해 정답을 결합하고 오차를 계산합니다. reader는 validation target만 제공하며, label의 공표시각이 assessment clock 이내인지 검사합니다. 공통 최종 assessment clock은 선택 freeze인 2024-09 말입니다.

`data/availability.py`에 추가한 것은 validation-only evaluator capability와 값 없는 maturity 검증 메서드뿐입니다. 기존 개발 `history_as_of/feature/training_targets`의 t-1 제약과 bridge/holdout 잠금은 그대로입니다. reader도 train·bridge·holdout target은 거부하고, 2024-09 freeze 이후 시각을 이용한 우회도 거부합니다. OS 수준의 파일 봉인은 아닙니다.

첫 fold에는 2021-05까지 737개월, 마지막 fold에는 2024-04까지 772개월이 있습니다. 이전 validation 정답이 시간이 지나 공개되면 이후 fold의 이력과 scale에 포함됩니다. 예를 들어 과거에 예측한 2021-07 가격은 2021-08 말에는 공개돼 입력에 들어갈 수 있지만, 2021-06 예측 때 미리 들어갈 수는 없습니다. 이는 선택된 규칙의 expanding 재실행이며 미래 정답을 선행 학습하는 것과 다릅니다.

Seasonal Naive에 학습 파라미터는 없지만 재사용 가능한 fold 감사표에는 성숙한 지도학습 후보 수·마지막 origin을 기록했습니다. 이는 실제 supervised fit 행수나 FeatureSpec lookback 적용 후 학습량을 뜻하지 않습니다. 현재 learner를 fit한 척하지 않습니다.

## MAE·MASE와 scale 비교

오차는 `e_(t,h)=actual-predicted`입니다. MAE의 단위는 USD/t이고 MASE는 무차원입니다.

```math
Q_t=\{m:m,m-12\in\mathcal F_t\},\qquad
s_t=\frac{1}{|Q_t|}\sum_{m\in Q_t}|P_m-P_{m-12}|
```

```math
MAE_h=\frac1{N_h}\sum_t|e_{t,h}|,\qquad
MASE_h=\frac1{N_h}\sum_t\frac{|e_{t,h}|}{s_t}
```

분모의 두 관측 모두 해당 origin에 공개된 history에 있어야 합니다. 첫 fold의 pair는 725개, `s=29.406344827586206`; 마지막은 760개, `s=32.701578947368425`입니다. 미래 관측을 history에 넣어 scale 함수를 호출하면 예외를 냅니다.

| 방식 | 정보 범위 | 취급 |
|---|---|---|
| Fold별 expanding as-of | 각 origin의 가용 history | **주 MASE**, 기존 평가 프로토콜 유지 |
| 고정 초기 as-of | 첫 validation origin에서 알려진 1960-01~2021-05, s=29.406344827586206 | 같은 오차에 적용한 보조 비교 |
| 명목상 Train 전체를 고정 | ~2021-06 | 첫 origin 2021-06에는 그 달 가격이 미공표이므로 사용 금지 |

주 방식은 결과를 보고 고른 것이 아니라 기존 프로토콜대로 사전에 설정했습니다. 고정 scale은 분모가 일정해 비교가 쉽지만 이후 공표된 변동 정보를 반영하지 못합니다. Fold 방식은 당시 가용한 학습 이력을 반영하므로 expanding 재학습 실험과 일관됩니다. 서로 다른 분모 방식의 MASE를 같은 정의의 수치처럼 섞지 않습니다.

fold별 MASE는 같은 origin의 3개 `|e|/s_t` 평균입니다. horizon별은 36 origins 동일 가중, 전체는 108 origin-horizon 쌍 동일 가중입니다. 완전한 균형 표본이므로 전체 MASE는 3개 horizon MASE의 평균과 같습니다. **`전체 MAE/평균 scale`로 계산하지 않습니다.**

pair가 없거나 scale=0이면 `value=null`과 `insufficient_seasonal_pairs`/`zero_seasonal_scale` 사유를 남깁니다. epsilon이나 임의 1로 대체하지 않습니다. MAE는 계속 계산하고 MASE는 정의된 ratio만 집계하되 defined/undefined 개수를 공개합니다. 이번 실제 결과는 108개 모두 MASE가 정의됐습니다.

## 실제 Validation 결과

| Horizon | 쌍 수 | MAE (USD/t) | MASE: fold as-of | MASE: 고정 초기 as-of |
|---|---:|---:|---:|---:|
| 1 | 36 | 100.1278 | 3.2304 | 3.4050 |
| 2 | 36 | 100.4889 | 3.2453 | 3.4173 |
| 3 | 36 | 99.4722 | 3.2142 | 3.3827 |
| 전체 | **108** | **100.0296** | **3.2300** | **3.4016** |

누락 예측·특징 실패·undefined MASE 모두 0입니다. 36개 fold별 수치와 반올림 전 결과는 metrics/fold audit에 저장했습니다. Seasonal Naive 자체의 MASE가 1일 필요는 없습니다. 분모는 과거 in-sample 12개월 차분이고 분자는 이 validation의 2/3/4-step 예측오차이므로 서로 다른 표본입니다. MASE가 크거나 작다는 이유만으로 구매 정책의 비용·서비스 우수성을 판단하지 않습니다. 아직 정책 실험은 없습니다.

## 재현성과 한계

최종 기준 run은 `artifacts/day3/20261027T013028732383Z/`, 반복 run은 `20261027T013029938690Z`입니다. 예측·특징·provenance·fold audit·metrics·failures의 **6개 핵심 파일 모두 바이트 해시가 동일**했습니다. 독립 검증 스크립트는 저장된 예측과 as-of store를 이용해 Seasonal Naive 참조, 36개 분모, MAE/MASE 산술을 별도로 대조했습니다.

입력은 기존 snapshot `20261024T012917500704Z_ea1c35082787`입니다. 수정본 vintage와 공표 지연 가정의 한계는 남아 있어 `latest_vintage_pseudo_real_time`입니다. 품질 정의 경계를 유지했고 어떤 가격도 바꾸지 않았습니다. 신규 데이터·패키지·외생변수·하이퍼파라미터 탐색은 없습니다. Day 4는 별도 지시 후 같은 계약에 추가 모델을 연결합니다.
