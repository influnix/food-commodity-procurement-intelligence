# Day 4 사전 모델 사양

2026-10-27, 신규 모델의 실제 validation 실행 **이전**에 `configs/day4.toml`을 작성했습니다. 향후 run의 spec freeze와 manifest에 설정 사본/해시/실제 실행 순서를 남깁니다. 이 파일의 최초 사양을 성과에 맞춰 바꾸지 않습니다. 날짜 split과 Day 3 baseline은 보존합니다.

- SARIMAX: 가격 수준의 `(1,1,0)x(1,0,0,12)`, trend 없음, stationary/invertible parameter 제약, L-BFGS 최대100회. 차분으로 수준 추세를 처리하면서 AR1과 연간 AR1만 넣은 작은 사양입니다. 외생변수·로그변환·가격 보간 없음. 최소120개월의 연속된 가용 이력을 매월 처음부터 fit합니다. 마지막 관측 t-1에서 4-step을 생성해 index1/2/3을 납품 horizon1/2/3으로 사용합니다. 비수렴은 해당 fold 실패, 그 외 경고는 기록하고 유효 예측이면 유지합니다. 음수/비유한 예측은 실패이며 clip하지 않습니다.
- LightGBM: horizon별 독립 회귀 3개, 고정100 boosting rounds, learning rate0.05, 7 leaves, depth3, 최소 leaf20, L2=1. 기존 15개 특징, imputation/scaling 없음. raw nominal USD/t label을 예측합니다. 최소120개 학습 행/horizon. 전체 3-horizon vector의 label이 모두 평가 t-1까지 공표된 sample만 사용합니다. 따라서 h1/h2에 더 최근 행을 주지 않는 보수적인 공동 마스크입니다. Recursive 예측값을 다음 입력으로 넣지 않습니다. Validation/early stopping set을 fit에 전달하지 않습니다.
- Seed 20261027, LightGBM thread1·deterministic·force_col_wise 고정. SARIMAX는 RNG를 사용하지 않습니다. 실행 프로세스의 BLAS/OpenMP thread 환경도1로 기록합니다. 전역 환경변수는 변경하지 않습니다.
- 예측은 같은 단위의 공통 point schema로 내보내되 Seasonal Naive의 target-12 참조 제약을 다른 모델에 강요하지 않도록 새 공통 계약을 adapter로 제공합니다. 기존 Seasonal Naive 구현/결과는 변경하지 않습니다.
- 모델 오류·수렴 경고·훈련 범위·성숙도·fit 시간·구성을 fold별 기록합니다. fallback 없음. 모델 고유 coverage와 공통 성공 키 교집합 성과를 분리하며, 108개 불완전 모델을 완전 모델처럼 순위 매기지 않습니다.
- 동일한 validation actual·Day 3 fold별 MASE scale을 사용합니다. 모든 신규 모델의 예측 생성 후에만 evaluator가 validation 정답을 읽습니다. 반복 실행은 재현성 확인용이며 설정 탐색이 아닙니다.

근거 API: [statsmodels SARIMAX](https://www.statsmodels.org/v0.14.6/generated/statsmodels.tsa.statespace.sarimax.SARIMAX.html), [LightGBM 4.6 train](https://lightgbm.readthedocs.io/en/v4.6.0/pythonapi/lightgbm.train.html), [LightGBM 4.6 parameters](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html). 설치 버전은 완료 후 환경 기록에 고정하며 현재 미설치 상태를 성공으로 표시하지 않습니다.

완료 후 기록: 위 최초 사양은 그대로이며 실제 설치 버전과 검증은 [환경 기록](DAY4_ENVIRONMENT.md), 결과는 [모델 비교](MODEL_COMPARISON.md)에 분리했습니다. 시간 계측·실패 logging 보강은 모델 사양 변경이나 탐색이 아니며 최초/최종 예측과 지표의 동일성을 확인했습니다.
