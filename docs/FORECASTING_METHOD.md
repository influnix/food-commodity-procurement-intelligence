# 가격 예측 방법

## 특징과 학습 정보 경계

`features/price.py`는 origin별 공개 이력에서 15개 특징을 만듭니다. lag 1/3/6/12, 이동평균 3/6/12, 표본 표준편차 3/6/12(ddof 1), 월간·연간 변화, origin 월·target 월·예측 Horizon입니다. 가격 window는 target이 아닌 t−1에서 끝납니다. 필요한 과거값이 없으면 명시적으로 실패하며 보간·대체·scaling·전체 표본 특징 선택은 하지 않습니다. 달력과 Horizon은 사전에 알 수 있는 정보이고, 각 특징은 의존 관측월과 공표시각을 보존합니다.

TrainingBatch는 과거 origin 특징과 완전히 성숙한 3개 Horizon label을 결합합니다. 평가 t에서 학습 origin o는 o+3≤t−1 및 모든 실제 가용시각 조건을 만족해야 합니다. MASE scale은 각 origin에서 사용 가능한 계절 차이로 계산합니다. 정의되지 않거나 0인 scale은 이유를 붙인 null로 남기고 임의 epsilon으로 바꾸지 않습니다.

## 고정 모델 사양

| 모델 | 사양 |
|---|---|
| Seasonal Naive12 | target−12 관측 사용, 최신 관측값으로 대체하지 않음 |
| SARIMAX | 가격 수준 `(1,1,0)×(1,0,0,12)`, 추세·외생변수·로그·보간 없음, 정상성·가역성 제약, L-BFGS 최대 100회, 최소 120개월, origin마다 재학습 |
| LightGBM Direct | H1/H2/H3 독립 L2 회귀, 100rounds, learning rate .05, 7leaves, depth 3, min leaf 20, L2=1, 15개 특징, Horizon별 최소 120개 성숙 행, 완전 벡터 공통 마스크, seed 20261027, thread 1, deterministic·force_col_wise |

탐색·early stopping·학습 중 Validation 정답·재귀 Horizon 입력·숨은 fallback은 없습니다. SARIMAX는 t−1에서 4step을 생성해 index 1/2/3을 납품 H1/H2/H3으로 내보냅니다. 비수렴은 fold 실패입니다. 유효한 예측과 함께 발생한 경고는 기록하고 유지합니다. 점예측은 유한한 양수여야 합니다.

설정은 `configs/forecasting/models.toml`, `features.toml`에 있습니다. `configuration.load_spec('models', root)`로 고정 수치 사양을 읽을 수 있습니다. 공통 스키마는 단위·Horizon·origin 혼동을 막으며, LightGBM L2 점예측을 q50으로 바꾸지 않습니다.

## 예측 발행과 순차 평가

`publisher.NativeForecastPublisher`는 origin·cutoff·이력 식별자·마지막 성숙 label과 공표시각·특징/모델 사양·성공 이벤트를 기록합니다. 발행된 예측은 불변입니다. 과거 재구성 Legacy는 증거 등급을 유지하며 없는 Native 이력·세션·당시 실시간 발행 증거를 만들지 않습니다.

Validation은 2021-06..2024-05의 36개 origin에서 각 3개 target을 평가합니다. 예측 생성 후 Validation 전용 evaluator가 실제 label을 받습니다. 학습·출처·실패 기록을 보존하고, 일부 성공한 키의 성과를 전체 108개 결과로 보고하지 않습니다. fold별 MASE는 scale로 나눈 오차의 평균이며 전체 MAE를 무관한 공통 scale로 나눈 값이 아닙니다.

실제 MAE·MASE와 구매 성과는 [검증 결과](VALIDATION_RESULTS.md)에 있습니다. 예측 오차와 조달비용·수요 충족률·종료 가능성을 각각 평가합니다.
