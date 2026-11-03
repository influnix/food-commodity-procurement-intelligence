# Day 5 실행 기록

2026-10-29 Asia/Seoul. **Day 5 완료**. 구현·전체 pytest·두 번의 실제 실행·독립 검산·예측 재현성 확인을 완료했습니다. Holdout 잠금을 유지하며 Day 6는 시작하지 않았습니다.

## 1. 생성·수정 파일

신규:

- `configs/day5.toml`: Coverage 확인 전에 고정한 Historical OOF·보정·가격 유효성·위험 신호 사양
- `src/food_procurement_intelligence/uncertainty/__init__.py`
- `src/food_procurement_intelligence/uncertainty/contracts.py`: 별도 불변 uncertainty 출력 계약
- `src/food_procurement_intelligence/uncertainty/models.py`: SAR native PI, direct quantile9개와 L2 연결 검산
- `src/food_procurement_intelligence/uncertainty/calibration.py`: OOF provenance, 달력 순서 release, 모델·h별 보정
- `src/food_procurement_intelligence/evaluation/uncertainty_metrics.py`: 유효 분모가 명시된 Pinball·Coverage·Width
- `src/food_procurement_intelligence/evaluation/uncertainty_backtesting.py`: 전체 walk-forward·구간 생성 후 채점·새 run 저장
- `tests/test_day5_uncertainty.py`: 실제 가격을 포함하지 않는 toy 테스트23개
- `scripts/verify_day5_results.py`: 독립 산술·공표 clock·학습 proof·기존 파일 보존·반복 해시 검증
- `docs/DAY5_UNCERTAINTY_DESIGN.md`, `docs/UNCERTAINTY_COMPARISON.md`, 본 문서

수정은 AGENTS·README·ROADMAP·EVALUATION_PROTOCOL·DATA_DICTIONARY·PROJECT_CHARTER의 새 단계 설명입니다. Day 0~4 구현 코드·테스트·설정·실제 데이터·기존 결과153개 파일은 보존 snapshot 해시와 일치합니다. 기존 Day 4 모델 명세·모델 비교·실행 기록은 변경하지 않습니다.

## 2. 고정 사양과 환경

`configs/day5.toml` SHA-256은 `d6b9ae26578ddba3daafc27d01359df762166576e6b41b853edfbbea93fe48ad`입니다. Day 4 config SHA `0ad6ddbb368349fd9b57afe54bec4e4ce83acca099b2e0bca23f3b4ede724b8e`와 split SHA `209f2a35dea2bc0afc19461b6f780deb61d27b8cf5acaf5a2aaa10e5cd963741`를 유지합니다.

기존 `.venv` Python3.11.5 / statsmodels0.14.6 / LightGBM4.6.0 / NumPy1.26.4 / SciPy1.17.1 / pandas2.2.3을 재사용했습니다. 신규 패키지 설치와 외부 데이터 다운로드는0건입니다. Seed20261027, LightGBM thread1·deterministic·force_col_wise, CLI 프로세스의 BLAS/OpenMP thread1도 Day 4와 같습니다. 전역 환경은 변경하지 않습니다.

## 3~4. SARIMAX와 Quantile 구현

SARIMAX `(1,1,0)x(1,0,0,12)`, trend n, 동일 fit 옵션을 유지했습니다. `get_forecast(steps=4,signal_only=False).conf_int(alpha=.2)`의2/3/4-step으로 관측가격 중앙80% PI를 만듭니다. Gaussian mean=median이며 Day 4 point와 일치했습니다. 계수 confidence interval과 구분하고 파라미터 추정 불확실성 전체를 반영한다고 주장하지 않습니다.

LightGBM은 Day 3의15개 특징과 완전 vector 성숙 TrainingBatch를 그대로 사용했습니다. 각h별 q=.1/.5/.9, 총9개 quantile model을 objective=quantile/alpha=q로 fit합니다. 나머지 복잡도·100 rounds·seed/thread는 Day 4와 같습니다. L2 point도 재계산해 보존 결과와 대조했으며 q50과 L2는108키 모두 다른 출력입니다. 탐색·early stopping·전역 전처리는 없습니다.

## 5~6. OOF 기간과 누수 방지

Historical origins2016-04~2021-03의60개는 Train 끝−3개월에서 거슬러5년을 취한 달력 사양입니다. target2016-05~2021-06은 모두Train이며 최소 학습 조건을 충족합니다. 두 모델의 Historical OOF360개와 마지막 Validation clock까지 성숙한 Validation OOF198개를 저장했습니다. 학습 cutoff/label publication proof와 실제값 publication timestamp를 모두 검사합니다.

