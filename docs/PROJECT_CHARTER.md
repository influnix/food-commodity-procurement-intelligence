# 프로젝트 헌장

상태: Day 0 설계 / 2026-10-24 (Asia/Seoul). 이 문서는 구현 완료나 실증 성과를 의미하지 않습니다.

## 비즈니스 문제와 성공의 의미

식품 제조기업 구매 담당자는 가격·공급·수요 불확실성 아래 공급업체와 월별 발주 물량을 결정합니다. 예측의 목적은 낮은 오차 자체가 아니라 재고·보관비·부족 비용을 함께 고려한 의사결정입니다.

주 연구 질문: 동일한 실제 시장가격 경로와 가상 운영조건에서 Forecast-Aware 및 Risk-Aware 정책은 Fixed 정책 대비 총비용, 미충족 수요율, tail risk를 얼마나 바꾸는가?

최종 성공 기준은 (1) 정보 시점과 출처를 추적하는 재현 가능한 전체 흐름, (2) 세 정책의 공정한 비교, (3) 예측 품질과 정책 성과의 분리, (4) 이득이 없어도 설명 가능한 결과입니다. 비용 절감률의 임의 목표를 달성하도록 가정을 조정하지 않습니다. 개선 주장은 paired 비용 차이와 서비스 차이, 구간 추정, 가정 민감도를 함께 제시할 때만 허용합니다. 특정 기업의 실제 성과나 정책의 인과효과로 해석하지 않습니다.

## 단계적 MVP

1. Wheat 한 계열, 월별 빈도, USD·metric tonne로 단위를 맞춥니다. 정확한 원천 계열은 Day 1 확인 후 고정합니다.
2. Seasonal Naive로 예측과 구매 평가를 먼저 연결합니다. SARIMAX와 LightGBM은 이후 같은 평가 계약에 추가합니다.
3. 가격만 사용하는 모델을 기본으로 하고, 근거 있는 생산지역과 lag가 확인될 때만 날씨를 추가합니다.
4. 공급업체 2곳, 확정적 100 t/월 수요 예측, 가상 수요 오차·납기 지연, 단일 창고와 lost sales를 사용합니다.
5. 고정 구매 → 점예측 기반 기대비용 최소화 → 가격·납기·수요 시나리오와 CVaR 기반 위험 정책을 비교합니다.
6. Wheat 평가가 검증된 후 Soybean Oil로 외적 타당성을 확인합니다. 다품목 공동 용량·환율·관세·품질·환헤지·부패는 MVP 밖입니다.

Day 0~4의 설계·데이터·특징·점예측 비교에 이어 Day 5에는 native/quantile 구간과 공표된 OOF 기반 보정·평가를 추가했습니다. 보정 후에도80% Coverage에 미달하며 [비교 결과](UNCERTAINTY_COMPARISON.md)를 그대로 공개합니다. 공동 가격 경로는 설계 단계이며 시뮬레이션·최적화·정책 비교는 아직 없습니다. 예측 성과를 비용 절감 실적으로 해석하지 않습니다.

Day 6 갱신: [공동 OOF 경로와 Fixed Toy 엔진](DAY6_STATUS.md)을 구현했습니다. 경험적 경로의 동일origin 의존성과 정보 시점을 검증했고, 실제가격을 사용한 정책 평가 없이 가상 가격·수요·납기의 ledger를 손계산했습니다. 최적화·실제 정책 성과 비교와 Day 7은 아직 없습니다.

Day 7 갱신: [Deterministic LP와Forecast-Aware](DAY7_STATUS.md)의손계산·동일Toy비교·저장Forecast계획smoke를완료했습니다. 기존엔진·분할·예측·불확실성결과를보존했고실제Validation구매성과·위험최적화는아직없습니다. 납품월연동계약에서발주가가격을고정한다고해석하지않습니다.

## 아키텍처와 경계

| 후속 모듈 | 입력 → 출력 | 책임 / 금지 사항 |
|---|---|---|
| data | 원본+manifest → 정규화 관측표 | 출처·단위·vintage·가용 시점 보존; 가격을 합성하지 않음 |
| features | origin+사용 가능 관측 → 특징 | as-of 필터 뒤 lag/rolling; 미래 실제 값 접근 금지 |
| forecasting | fold별 학습표 → target별 점예측 | Seasonal Naive, SARIMAX, LightGBM 공통 출력 |
| uncertainty | 과거 검증 잔차/quantile → 구간·시나리오 | 미래 잔차로 보정 금지; horizon 간 의존성 고려 |
| simulation | 실제 가격+가상 외생 경로+발주 → 정산·재고 | 미래 경로를 보유하는 유일한 실행 경계 |
| optimization | 예측·현재 상태·계약조건 → 계획 | 실제 미래값 직접 접근 금지; solver 실패 명시 |
| policies | decision context → 현재 발주 | 동일한 정보 구조; 알려진 주문과 재고만 사용 |
| evaluation | 예측/운영 ledger → 지표·paired 비교 | holdout 잠금, 비용 중복 계산 방지, 가정 민감도 |

