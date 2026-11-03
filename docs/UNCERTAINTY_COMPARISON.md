# Day 5 Validation 불확실성 비교

2026-10-29 Asia/Seoul. 사전 사양은 [불확실성 설계](DAY5_UNCERTAINTY_DESIGN.md)와 `configs/day5.toml`입니다. 아래는 두 실제 실행과 각각의 독립 검산에서 확인한 결과입니다. 예측·OOF·보정·지표·위험 신호 핵심11개 파일이 바이트 동일했고 정확한 경로는 [실행 기록](DAY5_STATUS.md)에 있습니다. Day 4 모델·point 예측·split과 원본 데이터는 보존했습니다.

## 같은 평가 키와 모델 연결

Validation origin은 2021-06~2024-05의36개월, target은 2021-07~2024-08의38개월입니다. 각 모델·방법별108개 키, 전체432행이며 각 horizon의N은36입니다. Raw SARIMAX 평균과 raw LightGBM L2를 다시 계산해 보존된 Day 4 point 값과 키별로 대조했습니다. SARIMAX의 `forecast`와 `get_forecast.predicted_mean`도 같았습니다. LightGBM q50은 L2와108개 모두 다른 값이므로 서로 덮어쓰지 않습니다.

SARIMAX의 관측가격 중앙80% 구간과 Gaussian q10/q50/q90, LightGBM의 direct quantile q10/q50/q90를 평가합니다. 보정 방법은 interval-only이므로 확장 양끝을 주변 분위수로 취급하지 않으며 Pinball은NA입니다. 원본 분위수는 별도로 보존합니다.

## Pinball Loss

단위는 nominal USD/metric tonne이며 작을수록 좋습니다. 각 원본 분위수의N은 horizon별36, 전체108입니다.

| 모델 | Horizon | q10 | q50 | q90 |
|---|---|---:|---:|---:|
| SARIMAX native | H1 | 9.3825 | 15.9684 | 10.8102 |
| SARIMAX native | H2 | 11.8730 | 21.7152 | 15.2293 |
| SARIMAX native | H3 | 13.3222 | 25.1300 | 16.4859 |
| SARIMAX native | 전체 | **11.5259** | **20.9379** | **14.1751** |
| LightGBM quantile | H1 | 17.3048 | 25.5734 | 21.7901 |
| LightGBM quantile | H2 | 16.8483 | 27.9490 | 25.8176 |
| LightGBM quantile | H3 | 15.9801 | 30.6952 | 29.0502 |
| LightGBM quantile | 전체 | **16.7111** | **28.0725** | **25.5526** |

SARIMAX는 이번 표에서 모든h·q의 Pinball이 더 작았습니다. 이는 Gaussian 분포 가정의 정확성이나80% Coverage 충족을 뜻하지 않습니다.

## Coverage와 평균 폭

Coverage는 inclusive `L<=actual<=U`, 폭은 `U−L`입니다. 유효 구간N은 horizon별36, 전체108이고 정의 불가·누락은0입니다. 폭 단위는 nominal USD/metric tonne입니다.

| 모델·방법 | Horizon | 포함 수/N | Coverage | 평균 폭 |
|---|---|---:|---:|---:|
| SARIMAX native | H1 | 18/36 | 50.00% | 47.9739 |
| SARIMAX native | H2 | 19/36 | 52.78% | 61.7830 |
| SARIMAX native | H3 | 15/36 | 41.67% | 73.2340 |
| SARIMAX native | 전체 | 52/108 | **48.15%** | **60.9970** |
| SARIMAX + rolling OOF | H1 | 23/36 | 63.89% | 64.0545 |
| SARIMAX + rolling OOF | H2 | 23/36 | 63.89% | 89.4219 |
| SARIMAX + rolling OOF | H3 | 20/36 | 55.56% | 99.9041 |
| SARIMAX + rolling OOF | 전체 | 66/108 | **61.11%** | **84.4602** |
| LightGBM quantile | H1 | 20/36 | 55.56% | 171.6496 |
| LightGBM quantile | H2 | 22/36 | 61.11% | 167.9350 |
| LightGBM quantile | H3 | 21/36 | 58.33% | 154.3039 |
| LightGBM + rolling OOF | H1 | 24/36 | 66.67% | 189.2472 |
| LightGBM + rolling OOF | H2 | 23/36 | 63.89% | 194.3804 |
| LightGBM + rolling OOF | H3 | 24/36 | 66.67% | 198.2547 |
| LightGBM quantile | 전체 | 63/108 | **58.33%** | **164.6295** |
| LightGBM + rolling OOF | 전체 | 71/108 | **65.74%** | **193.9608** |

전체 Coverage는 SARIMAX가12.96 percentage points, LightGBM이7.41 percentage points 높아졌고 평균 폭은 각각23.4632 /29.3312 USD/t 늘었습니다. 이 방식은 비음수 score로 확장만 하므로 원본에서 포함했던 점이 보정 때문에 제외되지는 않습니다. Coverage 상승 자체가 미래 보정 성공의 증거는 아닙니다. **두 모델 모두 모든horizon에서 명목80%에 못 미쳤습니다.** 이 결과를 보고 보정 창·최소 표본·학습 기간·파라미터를 다시 고르지 않았습니다.

SARIMAX 원본과 보정 폭은h가 길수록 커졌습니다. LightGBM 원본 평균 폭은H1→H3에서 줄었고 보정 후에는 늘었습니다. Horizon별 독립 quantile 모델에 폭의 단조 증가 제약을 추가하지 않았으며, 이 현상만으로 더 먼h의 실제 불확실성이 작다고 해석하지 않습니다.

