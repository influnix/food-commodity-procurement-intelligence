# Day 3 실행 기록

실행일: **2026-10-27 Asia/Seoul**. Day 3 완료, Day 4는 미착수입니다. 고정 validation의 특징·Seasonal Naive·MAE/MASE만 구현하고 평가했습니다. SARIMAX/LightGBM, NASA 수집, 예측구간, 공급업체 시뮬레이션, 구매 최적화, 하이퍼파라미터 탐색, holdout 평가, 패키지 설치, Git commit/push는 수행하지 않았습니다.

## 1. 생성·수정 파일

신규 파일:

- `configs/day3.toml`: Day 2 split/config 해시, 고정 특징·계절주기·집계 방식
- `src/food_procurement_intelligence/features/__init__.py`, `features/price.py`: as-of 특징, 원천월 provenance, 미래 전처리용 mature TrainingBatch
- `src/food_procurement_intelligence/forecasting/__init__.py`, `forecasting/seasonal_naive.py`: target-12 가격과 검증된 예측 schema
- `src/food_procurement_intelligence/evaluation/forecast_metrics.py`: MAE, seasonal scale, fold/horizon/전체 MASE
- `src/food_procurement_intelligence/evaluation/backtesting.py`: validation 전용 실행 및 산출물 CLI
- `tests/test_day3_forecasting.py`: 실제 가격·네트워크 없는 toy 검증
- `scripts/verify_day3_results.py`: 독립 산술·as-of 분모·반복 출력 해시 대조
- `docs/FEATURES_AND_BASELINE.md`, 본 문서

수정 파일: `data/availability.py`에 validation-only 정답 reader와 값 없는 성숙도 assertion을 추가했습니다. 기존 as-of/bridge/holdout 접근 제한은 변경하지 않았습니다. README, AGENTS, PROJECT_CHARTER, EVALUATION_PROTOCOL, DATA_DICTIONARY, ROADMAP 및 SPLIT_DESIGN의 후속 기록을 갱신했습니다.

Day 0~2의 날짜 설정·실행 기록·artifact·원본·CSV는 덮어쓰지 않았습니다. Day 2의 다른 코드와 기존 테스트도 변경하지 않았습니다. availability.py의 additive 확장은 새 code hash로 Day 3 manifest에 기록합니다. 이전 run의 code hash와 현재 확장된 코드가 같다고 주장하지 않습니다.

## 2. Feature Engineering

15개 특징을 구현했습니다: origin 기준 lag 1/3/6/12, trailing mean/std 3/6/12, 최신 월간/전년 동월 변화율, origin/target calendar month, horizon. 가격 특징 12개는 t-1 이전 공개 관측만, 나머지 3개는 미리 알려진 달력/계획 정보입니다.

표준편차는 ddof=1, YoY는 `P_(t-1)/P_(t-13)-1`입니다. 모든 가격 특징의 원천 월과 가용시각을 저장했습니다. lookback 부족은 명시적 실패이며 0 대체·보간·scaling은 없습니다. 모델 fit을 위한 미래 전처리는 성숙한 과거 target과 해당 과거 origin 특징으로 만든 TrainingBatch에만 fit하도록 경계를 제공했습니다. 실제 learner/scaler fit은 없습니다.

정의·단위·출력 schema·lookback 범위는 [명세](FEATURES_AND_BASELINE.md)에 있습니다. 이번 실제 validation 특징은 108행이며 모두 필요한 이력을 충족했습니다. Seasonal Naive가 이 특징을 학습한 것은 아닙니다.

## 3. 정보 가용성과 누수 방지

- Day 2의 `history_as_of`, `feature`, `assert_feature_available`, target 성숙도 및 overlap 함수를 재사용했습니다.
- 모든 과거 학습 vector 후보는 `origin+3<=evaluation_origin-1`와 실제/가정 availability timestamp를 검사했습니다. 그 수를 fold audit에 기록하되 supervised fit으로 표현하지 않았습니다.
- 모든 108개 예측을 먼저 만든 뒤 evaluator가 validation-only 정답 reader를 요청합니다. 이 순서를 spy test로 확인했습니다.
- 정답 reader는 validation origin/target 범위와 공표·선택 freeze clock을 검사하며 train·bridge·holdout은 거부합니다. 개발 history의 첫 holdout origin 차단도 그대로입니다.
- 미래/bridge/holdout toy 값을 크게 바꿔도 과거 특징·예측·scale 및 validation 결과 전체가 불변임을 확인했습니다. 실제 데이터는 수정하지 않았습니다.
- `feature_asof_at`, `forecast_asof_at`은 모의 결정 정보 시각이고 실제 생성 시각은 manifest의 `created_at_utc`입니다. 실제 역사적 예측 파일이라고 오해할 필드명을 사용하지 않습니다.