저장 구조는 `raw → interim → processed`와 `synthetic`을 분리합니다. 모델 출력 및 실행 manifest는 `artifacts/<run_id>`에 둡니다. 현재는 최소 구조만 생성합니다.

핵심 자료 계약은 [데이터 사전](DATA_DICTIONARY.md)에 정의한 observations, forecasts, supplier contracts, demand beliefs, orders, receipts, inventory ledger, scenario paths, experiment manifests입니다. 정책에 전달되는 context에는 미래 실제 값 컬럼이 없어야 합니다.

## 권장안과 대안

| 쟁점 | 권장안과 이유 | 대안 / 검토 조건 |
|---|---|---|
| 첫 원재료 | Wheat 한 계열로 단위·평가·재고 흐름 검증 | Soybean Oil은 독립 확장; 처음부터 다품목이면 오류 분리 어려움 |
| 계약 가격 | 납품월 지수 연동. 미래 지수 예측이 정산 위험과 직접 연결 | 발주 시 고정 견적은 알려진 견적만 입력; 미래 견적은 별도 예측 필요 |
| 정보 지연 | 월말 t에 t-1까지 허용하는 보수적 1개월 가정 | 실제 발표 이력 확보 시 정확한 timestamp; 무지연은 주 분석에서 제외 |
| 예측 길이 | 다음 3개 납품월, 매월 재계획 | 1개월은 2개월 lead 공급업체를 충분히 평가 못함; 6개월은 민감도 |
| 모델 복잡도 | Seasonal Naive부터 end-to-end | 고급 모델 추가는 validation과 운영 지표로 정당화 |
| 최적화 도구 | 연속 물량 LP 및 CVaR, OR-Tools GLOP 우선 검토 | 최소 lot/정수 발주 도입 시 MIP/CP-SAT와 단위 정수화 검토 |
| 날씨 | 기본 비활성화 | 지역·생육시기·공표시점 근거와 validation 개선이 있을 때 ablation |
| 수요 부족 | lost sales: 해당 월 미충족 수요에 일회성 패널티 | backlog는 별도 모델이며 반복 패널티·상태 전이를 재설계해야 함 |

## 미결정 사항과 변경 절차

Day 1 갱신: 대표 계열은 `Wheat, US HRW`로 선택했습니다. nominal USD/metric tonne, 1960-01~2026-09의 801개 유효값을 확인했습니다. SRW는 별도 보존합니다. HRW의 2020년 등급 정의 변경과 최신 수정본 한계는 [출처 기록](WORLD_BANK_SOURCE.md)을 따릅니다. 아래 Day 1 TODO 중 계열·단위·기간·결측·공식 URL 확인은 완료됐으며 과거 개별 공표 timestamp/vintage는 미확보입니다. Day 0 설정 파일은 당시 스냅샷으로 보존하고 실제 선택은 `configs/day1.toml`에 고정합니다.

- TODO Day 1: 원천 계열명·단위·기간·결측·이용약관·다운로드 URL·공표 이력 및 vintage 가용성 확인.
- TODO Day 2: 데이터 감사 후 시작일과 split 날짜를 고정. 충분한 월수가 없으면 holdout을 몰래 축소하지 말고 범위 변경 기록.
- TODO Day 5~6: 구간 보정법, 경로 생성법, 서비스 목표·위험 가중치를 validation에서만 선택.
- TODO Day 10: 개발용 seed와 분리된 최종 seed bank, 코드/설정 버전, holdout 진입 허가를 고정.
- 비용·공급 수치는 현실 추정값이 아닌 제안된 합성 가정입니다. 외부 데이터로 보정하지 못하면 가상 조건임을 유지합니다.

모든 변경은 변경 이유·영향받는 평가·승인된 Day를 기록합니다. 최종 holdout을 본 뒤 바꾼 사양은 기존 실험과 구분합니다.

Day 2 TODO 완료: 전체 801개월의 기본 무결성, 개발 구간 급변동 7개월 보존, 정의 변경 메타데이터를 확인했습니다. 전체 기간 유지+경계 메타데이터 관리를 기본으로 채택합니다. validation origin 2021-06~2024-05와 최종 holdout target 2024-10~2026-09를 고정했고, 기존 validation 종료일의 공표 지연 문제를 명시적으로 정정했습니다. [데이터 감사](DATA_AUDIT.md)와 [분할 설계](SPLIT_DESIGN.md)가 근거입니다. 실제 모델별 학습 시작은 Day 3 이후 lag 조건으로 추가 제한할 수 있으나 holdout 성과를 보고 조정하지 않습니다.