최대 폭은 SARIMAX raw76.3340 / calibrated136.1039, LightGBM raw258.2643 / calibrated288.3121 USD/t입니다. 사전 wide 기준인 `폭>해당 origin 마지막 공개가격`은 네 방법 모두0개였지만, 큰 절대 폭의 경제적 유용성은 아직 검증하지 않았습니다.

## Historical OOF와 시점별 보정

Historical origin60개는2016-04~2021-03, target합집합62개월은2016-05~2021-06이며 모두Train 내부입니다. 최초 raw 이력675개월 / LGB mature 행659개/h에서 시작합니다. Native와 quantile 각180개, 합계360개 historical interval forecast를 생성했습니다. Validation 원본216개와 합쳐 `all_oof_forecasts.csv`는576행입니다.

처음24개 성숙 score가 모이는 역사적 시각은 두 모델 모두 H1=2018-05, H2=2018-06, H3=2018-07입니다. 실제 보정 적용은 고정 Validation 시작인2021-06부터입니다. 첫보정은 h별60/60/59개이며 마지막 historical H3 target2021-06은 그때 미공표라 제외됩니다. H1 최신 score target은2021-04, H2/H3는2021-05입니다. Historical origin을 완전3-horizon Train 표본으로 고정해2021-04/05 origin의 부분표본을 추가하지 않았습니다.

Window60 / 최소24 / horizon·모델별 분리 / 유한표본 k번째 score 규칙을 사용했습니다. 각 보정의n은59~60, 보정 성공216/216, 부족 fallback0입니다. 마지막 origin에서는 모델별 h1/h2/h3의 Historical/Validation 구성은26/34,27/33,28/32개이고 최신 score target은2024-04입니다.

마지막 validation clock까지 저장한 잔차는 historical360개 +성숙 validation198개=558개입니다. 나머지18개 원본 예측은 target 미공표 상태로 날짜만 pending 목록에 남습니다. 채점 시 실제값을 나중에 읽더라도 이18개를 이전 보정 pool에 소급 편입하지 않습니다. 모델·horizon 안의 target 중복0이며, 서로 다른h가 같은target을 공유하는 그룹은 두 모델 합계186개입니다. Pool을 합치거나 독립 표본으로 세지 않습니다.

## 실패·경고·가격 유효성

96 SARIMAX fits와864 quantile fits, point 연결 검사용288 L2 fits, 총1,248개 fit 이벤트가 모두 성공했습니다. Historical에서780개, validation에서468개입니다. 원본·보정 validation432행 모두 valid, crossing0, 음수/0 경계0, 비유한·누락0입니다. Historical raw360행도 모두 valid였습니다. SARIMAX96개 모두 수렴했고 fit 경고0입니다.

첫 LightGBM import에서 기존 optional plotting 의존성의 PyparsingDeprecationWarning13개를 포착했습니다. 모델 fit 실패와 구분해 `failures_and_warnings.json`에 남겼으며 무관한 패키지를 설치·업그레이드하지 않았습니다. verbosity=-1인 C++ routine 로그 전체를 수집한 경고 수는 아닙니다.

첫 실행 wall400.4150s, fit합계62.9357s, 기존 as-of TrainingBatch 준비323.7567s였습니다. 시간은 호스트 부하·import·캐시에 따라 달라지며 일반적인 속도 benchmark가 아닙니다. 설정 비교나 성능 탐색을 위해 반복한 실행은 없습니다. 동일 설정 재실행은 예측 재현성 검사입니다.

## 가격 상승 신호와 후보 판단

마지막 공개가격 대비10% 상승 임계값을 raw q90이 넘은 키는 SARIMAX34/108, LightGBM23/108입니다. 보정 upper 초과 신호는 각각62/108,47/108입니다. 이 빈도는 위험 신호가 켜진 결정 키 수이며 사건 확률, 실제 상승률, 품절률이나 구매 절감률이 아닙니다. `event_probability`는 전부 빈 값입니다.

현재는 **SARIMAX + rolling OOF를 구간 효율 관점의 우선 진단 후보**로 두는 것이 합리적입니다. 근거는 원본의 모든 Pinball이 더 작고, 보정 폭84.46이 LightGBM의193.96보다 좁다는 점입니다. 반면 보정 Coverage는61.11%로 LightGBM65.74%보다 낮아 일방적 우월성은 없습니다. Coverage를 더 우선하는 비교 후보로 LightGBM 보정 구간을 보존합니다. **어느 쪽도 검증된80% 위험 보장 구간으로 채택할 근거는 부족합니다.** 모델 선택은 MAE 하나로 결론내리지 않았습니다.

108개 오차는38개 실제target을 공유하며 시계열 의존성이 있습니다. 최신 수정본·가정 공표시각·장기 nominal 이력·2020-07 등급 정의 변경이 남습니다. Historical pool이 경계 전후를 포함한다는 이유만으로 구조적 단절이나 undercoverage 원인을 단정하지 않습니다. 과거 OOF로도 급변하는 조건부 오차를 즉시 반영하기 어렵고, rolling refit·의존 표본에서 exchangeability 기반 보장을 주장하지 않습니다. 작은 Validation에 대한 이번 후보 판단은 미래 보장이나 Holdout·구매 성과 검증이 아닙니다.
