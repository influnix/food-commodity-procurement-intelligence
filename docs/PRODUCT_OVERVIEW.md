# 제품 개요

월말에 밀을 주문한다고 가정해 보겠습니다. 할증이 낮은 업체는 도착까지 두 달이 걸리고, 한 달 만에 받을 수 있는 업체는 더 비쌉니다. 싼 쪽에 물량을 몰면 당장 필요한 양을 제때 채우지 못할 수 있습니다. 반대로 빠른 업체에 여유 있게 주문하면 할증과 보관비가 늘어납니다. 이 프로젝트에서 비교한 것은 같은 가격과 수요를 겪었을 때 어떤 주문 규칙이 이 균형을 더 잘 맞추는가입니다.

## 한 달에 한 번 정하는 발주량

월말에 정하는 값은 두 공급업체에 지금 주문할 수량입니다. 향후 세 달의 도착 물량과 재고까지 계산하는 이유는 이번 주문이 나중에 어떤 제약을 남기는지 보기 위해서입니다. 미래 주문은 계획으로 남겨 두고, 다음 달에 갱신된 정보로 다시 정합니다.

Fixed는 정해진 배분을 반복하고, FA는 한 가지 가격 예측을 보고 주문합니다. RN은 여러 가격 경로의 평균비용을, RA는 평균과 고비용 경로의 꼬리 평균을 함께 봅니다. 같은 가격·수요·지연 경로를 적용하되 정책별로 실제 주문과 재고를 별도 장부에 남겨, 비용 차이를 매입·보관·부족 등으로 나눠 확인할 수 있게 했습니다.

| 입력 | 사용 계약 | 출력 |
|---|---|---|
| 월별 Wheat US HRW 관측 | 명목 USD/metric tonne, 원천·Snapshot·공표 메타데이터, As-Of 접근 | origin별 특징과 가용 이력 |
| 고정 모델 사양 | Seasonal Naive, SARIMAX, LightGBM Direct, H1/H2/H3 | 불변 예측, 학습·발행 증거, 지표 |
| 성숙한 OOF 예측과 관측 | Horizon별 보정과 완전 벡터 Joint 성숙을 구분 | 통계 구간과 공동 Planning 시나리오 |
| 공개된 재고·pipeline·공급·비용 가정 | 미래 실제 가격·수요·지연 제외 | 현재 발주, 미래 계획, 검산한 solver 상태 |
| 평가 엔진이 소유한 외생 경로 | 정책과 분리, 수령월 정산 | 입고·재고·부족·비용·수요 충족률 원장 |

## 이 결과로 답할 수 있는 질문

월별 예측, 순차적 백테스트, 동일 조건의 대표 2개 정책 비교, 원천부터 비용까지의 추적, 저장 결과 검산 재현을 MVP 수용 기준으로 삼았습니다. 기존 검증 기록에서 다섯 기준을 충족했고, 비교를 7개 정책과 운영조건 민감도로 넓혔습니다. 예를 들어 부족 비용을 높이면 주문 정책의 순위가 유지되는지, 비용이 늘었다면 어느 항목에서 늘었는지를 장부로 확인할 수 있습니다.

개발 Validation에서 시장가격은 실제 관측이고 공급·수요·비용은 가정입니다. 따라서 답할 수 있는 질문은 이 운영조건에서 정책 간 차이가 얼마였는가입니다. 별도의 합성 통합 검증은 주어진 입력에서 정보 경계와 회계가 맞는지를 확인합니다. [검증 결과](VALIDATION_RESULTS.md)

## 주요 Python 인터페이스

`configuration.CONFIG_FILES`의 기능별 이름과 `load_spec(name, root)`로 설정을 찾을 수 있습니다.

- `data.availability.DevelopmentPriceStore`, `data.sequential.SequentialObservationStore`: 공개된 관측만 제공
- `features.price.build_features`, `forecasting.seasonal_naive.predict`, 두 모델 모듈의 `fit_predict`: 특징과 예측 생성
- `forecasting.publisher.NativeForecastPublisher`, `forecasting.legacy.LegacyReconstructedForecast`, `planning_points`: 증거 등급은 구분하면서 공통 수치 Planning 뷰 제공
- `uncertainty.horizon_sequential.HorizonSequentialOOF`, `provenance_sequential.ProvenanceSequentialOOF`: 성숙도를 반영한 보정·Joint 수명주기
- `optimization.deterministic.solve_plan`, `scenario_lp.solve_risk_plan`, `policies.*`, `simulation.engine.run_simulation`: 계획·발주·재고 실행
- `evaluation.policy_backtest.run_historical_policy`, `sequential_runner.run_policy_calendar`: 정책 비교·상태 분리·회계 검증

API 사용이 실제 데이터 접근 권한을 부여하지는 않습니다. 안전한 실행 명령은 [재현성](REPRODUCIBILITY.md)에 있습니다. 실제 Source/Seed Runtime은 NOT_VERIFIED이며, 최종 Holdout은 미평가·잠금 상태입니다.

## 문서 탐색

[아키텍처](SYSTEM_ARCHITECTURE.md) · [데이터와 As-Of](DATA_AND_ASOF_CONTRACT.md) · [가격 예측](FORECASTING_METHOD.md) · [불확실성](UNCERTAINTY_AND_SCENARIOS.md) · [구매 최적화](PROCUREMENT_OPTIMIZATION.md) · [연구 한계](LIMITATIONS_AND_FUTURE_WORK.md)
