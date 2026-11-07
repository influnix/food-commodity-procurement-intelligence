# 가격 예측 방법

가격 이력을 더 복잡하게 모델링할 가치가 있는지 보려면 먼저 작년 같은 달 가격을 쓰는 규칙을 넘어서는지 확인해야 합니다. 이 기준 옆에 계절 시계열 모형인 SARIMAX와, 최근 가격의 수준·변동을 특징으로 받는 LightGBM을 뒀습니다. 세 모델을 같은 결정일과 같은 납품월에서 비교했습니다. 각 fold에서는 사양을 고정하고 당시 학습에 쓸 수 있는 이력으로만 모델을 적합했습니다.

## 특징과 학습 정보 경계

이동평균을 납품월까지 계산하면 예측할 가격이 입력에 섞입니다. 그래서 `features/price.py`는 과거 학습 행도 각 origin의 공개 이력으로 다시 만들고, 가격 window를 t−1에서 닫습니다. 15개 특징은 lag 1/3/6/12, 이동평균 3/6/12, 표본 표준편차 3/6/12(ddof 1), 월간·연간 변화, origin 월·target 월·예측 Horizon입니다. 달력과 Horizon은 사전에 아는 정보입니다. 가격에 의존하는 특징은 관측월과 공표시각을 남기고, 필요한 이력이 없으면 실패로 기록합니다. 보간·대체·scaling·전체 표본 특징 선택은 하지 않습니다.

학습에 들어가는 과거 origin o의 특징은 당시 시점으로 계산하되, label을 붙일 수 있는지는 현재 학습 시점 t에서 판단합니다. TrainingBatch는 o+3≤t−1이고 세 label의 가용시각 조건도 충족할 때 그 사례를 담습니다. 가격 오차의 크기를 당시 계절 변동과 비교하는 MASE scale도 각 origin에서 사용 가능한 이력으로 계산합니다. 정의되지 않거나 0인 scale은 사유와 함께 null로 남깁니다.

## 고정 모델 사양

| 모델 | 사양 |
|---|---|
| Seasonal Naive12 | target−12 관측 사용, 최신 관측값으로 대체하지 않음 |
| SARIMAX | 가격 수준 `(1,1,0)×(1,0,0,12)`, 추세·외생변수·로그·보간 없음, 정상성·가역성 제약, L-BFGS 최대 100회, 최소 120개월, origin마다 재학습 |
| LightGBM Direct | H1/H2/H3 독립 L2 회귀, 100rounds, learning rate .05, 7leaves, depth 3, min leaf 20, L2=1, 15개 특징, Horizon별 최소 120개 성숙 행, 완전 벡터 공통 마스크, seed 20261027, thread 1, deterministic·force_col_wise |

월말 t에서 최신 관측은 t−1까지이므로, 납품월 t+1은 모델 기준 두 번째 step입니다. SARIMAX는 4step을 생성해 index 1/2/3을 H1/H2/H3으로 내보냅니다. LightGBM Direct는 Horizon마다 별도 회귀를 학습하므로 앞 달의 예측을 뒤 달의 입력으로 사용하지 않습니다. 고정 사양 그대로 학습하며 탐색·early stopping·학습 중 Validation 정답은 사용하지 않습니다. 비수렴은 fold 실패로 남깁니다. 유한한 양수 예측을 낸 경우에도 경고는 기록하고, 모델 실패 시 숨은 fallback은 두지 않습니다.

설정은 `configs/forecasting/models.toml`, `features.toml`에 있습니다. `configuration.load_spec('models', root)`로 고정 수치 사양을 읽을 수 있습니다. 공통 스키마는 단위·Horizon·origin 혼동을 막으며, LightGBM L2 점예측을 q50으로 바꾸지 않습니다.

## 예측 발행과 순차 평가

`publisher.NativeForecastPublisher`는 origin·cutoff·이력 식별자·마지막 성숙 label과 공표시각·특징/모델 사양·성공 이벤트를 기록합니다. 발행된 예측은 불변입니다. 과거 재구성 Legacy는 증거 등급을 유지하며 없는 Native 이력·세션·당시 실시간 발행 증거를 만들지 않습니다.

Validation은 2021-06..2024-05의 36개 origin을 순서대로 이동하며 각 3개 target을 평가합니다. 예측을 만든 다음 Validation 전용 evaluator에 label을 전달합니다. 전체 108개 키의 완전성을 먼저 확인하고, 학습·출처·실패 기록으로 빠진 키를 추적합니다. MASE는 오차를 각 fold의 scale로 나눈 뒤 평균하므로 fold별로 가격이 흔들리던 정도를 반영합니다.

실제 MAE·MASE와 구매 성과는 [검증 결과](VALIDATION_RESULTS.md)에 있습니다. 예측 오차와 조달비용·수요 충족률·종료 가능성을 각각 평가합니다.