잔차 사용 조건은 `o<t`, `o+h<=t−1`, `actual_available_at<=decision_at(t)`입니다. 각h를 따로 보정하므로 모든h를 기다리는 추가 embargo를 두지 않습니다. 모델 학습은 기존 `o+3<=t−1` 완전 vector 조건을 유지합니다. Bridge/Holdout은 어떤 pool에도 들어가지 않습니다. 원본 fit의 fitted residual을 쓰지 않았습니다.

첫 최소24개가 가능해지는 역사적 clock은 H1/H2/H3=2018-05/06/07이며 실제 보정은2021-06부터입니다. 첫보정n은60/60/59, 이후59~60입니다. 보정 audit216개에 선택한 잔차 키 전체·cutoff·최대공표 timestamp·finite rank를 저장했습니다. 과거 OOF 사양은 이미 Day 4 validation에서 사용한 모델이므로 독립적인 사전등록 실험은 아닙니다.

## 7~10. 확률예측 평가

정확한 전체/horizon별 Pinball·Coverage·Width는 [비교 보고서](UNCERTAINTY_COMPARISON.md)에 기록합니다. 각h당36개, 각모델·방법당108개가 완전하며 실제target은38개월입니다.

| 모델·방법 | 전체 Coverage | 평균 폭 USD/t | q10 / q50 / q90 Pinball |
|---|---:|---:|---|
| SARIMAX native | 48.15% | 60.9970 | 11.5259 /20.9379 /14.1751 |
| SARIMAX + rolling OOF | 61.11% | 84.4602 | NA: interval-only |
| LightGBM quantile | 58.33% | 164.6295 | 16.7111 /28.0725 /25.5526 |
| LightGBM + rolling OOF | 65.74% | 193.9608 | NA: interval-only |

모든h에서80% 미달입니다. 보정이 Coverage를 높였지만 폭도 넓어졌습니다. 성과를 본 뒤 설정을 조정하지 않았고 명목 Coverage 보장을 주장하지 않습니다. 원본 분위수와 보정 구간을 분리하며 보정 양끝에 임의 Pinball을 만들지 않습니다.

## 11. 표본·결측·실패·fallback

Raw SAR/LGB 각108개, calibrated216개, 합계432행 모두 valid입니다. 전체1,248 fit 이벤트 실패0, SARIMAX 비수렴0, crossing0, 음수/0 경계0, 비유한/누락0입니다. Calibration216/216 가능, 부족 fallback0입니다. 사전 fallback은 최소24개 미달일 때 원본 구간을 유지하고 `insufficient_raw_fallback`을 남기는 정책이며 toy 테스트에서 검증했습니다. 원본 fit 실패에는 다른 모델 대체가 없습니다.

마지막 validation clock에 미성숙인18개 OOF는 target 날짜만 pending으로 보존합니다. 이후 채점 정답으로 이 과거 pool을 다시 만들지 않습니다. 같은model+h 안 target 중복0, 서로 다른h의 같은target 공유 그룹186개는 상관성으로 기록했습니다.

Fit 경고0, LightGBM 첫 import에서 PyparsingDeprecationWarning13개가 기록됐습니다. 기존 optional plotting 의존성에서 나온 것으로 별도 분류했고 무관한 환경 변경은 없습니다. Native routine 로그 전체를 수집한 숫자로 해석하지 않습니다.

