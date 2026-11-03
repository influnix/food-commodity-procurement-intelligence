# Day 9 사전 평가 프로토콜

2026-10-30 Asia/Seoul. 실제 구매 성과 계산 전에 `configs/day9.toml`과 본 문서를 고정합니다. 명칭은 **Historical Price-Based Simulated Procurement Backtest**입니다. 실제 자료는 World Bank Wheat US HRW 가격뿐이며 업체·수요·납기·비용·재고는 가상입니다. 기존 Day0~8 데이터·설정·예측·코드·성과·Holdout 잠금을 보존합니다.

## 달력과 최초 결정

2021-06 월말 재고200t·빈pipeline에서 시작하고 같은 달에 첫 주문을 결정합니다. 2021-06~2024-05의36개 origin에서만 정책을 호출합니다. 2021-07~2024-08의38개월 가격/수요/입고/비용 ledger를 생성합니다. Active ledger는2021-07~2024-05의35개월, Runoff는2024-06~08의3개월입니다. 최초 결정월2021-06은 사전 상태 시점이며 수요/보관/정산 ledger에 추가하지 않습니다. Active decision36개월과 active operating35개월을 구분합니다.

월말 결정 t는 t−1까지의 가격 및 available_at≤d_t인 자료만 받습니다. 마지막 origin2024-05의 H1/2/3은2024-06/07/08입니다. 이후 예측을 생성하거나 기존 scenario를 장기 실현가격으로 이어 붙이지 않습니다. Runoff는 현재 고정된 forecast 달력의 실험적 정산 규칙이며 기업 관행의 주장이 아닙니다.

## 기존 엔진과의 충돌 및 고정한 해법

Day6 엔진은 매월 운영을 처리한 뒤 정책을 호출하고 ToyWorld는 synthetic-only입니다. 실제 가격을 ToyWorld로 위장하거나 기존 엔진을 수정하지 않습니다. 별도의 HistoricalEvaluationWorld를 사용하되 기존 엔진의 런타임 구조 계약(기간·가격·수요·delay·knowledge_type)을 재사용합니다. 최초6월 주문은 운영 시작7월보다 먼저 수동으로 동일 정책 경계를 호출해 확정하고, 엔진에는 그 **첫 결정 직후 pipeline**으로 전달합니다. 이는 초기 상태의 외생 pipeline이 아니며 첫 결정 전 빈pipeline과 구분해 기록합니다. 엔진의 opening flag를 새 결과에서 최초 결정 주문으로 재분류하고 원래 엔진 flag도 남깁니다. 38개월 운영·납품 회계는 기존 run_simulation을 그대로 사용합니다.

또한 Day7/8 LP는 명목상 t..e−1의 미래 주문을 허용하므로 마지막 결정 뒤 Runoff 주문을 계획할 수 있습니다. 대안으로 이를 그대로 두면 실행하지 않을 주문에 의존한 말기 계획이 생깁니다. 기본안은 **Day9 solver adapter가 모든 k>2024-05 신규 q의 상한을0으로 추가**하는 것입니다. 기존 수식·계획창·목적·가격 입력·검산은 유지하고, 고정된 운영 달력의 발주 금지 제약만 추가합니다. 원본 LP/solver 코드는 변경하지 않습니다. 이 제약은 실제 성과를 보기 전에 모든 최적화 정책에 동일하게 적용합니다. 실제 Fixed 역시 Runoff에 호출하지 않습니다.

계획창은 e=min(t+3,T)이며 공급업체 최대 추가 지연까지 e 안 도착하는 신규 주문만 허용하는 기존 보수적 조건을 유지합니다. 단축창은 합성 경계 테스트에서 검사하고 실제36개 origin에는 모두 기존3h 예측을 사용합니다. 마지막 주문 최대 도착은 T=2024-08 이내여야 하며 종료pipeline은0입니다. 계획말기 비용을 월별 실현원장에 누적하지 않고 γ|I_T−200|을 마지막8월에 한 번만 청구합니다.

## 외생 환경·정책 사양

모든 정책에 같은 초기200t·빈pipeline·창고400t, 기존A/B 계약을 사용합니다. A premium2%/lead2/cap80, B8%/lead1/cap100t, 기본delay0·최대delay1입니다. 실제 수요100t/월, 실현 추가delay0이며 RNG·seed bank·추가 stress는 이번 primary에서 사용하지 않습니다. 보관3·부족1500·폐기1·말기편차9USD/t, lost sales, 잔여재고 회수수익0입니다. 초기재고 취득비는 공통 sunk cost입니다.

