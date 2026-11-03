# Day 4 공정한 Validation 모델 비교

2026-10-27 Asia/Seoul. 기준 spec은 [사전 모델 사양](DAY4_MODEL_SPEC.md), 정확한 값은 `configs/day4.toml`입니다. 두 모델의 차수/학습 파라미터는 첫 신규 모델 validation 전에 함께 고정했고 성과를 보고 바꾸지 않았습니다. [환경 기록](DAY4_ENVIRONMENT.md)에 설치 범위와 버전을 남겼습니다.

## 같은 정보와 평가 계약

Validation은 2021-06~2024-05의 36 origins, target 2021-07~2024-08의 38개 고유 월, 108개 origin-horizon 쌍입니다. 모델 입력은 모두 월말 t에서 가용한 t-1 이하 관측만 사용합니다. Day 3의 실제 가격과 fold별 MASE 분모를 키별로 대조해 정확히 일치할 때만 비교했습니다.

새 공통 `ModelPrediction`은 origin/cutoff/target/horizon/유한 양수 가격/단위/모델명과 logical forecast_asof_at을 검증합니다. Seasonal Naive는 adapter를 제공하되 기존 구현·CSV를 변경하지 않았습니다. seasonal reference=target-12라는 제약은 Seasonal Naive 전용으로 남깁니다.

모델별 입력 표현은 같지 않습니다. SARIMAX는 전체 가용 가격 history 737~772개월을 사용하는 단변량 모형입니다. LightGBM은 과거 origin의 15개 특징을 쓰며, 전체3-horizon vector의 target이 모두 현재 t-1까지 공표된 sample만 허용합니다. 초기 특징 lookback 부족을 제외하면 각 horizon의 학습 행은 **721~756개**입니다.

첫 fit의 LightGBM 학습 feature origins는 1961-02~2021-02, h1/2/3의 마지막 label은 각각 2021-03/04/05입니다. 가장 늦은 과거 feature 관측월은 2021-01입니다. 현재 예측용 feature는 별도로 2021-05까지를 사용합니다. 마지막 fit의 과거 feature origin은 2024-01까지이며 h3 label은 2024-04까지입니다. 모든 행이 Day 3 `TrainingBatch`의 as-of·target 성숙도 경계를 통과했습니다.

h별 label만 검사하면 h1/h2에 더 최근 과거 origin을 각각2개/1개 추가할 수 있지만 오늘은 보수적인 공동 vector 마스크를 유지했습니다. 이 마스크 차이와 특징 표현은 모델의 일부입니다. 동일 원시 학습 행수를 강제로 맞췄다고 주장하지 않으며, 동일한 정보 집합·평가 target·scale을 맞춘 비교입니다.

LightGBM은 3개 별도 direct 모델입니다. 재귀 예측값을 다음 입력으로 쓰지 않고 각 origin에서 처음부터 fit합니다. 100 rounds 고정, validation set/early stopping/전처리 fit 없음. SARIMAX도 매번 동일 사양으로 refit하고 최신 관측 t-1 뒤의4-step에서 2/3/4번째를 business horizon1/2/3으로 골랐습니다. 중간 P_t의 실제값이나 미래 외생변수는 쓰지 않았습니다.

모든 fit이 끝난 뒤에만 validation 전용 reader로 정답을 결합합니다. 과거 validation 가격이 나중에 공표돼 expanding history/label에 들어가는 것은 허용하지만 현재 origin의 미래 label은 fit에 전달하지 않습니다. Holdout·bridge·품질 정의 경계·원본/가공 파일은 그대로입니다.

## 실제 성능표

MAE 단위는 nominal USD/metric tonne, MASE는 무차원입니다. MASE는 Day 3와 동일한 origin별 as-of scale 및 equal-pair 집계입니다. 실패한 예측을 baseline으로 대체하지 않았습니다.