잠금은 코드 인터페이스 경계이며 OS 수준의 raw 파일 봉인은 아닙니다. 최신 수정본에 가정된 발표시각을 부여한 pseudo-real-time 한계도 남아 있습니다.

## 4. Seasonal Naive

`predicted(target)=observed(target-12개월)`입니다. h=1/2/3 각각 t-11/t-10/t-9 가격을 참조하고 origin에서 공개됐는지 다시 검사합니다. 마지막 관측값 반복과 다릅니다. 모델명은 `seasonal_naive_12`, fitted parameter 수는 0입니다.

없는 참조 가격은 명시적인 실패로 기록하며 다른 baseline으로 대체하지 않습니다. target/horizon/cutoff/reference/monthly unit/가격 유효성/공표시각의 입력·출력 검증을 구현했습니다.

## 5. Validation Rolling-Origin 실행

경계는 그대로입니다: Train 원시 관측 1960-01~2021-06, validation target 2021-07~2024-08, bridge 2024-09, holdout target 2024-10~2026-09.

36 origins **2021-06~2024-05**, 3 horizon, **108개 키 모두 완전**합니다. 고유 target은 38개월이고 동일 target의 여러 origin 예측은 정상적으로 구분했습니다. 예측·특징 실패 0, 누락 키 0, 정의 불가능한 MASE 0입니다.

첫 history는 2021-05까지 737개월, 마지막은 2024-04까지 772개월입니다. 이전 validation 관측이 이후 origin에 공개되면 그때부터 history/scale에 포함했습니다. 당시 미공표였던 미래 target을 과거 입력에 넣은 것이 아닙니다.

## 6~7. 실제 MAE·MASE

| Horizon | N | MAE (USD/t) | MASE: fold as-of | MASE: 고정 초기 as-of |
|---|---:|---:|---:|---:|
| 1 | 36 | 100.1278 | 3.2304 | 3.4050 |
| 2 | 36 | 100.4889 | 3.2453 | 3.4173 |
| 3 | 36 | 99.4722 | 3.2142 | 3.3827 |
| 전체 | **108** | **100.0296** | **3.2300** | **3.4016** |

반올림 전 전체 MAE는 100.02962962962962, 주 MASE는 3.2299685467078207, 보조 MASE는 3.401634246490622입니다. 가격/단위는 nominal USD/metric tonne이며 별도 물가·환율 변환은 없습니다. 이 결과는 비용 절감이나 공급 안정성 개선의 실증 결과가 아닙니다.

## 8. MASE scale과 집계

주 분모는 각 origin의 공개된 history에서 `mean(abs(P_m-P_(m-12)))`입니다. 첫 fold는 725쌍, scale **29.406344827586206**; 마지막은 760쌍, scale **32.701578947368425**입니다.

비교용 고정 Train 기준은 **첫 fold에서 이용 가능한 ~2021-05**로 고정했습니다. 명목상 Train 끝 2021-06까지 넣으면 첫 origin에서 미공표 가격을 쓰므로 금지했습니다. 주 방식은 기존 EVALUATION_PROTOCOL의 expanding fold-as-of를 유지했고, 성과를 본 뒤 유리한 정의를 고르지 않았습니다.

fold별 3개 ratio 평균, horizon별 36 origins 동일 가중, 전체 108 pair 동일 가중입니다. ratio 평균을 사용하며 전체 MAE/평균 scale로 대체하지 않습니다. 분모 0 또는 pair 부족은 null과 상태를 남기고 undefined 개수를 공개합니다. 실제 108개는 모두 정의됐습니다. toy 상수열 테스트에서는 MAE=0이어도 MASE는 0/0 대신 null입니다.

## 9. 테스트와 실제 재현 검증

