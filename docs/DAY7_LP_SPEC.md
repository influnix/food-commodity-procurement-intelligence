# Day 7 사전 LP 명세

2026-10-29 Asia/Seoul. Solver 구현과 정책 비용 비교 전에 이 수식과 `configs/day7.toml`을 고정했습니다. Day 6의 계약·엔진·Fixed와 비용 계수를 변경하지 않습니다. Day 7 신규 모듈만 추가하며 OR-Tools9.14.6206 GLOP을 사용합니다.

## 시점과 입력

월말t에 입고·수요·폐기를 처리한 현재재고I_t를 받습니다. 계획 납품월은 `M={t+1,...,e}`, `e=min(t+3,T)`입니다. 계획 발주월은 `K={t,...,e−1}`이고 실제로는 q_(s,t)만 실행합니다. 미래 계획은 다음 월에 다시 풀며 확정 pipeline으로 이월하지 않습니다.

입력은 공개 DecisionContext, 현재 origin의 점예측, 미래 계획수요, 기존 가상 비용/계약뿐입니다. t−1을 넘는 실제가격·미래수요·실제delay·evaluation scenario는 없습니다. Nominal lead는 `L_s+nominal_delay_s`이며 신규 주문 허용은 별도로 `k+L_s+maximum_delay_s<=e`를 요구합니다. 이는 Day 0의 계획창 말기 허용 규칙을 유지한 보수적 선택입니다. 글로벌종료T도 넘지 않습니다.

기존 pipeline은 취소/재최적화하지 않습니다. 예상입고는 `max(promised+nominal_delay,t+1)`로 두며 overdue 주문은 다음 달로 예상합니다. 실제 미래 도착월을 읽지 않습니다. 계획창 밖 기존 pipeline은 deferred 목록에 남기고 이번 목적함수에서는 제외하며 이후 fold/실제 ledger에서 처리합니다. 글로벌T 밖 도착 가능한 pipeline은 거부합니다. 같은 업체·발주월의 이미 확정된 수량은 신규 capacity에서 차감합니다.

## 상수와 변수

`B_(s,m)`은 기존 supplier별 예상입고, `P_m`은 현재 발행된 납품월 점예측, `D_m`은 수요계획, `C_s`는 발주capacity, `V=400`은 저장capacity입니다. premium a_s, 운송단가 v_s, h=3, p=1500, d=1, gamma=9, 종료목표I*=200은 기존 가상 가정입니다.

연속 비음수 변수: 신규발주q_(s,k), 입고R_m, 월말재고I_m, 미충족U_m, 폐기W_m, 말기편차z+/z−. MOQ와multiple이0인 계약만 지원하며 다른 값이면 LP를 조용히 MIP처럼 취급하지 않고 거부합니다.

```math
0\le q_{s,k}\le C_s-\text{committed}_{s,k}
```

허용성 검사를 통과하지 않는 q는 상한0입니다.

```math
R_m=\sum_s B_{s,m}+\sum_{s,k:k+L_s+nominalDelay_s=m}q_{s,k}
```

```math
I_m=I_{m-1}+R_m-D_m+U_m-W_m,\quad 0\le I_m\le V,\quad 0\le U_m\le D_m
```

Day 7의 보수적 기본사양은 `W_m=0`입니다. 기존 엔진은 정상재고를 임의 폐기하지 않으며 용량 초과만 처리합니다. 자유 W를 비용1로 최소화하면 보관/종료비를 피하려고 정상재고를 버릴 수 있어 엔진과 충돌합니다. 그 동작을 추가하지 않고 계획 폐기를 금지합니다. 강제 초과 pipeline은 이 제한된 LP에서 INFEASIBLE일 수 있으며 실제 엔진 자체가 불가능하다는 의미는 아닙니다. 실제 충격의 초과폐기는 기존 엔진 규칙을 그대로 따릅니다. 해의 U/I/W를 greedy 서비스·overflow 회계로 재검산해 불일치하면 실행하지 않습니다.

```math
I_e-I^*=z^+-z^-,\quad z^+,z^-\ge0
```

목적함수의 신규 발주 변동비는 납품월에 의해 결정됩니다.