| Model | Horizon | N | MAE | MASE | Failure |
|---|---|---:|---:|---:|---:|
| Seasonal Naive | 1 | 36 | 100.1278 | 3.2304 | 0 |
| Seasonal Naive | 2 | 36 | 100.4889 | 3.2453 | 0 |
| Seasonal Naive | 3 | 36 | 99.4722 | 3.2142 | 0 |
| Seasonal Naive | Overall | 108 | 100.0296 | 3.2300 | 0 |
| SARIMAX | 1 | 36 | 31.9368 | 1.0362 | 0 |
| SARIMAX | 2 | 36 | 43.4305 | 1.4131 | 0 |
| SARIMAX | 3 | 36 | 50.2599 | 1.6378 | 0 |
| SARIMAX | Overall | 108 | **41.8757** | **1.3624** | 0 |
| LightGBM Direct | 1 | 36 | 41.9029 | 1.3697 | 0 |
| LightGBM Direct | 2 | 36 | 48.2184 | 1.5777 | 0 |
| LightGBM Direct | 3 | 36 | 55.8647 | 1.8260 | 0 |
| LightGBM Direct | Overall | 108 | **48.6620** | **1.5912** | 0 |

세 모델 모두 108개 키가 완전하고 예측 실패율0%, 공통 성공 키 교집합도108개입니다. 이번에는 모델별 성공 집합 표와 공통 교집합 표의 표본이 같습니다. 코드에서는 불완전 모델의 전체108 기준 개선율을 null로 두고 coverage/failure/missing keys를 공개합니다. 공통 성공 교집합 성과는 별도 파일에 저장하며 그 표본을 전체108 성과로 표시하지 않습니다.

| Model | 전체 MAE 개선율 | 전체 MASE 개선율 |
|---|---:|---:|
| SARIMAX | **58.1367%** | **57.8210%** |
| LightGBM Direct | **51.3524%** | **50.7377%** |

개선율은 `(baseline-model)/baseline*100`입니다. Horizon별 개선율도 comparison CSV에 저장했습니다. SARIMAX는 h1/2/3 MAE를 각각68.1039/56.7808/49.4734%, LightGBM은58.1505/52.0162/43.8389% 낮췄습니다. h가 길어질수록 두 신규 모델의 절대오차가 커지는 양상이 관측됐습니다. 원인 분석이나 사후 사양 변경은 하지 않았습니다.

## 계산시간·경고·실패

아래는 시간 계측을 정리한 최종 재실행의 값입니다. 사양과 예측/지표는 첫 실행과 동일합니다.

| 항목 | SARIMAX | LightGBM Direct |
|---|---:|---:|
| fit 수 | 36 | 108 (origin당3개) |
| fit 시간 합계 | 1.8581 s | 1.4046 s |
| origin별 fit 평균 | 0.0516 s | 0.0390 s |
| origin별 fit 중앙값 | 0.0525 s | 0.0379 s |
| origin별 fit 최소/최대 | 0.0419 / 0.0674 s | 0.0362 / 0.0552 s |
| origin별 fit p90 | 0.0563 s | 0.0418 s |
| 라이브러리 import 합계 | 2.0283 s | 2.6690 s |
| TrainingBatch 준비 합계 | 해당 없음 | 40.0785 s |
| 전체 평가 wall time | 4.4250 s | 45.0717 s |
| fit/예측 실패 | 0 | 0 |
| 비수렴 | 0 | 해당 없음 |

LightGBM이 순수 fit은 짧아도 과거 특징/label의 정보 가용성을 반복 검증하는 batch 준비가 대부분의 시간을 차지했습니다. 실제 전체 속도가 더 빠르다고 해석하면 안 됩니다. origin별 시간은 LightGBM의 세 horizon fit을 합산했습니다. wall time에는 준비·import·검증·예측·채점도 포함되고 artifact 저장은 제외됩니다. CPU 부하/캐시/호스트에 따라 시간은 변하므로 보편적 성능 benchmark가 아닙니다.

계측 분리 후 앞선 재실행에서도 같은 예측을 얻었지만 fit 합계는 SARIMAX6.0407s/LightGBM3.0855s, wall10.5072s/94.2929s였습니다. 최종 run에서는119개 회귀 검증과 함께 부족 feature의 실패 기록도 확인했습니다. 시간의 run 간 변동을 모델 정확도 변화나 파라미터 변경으로 해석하지 않습니다.