7정책은 Fixed, SARIMAX/LightGBM 각각 FA(point), RN(기존 Planning scenario λ0), RA(동일 scenario λ.5)입니다. α.90·기존 모델·calibration·scenario pool/방법/seed를 변경하지 않습니다. Scenario 공유는 immutable bundle과 record hash로 확인합니다. 서로 다른 정책의 재고/pipeline이 달라지는 것은 정상이며 외생 환경과 초기조건만 같아야 합니다.

## 가격 접근과 정보 경계

기존 개발 store의 validation-only evaluator capability를 Day9 GuardedValidationPrices로 감쌉니다. 날짜 하나당 단일-horizon ForecastSample을 만들어38개 고유 Validation 가격을 한 번씩 평가 경로로 취득합니다. Bridge/Holdout은 capability에 도달하기 전에 거부합니다. 평가용 clock은 선택 freeze2024-09이며 정책의 decision clock과 분리합니다. 사후 정산을 위해 알 수 있는 월t 가격을 현재 정책에 전달하지 않습니다.

평가 엔진만 HistoricalEvaluationWorld와 전체 실제가격 경로를 받습니다. 공개 context는 기존 DecisionContext이고, 별도 as-of history provider가 현재 origin의 공개 이력만 채웁니다. 정책은 evaluator·world·미래 실현수요/delay·현재 정산단가/비용을 받지 않습니다. Spy reader·미래 가격/수요/delay·Holdout 변경 테스트로 경계를 확인합니다. API 경계이며 OS 차원의 악의적 접근 방지는 아닙니다. 원본 무결성 검증은 기존 로더 내부에서 수행하고 정책에 bridge/holdout 값을 export하지 않습니다.

## 평가와 실패

매입/운송/보관/부족/폐기/실제종료비와 총비용, 수요·충족·부족·fill rate·stockout개월·평균재고, 업체별/월별 주문과pipeline, solver/status/시간을 저장합니다. Full/Active/Runoff를 별도 집계하고 paired 월별 비용·서비스·재고·발주 차이와 전체 차이를 저장합니다. 입고에 달린 origin/horizon은 신규 주문부터의 실제 수령 offset으로만 보조 집계하며 offset1/2/3+를 겹치지 않게 세고 비용 전체를 이 기준으로 억지 배분하지 않습니다.

주 비교는 FA−Fixed(예측+최적화 전체), 같은 모델의RA−RN(위험 목적 추가), 같은 정책의LightGBM−SARIMAX(모델 및 scenario 입력 변경), RA−FA입니다. FA point와 scenario mean 차이를 순수CVaR 효과라 부르지 않습니다. 최초 공통 상태에서 RN/RA를 같은 세트로 푼 진단도 저장하되 장기 총효과와 구분합니다.

Forecast/scenario 누락·불일치, as-of 실패, solver 비정상/비물리해, 수치·재고·pipeline 오류는 숨기거나 fallback하지 않습니다. 첫 실패origin·완료decision/ledger·부분결과·공통완료구간을 저장하고 incomplete에서는 완전기간 총성과/정책 순위를 생성하지 않습니다. 실패정책의 성공기간만 골라 전체성과처럼 비교하지 않습니다.

Toy end-to-end 검증을 먼저 통과해야 실제 실행을 허용합니다. 실제 실행은7정책×36결정과7×38ledger의 완전성을 검사한 후에만 paired 집계를 만듭니다. 기존 solver/엔진 회계의 독립 검산, 반복 바이트 재현, 보존 hash를 확인합니다. 정책·α/λ·달력·말기 사양은 성과를 보고 변경하지 않습니다.

## 해석과 후속 단계

SARIMAX는 이미 같은 Validation에서 상대적으로 좋은 점예측 모델로 선택되었습니다. 이번 결과는 개발·선택 기간의 탐색적 운영평가이며 독립 OOS가 아닙니다. 단일 역사적 가격 경로이고 월별 비용/재고가 의존하므로38개월을 독립 표본으로 취급하거나 유의확률·신뢰구간·시장 실현CVaR를 산출하지 않습니다. Planning CVaR 합계도 실현CVaR가 아닙니다. Day5 coverage미달, 검증되지 않은 bootstrap 발생확률·tail, 사후 수정 snapshot·가정공표시각·2020-07 정의변경 한계를 유지합니다.

Day10은 별도 지시 후 초기/말기재고·비용·horizon·계약/lead/capacity·수요/delay·공표지연의 민감도 grid와 공통 평가경로/seed bank를 사전 고정해야 합니다. 추가 horizon/지연의 예측이 없으면 새 forecast 없이 지원된다고 주장하지 않습니다. Holdout은 계속 잠금이며 이번 단계에서 실행하지 않습니다.
