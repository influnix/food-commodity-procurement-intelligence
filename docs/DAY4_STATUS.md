# Day 4 실행 기록

2026-10-27 Asia/Seoul. **Day 4 완료**, Day 5 미착수. 고정 SARIMAX·LightGBM 구현, 단계별 검증, validation 비교만 수행했습니다. 날짜 split·원본·Day 0~3 코드와 산출물은 보존했습니다. Holdout/quantile/예측구간/NASA/시뮬레이션/최적화/대시보드/하이퍼파라미터 탐색/Git commit·push는 수행하지 않았습니다.

## 1. 생성·수정한 파일

신규:

- `configs/day4.toml`: validation 성능 확인 전 고정한 두 모델 spec와 실행 규칙
- `requirements/day4-lock.txt`: 모델 필수 의존성 closure exact pin 11개
- `forecasting/common.py`: 최소 공통 ModelPrediction·ModelFold, Seasonal Naive adapter
- `forecasting/sarimax.py`: 단변량 as-of fit, 4-step 매핑, 수렴/경고/오류 기록
- `forecasting/lightgbm.py`: 기존 mature TrainingBatch의 horizon별 direct fit
- `evaluation/model_backtesting.py`: 모델별 phase, 모든 fit 후 채점, 시간·실패·manifest
- `evaluation/model_comparison.py`: 동일 actual/scale/단위 검사, coverage와 공통 교집합 비교
- `tests/test_day4_models.py`: fake estimator, 실제 라이브러리 toy, 누락/실패/공정성 검증
- `scripts/verify_day4_results.py`: 별도 산술·입출력/코드 해시·Day 3 보존 검증
- 문서: DAY4_MODEL_SPEC, DAY4_ENVIRONMENT, MODEL_COMPARISON, 본 문서

위 모듈 경로의 기준은 `src/food_procurement_intelligence/`입니다. 수정은 `pyproject.toml`의 선택적 models extra와 README·ROADMAP·EVALUATION_PROTOCOL·DATA_DICTIONARY·PROJECT_CHARTER·AGENTS의 상태/규칙 기록입니다. 기존 Day 3 예측 함수·feature·availability·metrics·backtesting 및 테스트는 변경하지 않았습니다.

## 2. 라이브러리와 설치 범위

기존 Python3.11.5 `.venv`에 **statsmodels0.14.6, LightGBM4.6.0, patsy1.0.2만 신규 설치**했습니다. NumPy1.26.4/SciPy1.17.1/pandas2.2.3 등은 기존 공유 패키지를 사용했습니다. 새3개 경로가 모두 `.venv` 안임을 확인했고 기본 Miniconda에서는 미설치 상태가 유지됐습니다. 필수 dependency spec과 import 모두 검증됐습니다.

최초 pip 시도는 샌드박스 DNS 오류로 실패했으나 승인된 네트워크 재시도로 성공했습니다. models extra의 로컬 editable metadata 갱신도 임시 파일 접근 거부 후 승인된 재시도로 완료했습니다. 불필요한 업그레이드나 환경 충돌 우회는 없었습니다. `pyproject`·설치된 Requires-Dist·lock11개의 버전이 일치합니다. 정확한 명령/경로/공유 환경 한계는 [환경 기록](DAY4_ENVIRONMENT.md)에 있습니다.

## 3~4. 최초 모델 사양

[사전 spec](DAY4_MODEL_SPEC.md)은 첫 신규 모델 실행 전에 두 모델 설정을 함께 작성했습니다. phase별 spec_freeze의 timestamp/config hash가 이를 기록합니다.

- SARIMAX: `(1,1,0)x(1,0,0,12)`, trend n, stationary/invertible 제약, L-BFGS maxiter100, 최소120개월. 원시 가격 수준, 외생변수·보간·로그변환 없음. 매 origin 전체 가용 이력을 새로 fit하고 t-1에서 4-step의2/3/4를 선택합니다. 비수렴/비유한·비양수 예측은 실패, clip/fallback 없음.
- LightGBM: 3개 direct-horizon 모델, objective regression_l2, 100 rounds, learning rate0.05, leaves7/depth3/min leaf20/L2=1, fraction/bagging1.0. 기존15개 특징, imputation/scaling 없음, 최소120행/horizon. seed/data seed20261027, thread1·deterministic·force_col_wise. Early stopping과 validation 전달 없음.

SARIMAX는 RNG를 사용하지 않고 CLI 프로세스의 BLAS/OpenMP thread를1로 기록했습니다. 파라미터·학습 창·마스크를 성과에 맞춰 바꾸지 않았습니다.

## 5. 학습 마스크와 누수 검증

정보는 월말 t에 t-1까지, 납품 target은 t+1/2/3으로 유지했습니다. SARIMAX는 737~772개 공개된 연속 가격만 fit했습니다. 누락 월이 있으면 임의 생성하지 않고 실패합니다.