SARIMAX의 기록된 경고는0개입니다. LightGBM은 첫 import 과정에서 기존 optional plotting 의존성의 **PyparsingDeprecationWarning 13개**를 포착했습니다(`parseString`6, `resetCache`6, `oneOf`1). 모델 fit 실패나 수렴 오류는 아닙니다. import 경고와 fit 중 Python 경고를 구분해 저장했습니다. 고정 spec의 LightGBM verbosity=-1은 routine native 로그를 억제하므로 이 개수는 모든 C++ 진단 메시지를 수집했다는 뜻은 아닙니다. Native/Python 예외는 실패로 기록합니다. 이 경고를 없애려고 무관한 전역 plotting 패키지를 업그레이드하지 않았습니다.

최초 LightGBM 실행의 fit 타이머에 cold import가 섞인 것을 확인해 **시간 계측만** 정정했습니다. 재실행에서는 두 모델 모두 import를 fit에서 분리했습니다. 모델 파라미터·마스크·데이터·예측은 변경하지 않았고 config hash 및 predictions/metrics 바이트 동일성을 확인했습니다. 시간 파일/경고 로그의 바이트 동일성을 요구하지 않습니다.

## 산출물·재현 명령

최종 모델별 run:

```text
artifacts/day4/sarimax_20261027T021556181229Z/
artifacts/day4/lightgbm_20261027T021556175230Z/
```

각각 `spec_freeze.json`, `predictions.csv`, `fold_fit_log.json`, `metrics.json`, `timing.json`, `manifest.json`이 있습니다. 파라미터/학습 범위/이력수/시간/경고/실패를 기록하며, manifest는 input/config/code/library/output hash와 holdout 잠금을 보존합니다.

최종 비교 run은 `artifacts/day4/comparison_20261027T021809505124Z/`입니다. `model_comparison.csv`, `common_success_comparison.csv`, `comparison.json`, `timing_comparison.json`, `manifest.json`을 저장했습니다.

```powershell
.\.venv\Scripts\python.exe -m food_procurement_intelligence.evaluation.model_backtesting --model sarimax
.\.venv\Scripts\python.exe -m food_procurement_intelligence.evaluation.model_backtesting --model lightgbm
# 위 명령이 출력한 새 run 경로를 다음 명령에 전달합니다.
.\.venv\Scripts\python.exe -m food_procurement_intelligence.evaluation.model_comparison --phases artifacts/day4/sarimax_20261027T021556181229Z artifacts/day4/lightgbm_20261027T021556175230Z
```

첫 run(사전 사양 고정 및 단계별 실행)의 SARIMAX `...T015441203295Z`, LightGBM `...T015706042628Z`도 보존했습니다. 모델별 최초/최종 재실행의 `predictions.csv`와 `metrics.json`은 바이트 동일합니다. `reproducibility_final_20261027.json`에 비교 결과를 남겼습니다. 설치 버전·CPU thread는 고정했으나 다른 BLAS/플랫폼까지 bitwise 동일하다고 보증하지 않습니다.

## 해석과 남은 한계

이번 고정 validation에서는 SARIMAX가 전체와 세 horizon 모두 낮은 MAE/MASE를 보였습니다. 다음 단계의 유력한 point-forecast 후보로 볼 수 있지만, LightGBM을 모든 상황에서 열등하다고 일반화하지 않습니다. 세 모델의 108개 오차는 **38개 target month를 공유**하고 시계열 상관이 있어 독립 표본108개가 아닙니다. 통계적 유의성·holdout 일반화·실제 조달 절감·공급 안정성은 검증하지 않았습니다.

공표 timestamp는 가정이고 최신 수정본 snapshot을 사용하는 pseudo-real-time 평가입니다. 장기 nominal 학습 이력과 2020-07 품질 정의 경계의 한계도 남습니다. 하이퍼파라미터·학습 창·표본을 유리하게 바꾸지 않았습니다. 예측구간·quantile·scenario·구매 정책은 Day 5 이후 별도 지시 범위입니다.
