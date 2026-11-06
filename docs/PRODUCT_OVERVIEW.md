# 제품 개요

Food Commodity Procurement Intelligence는 월별 밀 구매를 위한 재현 가능한 의사결정 지원 연구 시스템입니다. 구매 분석가·데이터사이언티스트·평가자가 예측 오차뿐 아니라 비용과 공급 서비스를 함께 검토하도록 설계했습니다.

## 지원하는 의사결정

월말에 납기·가격 할증·발주 용량이 다른 두 공급업체에 현재 주문을 배분합니다. 세 납품월을 계획하되 현재 주문만 실행하고, 다음 달에 새로 공개된 정보로 다시 최적화합니다. Fixed, 예측 기반 FA, 시나리오 위험중립 RN, 위험회피 RA를 동일한 외생 조건과 독립된 재고 상태에서 비교합니다.

| 입력 | 사용 계약 | 출력 |
|---|---|---|
| 월별 Wheat US HRW 관측 | 명목 USD/metric tonne, 원천·Snapshot·공표 메타데이터, As-Of 접근 | origin별 특징과 가용 이력 |
| 고정 모델 사양 | Seasonal Naive, SARIMAX, LightGBM Direct, H1/H2/H3 | 불변 예측, 학습·발행 증거, 지표 |
| 성숙한 OOF 예측과 관측 | Horizon별 보정과 완전 벡터 Joint 성숙을 구분 | 통계 구간과 공동 Planning 시나리오 |
| 공개된 재고·pipeline·공급·비용 가정 | 미래 실제 가격·수요·지연 제외 | 현재 발주, 미래 계획, 검산한 solver 상태 |
| 평가 엔진이 소유한 외생 경로 | 정책과 분리, 수령월 정산 | 입고·재고·부족·비용·수요 충족률 원장 |

## 구현 범위와 검증 근거

MVP의 다섯 수용 기준은 월별 예측, 순차적 백테스트, 동일 조건의 대표 2개 정책 비교, 원천부터 비용까지의 추적, 저장 결과 검산 재현입니다. 기존 검증 기록에서 모두 통과했습니다. 확장 기능으로 추가 5개 정책, CVaR, 운영조건 민감도, 출처를 보존한 순차 예측과 Legacy 복원을 유지합니다.

개발 Validation은 실제 시장가격과 가상 운영조건을 사용했습니다. 별도의 합성 통합 검증은 소프트웨어 경계를 확인한 결과입니다. [검증 결과](VALIDATION_RESULTS.md)에는 SARIMAX 정확도 개선이 구매비용 감소로 이어지지 않은 결과도 그대로 보고합니다.

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