## 12. pytest와 독립 검산

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_day5_uncertainty.py
.\.venv\Scripts\python.exe -m pytest -q
```

신규23 passed in56.47s, 전체 **142 passed in89.69s**, exit0입니다. 기존119개를 모두 포함합니다. Toy 가격만 사용했으며 네트워크가 필요하지 않습니다. 테스트는 미래 label/availability 차단, Historical Train 범위, OOF 증명, h별 pool, 첫n=60/60/59, 미래 Validation 변경 시 과거 결과 불변, Holdout 변경 시 전체 Validation 결과 불변, 최소표본/fit실패, SAR step/API mapping, LGB objective/alpha, 실제 toy quantile 반복, crossing·음수·누락, 손계산·108키·같은 actual·모든 fit 후 채점을 포함합니다.

별도 스크립트는 실제 저장 결과의 Pinball·Coverage·Width·OOF score·finite quantile·보정폭을 sum/count와 order statistic으로 다시 계산했습니다. 216개 보정 입력의 날짜·timestamp·h·모델·학습 proof, 153개 기존 파일 해시, Day 4 point 연결과 동일 actual108키/고유target38개월을 확인해 passed입니다. 실제 World Bank 통합 검산은 pytest toy fixture와 분리했습니다.

## 13. 산출물과 재현성

첫 실제 run: `artifacts/day5/20261029T004616487272Z/`.

```text
spec_freeze.json
sarimax_native_intervals.csv, lightgbm_quantiles.csv, calibrated_intervals.csv
all_oof_forecasts.csv
historical_oof_calibration.csv, validation_oof_calibration.csv
calibration_audit.json, pending_oof_metadata.json
metrics.json, uncertainty_comparison.csv, risk_signals.csv
fit_log.json, failures_and_warnings.json, timing.json, manifest.json
```

Manifest는 데이터·원본·설정·코드·라이브러리·Day 4 point 연결 해시를 보존합니다. 개별 모델 weights를 직렬화하는 대신 동일 이력으로 refit하는 재현 계약입니다. run마다 새 폴더이며 시간/로그는 결정적 출력 비교에서 제외합니다.

반복 run은 `artifacts/day5/20261029T005316816984Z/`입니다. 두 run의 설정·코드 해시가 같고, native/quantile/calibrated 예측, 전체 OOF forecast, historical/validation 잔차 표, calibration audit, pending 날짜 목록, metrics, 비교 CSV, risk signals의 **11개 파일이 모두 바이트 동일**했습니다. 양쪽 실행의 독립 산술도 각각 passed입니다. 다른 운영체제·BLAS·공유 패키지 환경까지 bitwise 재현을 보증하지는 않습니다.

독립 검증: `artifacts/day5/verification_20261029T004616487272Z.json` passed. 기존파일 snapshot: `artifacts/day5/preservation_before.json`.

반복 검증: `artifacts/day5/verification_20261029T004616487272Z_repeat.json`, 두 번째 실행 독립 검증: `artifacts/day5/verification_20261029T005316816984Z.json`, 모두 passed입니다.

```powershell
.\.venv\Scripts\python.exe -m food_procurement_intelligence.evaluation.uncertainty_backtesting --config configs/day5.toml
.\.venv\Scripts\python.exe scripts/verify_day5_results.py --run artifacts/day5/20261029T004616487272Z
.\.venv\Scripts\python.exe scripts/verify_day5_results.py --run artifacts/day5/20261029T004616487272Z --repeat artifacts/day5/20261029T005316816984Z
```

첫 실행 wall400.4150s /fit62.9357s /batch준비323.7567s이며 추가 연산은 Historical OOF와9개 quantile 모델 및 L2 연결 검산에서 발생했습니다. 호스트 성능에 따라 달라집니다.

반복 실행은 wall370.8330s /fit58.8767s /batch준비298.5853s였습니다. 최종 QA는 기존153개 파일 해시 유지, 로컬 Markdown 링크74개 정상, TOML7개 파싱, 결정적 파일11개 동일, 설치 버전 유지와 synthetic 데이터 미생성을 확인했습니다. 기록은 `artifacts/day5/final_qa.json`입니다.

이미 존재하는 검증 JSON은 덮어쓰지 않습니다. 위 예시는 이번에 실제 실행한 명령이며, 새 검증을 만들 때는 새 backtest run 경로를 전달합니다. 테스트 코드와 실제 결과 통합 검증은 분리했습니다.

## 14. 가격 상승 위험과 현재 후보

마지막 공개가격×1.10을 넘는 raw q90 신호는 SAR34/108, LGB23/108이고 calibrated upper 신호는62/108,47/108입니다. 확률·공급 부족·비용 절감을 추정하지 않았습니다. 공동 가격 경로의 의존성·양수성·planning/evaluation seed는 설계 계약만 남겼습니다.

SARIMAX+rolling OOF를 구간 효율과 더 낮은 원본 Pinball에 근거한 우선 진단 후보로 권합니다. LightGBM 보정은 Coverage가4.63pp 높지만 폭이 훨씬 넓습니다. 둘 다80%에 미달하므로 보장된 구매 리스크 구간으로 채택하지 않습니다. 108개가 독립이라는 주장, Holdout 일반화, 최신 수정본의 엄밀한 당시 정보 재현은 하지 않습니다.

## 15. Day 6의 다음 작업 — 미착수

1. 이번 고정 결과를 보존한 상태에서 undercoverage와 폭의 실무 허용 조건, 후속 민감도 사양을 먼저 문서화합니다. 같은 Validation을 계속 독립 검증으로 취급하지 않습니다.
2. Horizon 간 동시 성숙 OOF 벡터, 잔차 의존성·양수성·tail·공동 가격 경로와 확률합 계약을 확정하고 planning/evaluation seed를 분리합니다. 세 분위수를 독립 표집해 경로로 연결하지 않습니다.
3. 사용자 지시 범위 안에서 공급업체·수요·납기 가정과 단위를 고정하고 월별 수령·수요·lost sales·재고·비용 ledger 및 Fixed 정책 toy 검산부터 진행합니다.
4. Holdout 진입·구매 최적화·비용 절감 평가는 해당 단계의 별도 지시까지 계속 보류합니다.

이번 작업에서 NASA·추가 데이터·공급업체 생성·가격 시나리오 생성·구매 시뮬레이션·최적화·대시보드·Git commit/push는 수행하지 않았습니다.