기존 Python 3.11.5 `.venv`에서 실행했습니다. 신규 외부 패키지·개발 도구 설치는 없습니다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m food_procurement_intelligence.evaluation.backtesting --config configs/day3.toml
```

최종 pytest: **100 passed in 1.79s**, exit code 0. 기존 74개를 전부 재실행했고 Day 3 검증 26개를 추가했습니다. 인공 선형열의 lag/rolling/std/변화율, seasonal 예측, MAE=12·MASE=1의 validation 결과와 손계산을 비교했습니다. 0·부족 분모, 미래/미공표 접근, 입력/출력 schema, 누락 사유, 36/108 완전성, 동일 target 다른 origin, 예측 후 채점 순서, 설정 복제·실제 파일 출력도 검증했습니다.

최종 기준 run:

```text
artifacts/day3/20261027T013028732383Z/
  validation_predictions.csv
  validation_features.csv
  feature_provenance.json
  fold_audit.csv
  metrics.json
  failures.json
  run_manifest.json
```

반복 run: `artifacts/day3/20261027T013029938690Z/`. 핵심 파일 6개가 바이트 해시까지 동일했습니다. manifest의 현재 실행시각/run 위치만 다릅니다. 초기 schema 확인 run 두 개도 덮어쓰지 않고 보존했으며 최종 보고는 위 ID를 기준으로 합니다.

```powershell
.\.venv\Scripts\python.exe scripts/verify_day3_results.py --reference-run artifacts/day3/20261027T013028732383Z --repeat-run artifacts/day3/20261027T013029938690Z
```

독립 검증 결과 **passed**, exit code 0. production metrics 함수를 호출하지 않고 sum/count 산술로 36개 scale·전체 MAE·MASE·고정 초기 MASE를 대조했습니다. 참조 가격, feature 원천월 cutoff, 예측 키 108개, 출력/input 해시도 검사했습니다. 기록은 `artifacts/day3/verification_20261027T013029938690Z.json`입니다. 실제 validation만 사용했으며 holdout 통계는 없습니다.

입력 원본 SHA-256은 `ea1c350827878ea3bbe30e3cda16a13fd3bd5b409b8458940dc94a36b5a33154`, 대표 CSV SHA-256은 `f5bc6a5a859285f0dd0ece5cea03d820a37efff157484fd31b45242cc4946025`로 유지됐습니다. split SHA-256도 Day 2 값 `209f2a35dea2bc0afc19461b6f780deb61d27b8cf5acaf5a2aaa10e5cd963741`과 같습니다.

최종 문서/무결성 확인: 로컬 Markdown 링크 43개 정상, manifest에 기록된 출력 해시 6개·코드 해시 9개 일치, Day 2 설정 2개와 Day 1 수집/추출 코드 해시 보존을 확인했습니다. TOML 5개 파싱 성공, synthetic 폴더의 marker 외 데이터 0개입니다.

## 10. 남은 한계

최신 수정본 snapshot을 당시 알고 있었다고 증명하지 못하며 공표시각도 가정입니다. 2020-07 품질 정의 경계와 장기 nominal scale의 해석 한계를 보존했습니다. Seasonal Naive의 MASE가 1이어야 하는 것은 아닙니다. 분모는 과거 in-sample의 12개월 차분이고 분자는 현재 validation의 2/3/4-step 오차이기 때문입니다.

특징 생성이 안전한 인터페이스와 테스트를 제공하더라도 후속 코드가 직접 전체 CSV를 읽거나 evaluator 정답을 predictor에 전달하면 경계를 우회할 수 있습니다. AGENTS에 그 금지를 기록했습니다. FeatureSpec의 예측 유용성, 추가 모델, calibration, 실제 구매 성과는 아직 평가하지 않았습니다.

## 11. Day 4 구체적인 다음 작업 — 아직 미착수

1. 별도 지시 범위 안에서 SARIMAX부터 같은 Prediction/origin/target/unit 계약에 연결하고, 이후 LightGBM direct-horizon 입력을 TrainingBatch로 구성합니다.
2. 모델별 lag·학습 이력·전처리 요건을 추가 마스크로 명시하고 validation만으로 검증합니다. 현재 날짜 split과 holdout 잠금은 유지합니다.
3. 같은 36 origins/108쌍에서 모델별 MAE·동일 fold MASE, 누락/실패/fallback, 계산비용을 비교합니다. 탐색 범위는 Day 4 지시 전에 실행하지 않습니다.
4. 필요한 라이브러리는 기존 프로젝트 환경의 가용성과 호환성을 먼저 확인하고 필요한 범위에서만 다룹니다. 오늘 설치/모델 구현은 하지 않았습니다.

Day 4는 별도 지시를 받은 뒤 진행합니다.