```math
\min \sum_{s,k} [P_{k+L_s+nominalDelay_s}(1+a_s)+v_s]q_{s,k}
+\underbrace{\sum_{s,m}[P_m(1+a_s)+v_s]B_{s,m}}_{\text{변경 불가 pipeline 상수}}
+\sum_m(hI_m+pU_m+dW_m)+\gamma(z^++z^-)
```

비용은USD, 수량은metric tonne, 단가는USD/t입니다. 상수와 신규변동비를 분리해 기록합니다. 3개월 계획창의말기비는 장기재고 가치의 근사로 매월 **계획 목적함수에만** 포함합니다. 실제 ledger는 전체 최종월에만 기존9×|I_T−200|을 한 번 부과합니다. 발주는 가격을 고정하지 않습니다. 미래 예상 납품월·업체·재고 보유를 조정할 뿐입니다.

## Solver·수치·실패

GLOP의 OPTIMAL/FEASIBLE/INFEASIBLE/UNBOUNDED/ABNORMAL/MODEL_INVALID/NOT_SOLVED와 미지 상태를 구분합니다. 기본 비교는 OPTIMAL이며 수치·물리 검사를 통과한 해만 실행합니다. FEASIBLE을 최적이라고 부르거나 Fixed로 대체하지 않습니다. 실패 시 비교를 중단하고 상태·원인을 남깁니다.

GLOP primal/dual tolerance1e−8, 수량 검증1e−7t, 목적함수 abs1e−4USD/rel1e−8, 제한10초, 고정random_seed와dual simplex를 사용합니다. GLOP의 SetNumThreads(1)은False를 반환했으므로 지원된 설정이라고 주장하지 않으며 기본 직렬GLOP을 사용합니다. raw변수와 현재실행수량을 별도 저장하고 경계의1e−7 이내 수치오차만0/capacity로 정규화합니다. 그 밖의 위반은 실패입니다.

## 실행 전 손계산 기준

각 검산은 declared maximum delay0, terminal weight0을 기본으로 단순화한 명시적 Toy LP이며 정책 비교의 계약을 바꾸지 않습니다.

| Case | 조건 | 최적 신규 발주 | 목적함수 USD |
|---|---|---|---:|
| A 단일 | 수요10, 재고2, lead1, 가격10 | 8t | 80 |
| B lead | 2개월수요각10, A lead2/0%, B lead1/20%, 가격10 | 현재A10/B10 | 220 |
| C capacity | 수요10, A cap4/0%, B cap10/20%, lead1/가격10 | A4/B6 | 112 |
| D 보관·가격 | 2개월수요각10, lead1 cap20, 가격10→20, 보관1 | 현재20, 미래0 | 210 |
| E 부족 | 수요10, cap4, 가격10, 부족패널티1000 | 4t, 부족6t | 6040 |

## 비교·실제 Forecast smoke 범위

Day 6의기존5개 인공 world를 그대로 쓰되 **두 정책 모두 초기재고200t·빈pipeline**으로 비교합니다. 기간·실제가격/수요/delay·비용·공급조건은 동일합니다. Day 6 손계산용opening pipeline은 회귀 테스트에서만 유지합니다. Toy 정책가격은 사전고정한 모든h의100USD/t belief이며 미래실제world에서 가져오지 않습니다. 충격을 보고 belief/기간/사양을 바꾸지 않습니다.

실제 SARIMAX와LightGBM은 Day 4 저장 point를 origin별로 읽는 adapter로2021-06/2024-05의4개 계획만 smoke 검사합니다. 현재재고200·빈pipeline은 명시적 가상 상태이며 실제 기업 상태가 아닙니다. 실제 target/구매 ledger를 읽거나 성과를 평가하지 않습니다. Holdout은 거부합니다.

API 근거: [Google LP 예제](https://developers.google.com/optimization/lp/lp_example), 설치된9.14.6206의pywraplp 소스와VerifySolution docstring, [PyPI 버전 메타데이터](https://pypi.org/project/ortools/9.14.6206/). 설치·호환성 기록과 실제 실행 결과는 별도 Day 7 상태 문서에 남깁니다.