LightGBM은 `build_training_batch`를 그대로 사용해 과거 origin에서 특징을 만들고 현재 t에서 `origin+3<=t-1`와 timestamp 검사를 통과한 전체 vector만 label로 썼습니다. 같은 origin 집합을 세 horizon에 사용해 학습 행은 각각721~756개입니다. h1/h2만의 최신 label을 추가하는 다른 마스크는 사용하지 않았습니다. 첫 fit의 마지막 feature origin은2021-02, h1/2/3 마지막 label은2021-03/04/05입니다.

모델 함수에 정답 reader를 전달하지 않습니다. 모든36개 fit 이후에만 evaluator가 validation actual을 읽습니다. 과거 validation 가격이 나중에 공표되면 이후 expanding fit에는 들어가지만 현재 origin의 미래 label은 들어가지 않습니다. Holdout 값·날짜 요청 차단은 기존 guard 그대로입니다.

## 6~9. 실제 Validation 성능

36 origins(2021-06~2024-05), 고유 target38개월(2021-07~2024-08), 모델별108개 키/동일 actual/동일 Day 3 MASE scale/동일 nominal USD/t를 확인했습니다. 세 모델 모두 실패0%, 공통 성공 키108개입니다.

| Model | Horizon | N | MAE (USD/t) | MASE | Failure |
|---|---|---:|---:|---:|---:|
| Seasonal Naive | 1 | 36 | 100.1278 | 3.2304 | 0 |
| Seasonal Naive | 2 | 36 | 100.4889 | 3.2453 | 0 |
| Seasonal Naive | 3 | 36 | 99.4722 | 3.2142 | 0 |
| Seasonal Naive | Overall | 108 | 100.0296 | 3.2300 | 0 |
| SARIMAX | 1 | 36 | 31.9368 | 1.0362 | 0 |
| SARIMAX | 2 | 36 | 43.4305 | 1.4131 | 0 |
| SARIMAX | 3 | 36 | 50.2599 | 1.6378 | 0 |
| SARIMAX | Overall | 108 | **41.8757** | **1.3624** | 0 |
| LightGBM | 1 | 36 | 41.9029 | 1.3697 | 0 |
| LightGBM | 2 | 36 | 48.2184 | 1.5777 | 0 |
| LightGBM | 3 | 36 | 55.8647 | 1.8260 | 0 |
| LightGBM | Overall | 108 | **48.6620** | **1.5912** | 0 |

전체 baseline 대비 개선율은 SARIMAX **MAE58.1367% / MASE57.8210%**, LightGBM **MAE51.3524% / MASE50.7377%**입니다. `(baseline-model)/baseline*100`을 사용했습니다. Fold scale·equal-pair 집계는 Day 3와 같습니다. 불완전 모델의 성공 표본만으로 전체108 기준 개선율을 만들지 않도록 null/coverage와 공통 교집합 표를 분리했습니다. 이번 실제 결과는 모두 완전해 두 표본이 같습니다.

## 10. 시간·경고·실패·재현성

최종 run의 순수 fit 합계는 SARIMAX1.8581s, LightGBM1.4046s입니다. LightGBM에는 batch 준비40.0785s가 추가돼 전체 평가45.0717s였고 SARIMAX 전체는4.4250s였습니다. origin별 mean/median/min/max/p90, library import 시간, 각 horizon의 fit/예측 시간은 [모델 비교](MODEL_COMPARISON.md)와 timing JSON에 있습니다. 호스트 부하/캐시 영향으로 이전 재실행의 시간과 차이가 있으며 일반적인 속도 우위를 보증하지 않습니다.

SARIMAX는36개 모두 수렴했고 기록된 경고0개입니다. LightGBM은 첫 import에서 optional plotting 의존성의 Pyparsing deprecation13개를 기록했고 실제 fit 오류0입니다. Python warning/import warning과 모델 실패를 구분했습니다. verbosity=-1의 native routine 로그는 수집 대상이 아니므로 모든 C++ 진단을 확보했다고 주장하지 않습니다.

첫 실행의 LightGBM 타이머에 cold import가 섞여 시간 계측만 분리했고, 최종 점검에서 부족한 현재 feature도 fold 실패로 기록하도록 보강했습니다. Leakage/Holdout 오류를 삼키지는 않습니다. 모델 사양·학습 마스크는 동일하고 최초/최종 predictions.csv와 metrics.json은 모델별 **바이트 동일**했습니다. 시간 파일은 재현성 동일성 대상에서 제외합니다.

최종 산출물:

```text
artifacts/day4/sarimax_20261027T021556181229Z/
artifacts/day4/lightgbm_20261027T021556175230Z/
  spec_freeze.json, predictions.csv, fold_fit_log.json,
  metrics.json, timing.json, manifest.json

artifacts/day4/comparison_20261027T021809505124Z/
  model_comparison.csv, common_success_comparison.csv,
  comparison.json, timing_comparison.json, manifest.json

artifacts/day4/environment.json
artifacts/day4/reproducibility_final_20261027.json
artifacts/day4/verification_comparison_20261027T021809505124Z.json
```

최초・중간 run도 덮어쓰지 않고 보존했습니다. Manifest는 모델 구현 코드 hash·고정 spec/config hash·데이터 hash·라이브러리/스레드·출력 hash를 기록합니다. 개별 fitted estimator를 직렬화한 weights 파일을 제공하는 것이 아니라, 동일 이력과 spec로 refit해 OOF 예측을 재현하는 단계입니다.

## 11. 테스트 및 독립 검증

전체 **119 passed in 13.40s**, exit code0. 기존 Day 0~3의100개가 모두 포함됩니다. Fake SARIMAX로 t-1 입력·2/3/4-step 매핑·입력기간·경고/비수렴/exception을 검증했고, fake LightGBM trainer로15열·h별 label·공동721개 마스크·future/holdout 차단을 확인했습니다. 실제 라이브러리 toy로 SARIMAX fit과 LightGBM seed 재현성도 검증했습니다.

공통 테스트는 동일 actual/scale/target/단위, 개선율 산술, 누락 키107개/불완전 모델의 비교 제한, 모든 fit 후 채점, 현재 feature 부족의 명시적 실패 기록을 포함합니다. 테스트에 실제 World Bank 가격이나 네트워크는 없습니다. Editable metadata 갱신 후 smoke3개도 별도로 통과했습니다.

실제 독립 검증 스크립트는 저장된 prediction에서 오차·MAE·MASE를 sum/count로 다시 계산하고 동일108개 키/actual/scale/unit을 확인했습니다. 기존 Day 3 코드 hash9개·baseline 출력 hash·원본/대표 CSV hash 보존 및 신규 모델 code/output hash를 확인해 passed였습니다.

최종 문서 확인: 로컬 Markdown 링크57개 정상, TOML6개 파싱 성공, 고정 split 해시 보존, lock11개와 설치 버전 일치, synthetic 폴더의 marker 외 데이터0개입니다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m food_procurement_intelligence.evaluation.model_backtesting --model sarimax
.\.venv\Scripts\python.exe -m food_procurement_intelligence.evaluation.model_backtesting --model lightgbm
.\.venv\Scripts\python.exe -m food_procurement_intelligence.evaluation.model_comparison --phases artifacts/day4/sarimax_20261027T021556181229Z artifacts/day4/lightgbm_20261027T021556175230Z
.\.venv\Scripts\python.exe scripts/verify_day4_results.py --phases artifacts/day4/sarimax_20261027T021556181229Z artifacts/day4/lightgbm_20261027T021556175230Z --comparison artifacts/day4/comparison_20261027T021809505124Z
```

새 실행은 새 디렉터리를 출력하므로 재실행 뒤에는 그 경로를 비교/검증 명령에 전달합니다. 같은 QA 출력 경로를 덮어쓰지 않으며 모든 명령을 다시 실행한 척하지 않았습니다.

## 12. 설계 위험과 해석

이번 validation에서는 SARIMAX가 전체와 각 horizon에서 상대적으로 유리했습니다. 이는 단순 고정 사양 간 이번 기간의 관측 결과이며 통계적 확정 우열·holdout 일반화·실제 비용 절감은 아닙니다. 108개 오차는38개 고유 target과 시계열 의존성을 공유합니다. 최신 수정본·가정 공표시각·2020-07 정의 변경·장기 nominal 이력의 한계가 남습니다. Shared-system-site-packages 환경과 호스트 성능 차이에 따른 재현/시간 한계도 있습니다.

## 13. Day 5 다음 작업 — 아직 미착수

1. 오늘의 point 예측과 모델별 실패/scale을 고정한 상태에서 quantile/interval 출력 schema와 공표된 OOF residual의 사용 시점을 정의합니다.
2. SARIMAX의 구간·LightGBM quantile 또는 과거 OOF 기반 보정을 별도 지시 범위에서 구현하되 미래 validation 정답으로 과거 구간을 보정하지 않습니다.
3. horizon별 Pinball Loss·80% coverage·구간 폭·교차/가격 양수성을 validation에서 평가하고 model-native 구간과 보정 효과를 분리합니다.
4. 시나리오 경로를 만들 때 horizon 간 의존성·planning/evaluation seed 분리를 설계합니다. Holdout은 계속 잠그고 구매 시뮬레이션/최적화는 아직 시작하지 않습니다.

Day 5는 별도 지시 후 진행합니다.
