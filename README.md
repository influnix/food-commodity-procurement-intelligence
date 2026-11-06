# Food Commodity Procurement Intelligence — 원자재 조달 의사결정

## 1. 프로젝트 개요

**월별 밀 가격 예측을 구매 계획·재고 흐름·비용·공급 서비스 평가로 연결한 데이터사이언스 포트폴리오입니다.** 가격을 잘 예측하는 모델이 실제 구매 의사결정에서도 더 나은 결과를 내는지 같은 운영조건에서 검증합니다.

MVP 수용 기준은 **5/5 PASS**입니다. 실제 최종 Holdout은 **미평가·잠금** 상태이며, 실제 원천·시드의 실행 연결(Source/Seed Runtime)은 **NOT_VERIFIED**입니다.

## 2. 해결하려는 비즈니스 문제

구매 담당자는 낮은 가격뿐 아니라 공급업체의 납기와 공급 용량, 보유 재고, 부족 시 손실을 함께 고려해야 합니다. 이 프로젝트는 가격 예측 오차와 구매 성과를 별도로 측정하고, 정확도 개선이 총비용과 수요 충족률 개선으로 이어지는지 확인합니다.

## 3. 전체 시스템 아키텍처

```mermaid
flowchart LR
  A[World Bank 원천과 시점별 가용성] --> B[의사결정 시점별 특징]
  B --> C[Seasonal Naive / SARIMAX / LightGBM]
  C --> D[Horizon별 보정 / 공동 시나리오]
  C --> E[결정론적 구매 LP]
  D --> F[시나리오 RN / CVaR LP]
  E --> G[현재 발주만 실행]
  F --> G
  H[고정 구매 정책] --> I[재고와 수령월 비용 엔진]
  G --> I
  I --> J[비용 / 서비스 / 순차 평가]
```

세 납품월의 가격을 예측해 공급업체별 발주를 계획하고, 현재 주문만 확정한 뒤 다음 달에 다시 최적화합니다. 정책마다 재고 상태를 분리하고 동일한 외생 경로로 비교하며, 입력·해·회계 검증에 실패하면 명시적으로 중단합니다.

## 4. 핵심 기능

- World Bank 원본 구조·단위 검사, 수집 Snapshot 추적, 제한된 원천 검증
- As-Of 특징 생성, 성숙한 학습 타깃, 순차적 백테스트와 예측 발행 증거 관리
- Horizon별 구간 보정과 완전 벡터 OOF 공동 시나리오: 최근 60개·최소 24개, 128경로
- 납기·발주 용량을 반영한 LP, 위험중립·CVaR 위험회피 정책, 재고·비용 회계
- 7개 정책 비교, 운영조건 민감도, 실패 상태 기록과 저장 결과 독립 검산

구현은 `src/food_procurement_intelligence/`의 data/features/forecasting/uncertainty/optimization/policies/simulation/evaluation 패키지로 구성됩니다. 설정은 `configs/` 아래 기능별로 구분합니다.

## 5. 데이터 및 시점별 정보 가용성

World Bank Pink Sheet의 **Wheat US HRW, 명목 USD/metric tonne**을 사용합니다. 월말 t에는 관측월이 t−1 이하이고 공표시각이 의사결정 시각 이하인 자료만 사용할 수 있습니다. H1/H2/H3의 납품 타깃은 t+1/t+2/t+3이며, 최신 관측 기준 2/3/4개월 앞입니다.

학습에 쓰는 과거 origin o의 완전 타깃은 o+3≤t−1이고 모두 공표된 상태여야 합니다. 현재 수정 Snapshot과 가정한 공표 지연을 사용하므로 평가는 **pseudo-real-time**입니다. 실제 과거 Vintage는 미검증이며 원천·가공 가격과 대규모 실행 기록은 Git에 포함하지 않습니다.

## 6. 예측 모델과 평가 방법

Seasonal Naive, SARIMAX, LightGBM Direct를 고정 사양으로 비교합니다. 개발 검증은 2021-06..2024-05의 **36개 origin × 3 Horizon = 모델별 108개 예측**입니다. 타깃은 2021-07..2024-08의 38개 고유 월이며 서로 겹칩니다. 108개 오차를 독립 표본으로 취급하지 않습니다.

## 7. 구매 정책 및 최적화

정기 고정 구매(Fixed), 점예측 기반 구매(FA), 시나리오 위험중립(RN), CVaR 위험회피(RA)를 비교합니다. SARIMAX·LightGBM별 FA/RN/RA와 Fixed를 합쳐 7개 정책입니다. 납기·용량·기존 pipeline을 반영하고 수령월 가격으로 비용을 한 번만 계상합니다. 동일 모델 RN/RA는 같은 Planning 시나리오를 사용합니다.

## 8. 핵심 Validation 결과

| 예측 모델 | MAE (USD/t) | 시점별 MASE |
|---|---:|---:|
| Seasonal Naive |100.0296|3.2300|
| SARIMAX |**41.8757**|**1.3624**|
| LightGBM Direct |48.6620|1.5912|

| 대표 구매 정책 | 총 시뮬레이션 비용 (USD) | 수요 충족률 | 부족량 |
|---|---:|---:|---:|
| Fixed |**1,351,501.68**|**100%**|**0t**|
| Forecast-Aware SARIMAX |1,365,914.16|99.4737%|20t|

SARIMAX의 MAE는 기준보다 58.14% 낮았지만, FA 구매비용은 **14,412.48 USD(+1.0664%) 높았습니다.** 추가 5개 정책·CVaR·11개 운영조건 민감도는 [검증 결과](docs/VALIDATION_RESULTS.md)에서 확인할 수 있습니다.

## 9. 비즈니스 관점의 인사이트

**예측 정확도가 높아져도 실제 구매비용이 반드시 감소하는 것은 아닙니다.** 매입·보관비 감소를 부족 비용과 Runoff 제약이 상쇄했습니다. 가격 예측과 함께 납기·재고·용량·종료조건·서비스 손실을 평가해야 합니다.

이는 **실제 Validation 가격을 사용한 가상 구매 운영 시뮬레이션**입니다. 실제 기업의 절감 실적·인과효과·최종 Holdout 성능이 아닙니다. 합성 Native/Legacy 통합 검증도 실제 시장 원천 연결의 검증과 구분합니다.

## 10. 설치 및 실행 방법

Python 3.11과 활성화한 가상환경을 사용합니다.

```sh
python -m venv .venv
# 사용하는 셸의 표준 명령으로 생성한 가상환경을 활성화합니다.
python -m pip install -r requirements/runtime-lock.txt
python -m pip install pytest==8.3.5
python -m pip install --no-deps -e .
python scripts/ci/run_contract_tests.py
python scripts/validation/run_synthetic_checks.py
python scripts/release/audit.py
```

## 11. 테스트와 재현성

계약 테스트 **330개 전체**를 원천 없는 환경에서 실행합니다. 합성 진입점은 7개 정책의 엔진·LP, 공동 시나리오, 미래정보 변경 불변성, λ 경계와 비예견성 검증 **6개**를 실행합니다. 6개는 330개의 부분집합이며 336개의 고유 테스트가 아닙니다.

두 진입점은 원천 가격·제외된 로컬 Evidence를 읽지 않고 테스트 중 네트워크 연결을 차단합니다. 과거 전체 613개 통과 기록은 별도 로컬 archive에 의존합니다. 전체 622개 항목이 수집되더라도 깨끗한 저장소에서 전부 실행했다고 주장하지 않습니다. [재현성 안내](docs/REPRODUCIBILITY.md)에 범위와 데이터 준비 조건을 구분했습니다.

## 12. 기술적 한계

명목 80%에 못 미친 구간 Coverage, 경험적 시나리오 확률, 단일 원재료·시장경로, 수정 데이터, 가상 운영, Validation 선택편향과 계획창·Runoff·말기 근사가 남습니다. [연구 및 운영상 한계](docs/LIMITATIONS_AND_FUTURE_WORK.md)를 참고하세요.

실제 원천·시드 연결은 **NOT_VERIFIED / ACCESS_APPROVAL_REQUIRED**입니다. 실제 Bridge/Holdout 읽기·학습·구매평가·잠금 해제는 비활성입니다. 저장소는 PRIVATE이며 코드 라이선스는 소유자가 아직 선택하지 않았습니다.

## 13. 상세 기술 문서

| 주제 | 문서 |
|---|---|
| 목적·입출력·사용 사례·API | [제품 개요](docs/PRODUCT_OVERVIEW.md) |
| 파이프라인과 정보 소유 경계 | [시스템 아키텍처](docs/SYSTEM_ARCHITECTURE.md) |
| 원천·As-Of·Legacy 증거 | [데이터 및 시점별 정보 가용성](docs/DATA_AND_ASOF_CONTRACT.md) |
| 특징·모델·순차 평가 | [가격 예측 방법](docs/FORECASTING_METHOD.md) |
| 유효성·구간 보정·공동 경로 | [불확실성과 시나리오](docs/UNCERTAINTY_AND_SCENARIOS.md) |
| LP·CVaR·재고 및 비용 회계 | [구매 의사결정 최적화](docs/PROCUREMENT_OPTIMIZATION.md) |
| 예측·정책·운영조건별 결과 | [검증 결과](docs/VALIDATION_RESULTS.md) |
| 안전한 실행·환경·재현 범위 | [재현성](docs/REPRODUCIBILITY.md) |
| 연구 한계·확장 가능성 | [연구 및 운영상 한계](docs/LIMITATIONS_AND_FUTURE_WORK.md) |
