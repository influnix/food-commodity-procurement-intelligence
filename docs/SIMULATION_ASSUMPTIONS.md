# 시뮬레이션 가정과 최적화 명세

이 문서의 수치는 **제안된 가상 입력**입니다. 공급업체·수요·비용 자료를 확보했다는 뜻이 아닙니다. Day 0에는 생성기나 solver를 구현하지 않았습니다. 확정된 것은 구조와 정보 규칙이며 수치의 적합성은 validation과 사전 정의한 민감도로 확인합니다.

Day 6 구현 범위: [사전 설계](DAY6_DESIGN.md), [실행 기록](DAY6_STATUS.md), `configs/day6.toml`이 실제 구현 사양입니다. 아래 Day 0 확률 지연·lognormal 수요·solver 제안은 보존하며 오늘 실행하지 않았습니다. 기본delay0/최대1의 외생 지정 지연과 명시적 Toy 수요를 사용합니다. 실제 Validation 구매 평가는 없습니다. 초기재고200/빈pipeline 기본안은 유지하되 정상 Toy 검산에는 명시적 미수령발주A80/B20을 추가 입력했습니다.

## 단위와 기준 운영조건

| 항목 | 제안값 / 생성 규칙 | 의미 |
|---|---|---|
| 시장 기준가격 | World Bank에서 확인할 실제 Wheat 계열 | 가격 자체를 합성하지 않음; 원단위 확인 전 실행 금지 |
| 단위 | metric tonne, USD/t, USD, 월 | 환율·세금·운임·품질 차이 제외 |
| 공급업체 A | premium 2%, 기본 lead 2개월, 발주용량 80 t/월 | 저가·느린 가상 업체 |
| 공급업체 B | premium 8%, 기본 lead 1개월, 발주용량 100 t/월 | 고가·빠른 가상 업체 |
| 지연 | A 확률 0.10, B 0.03로 1개월 추가; 아니면 0 | 발주월·업체별 외생 추첨; 개별 주문 단위와 혼동하지 않음 |
| 수요 계획 | 미래 매월 100 t | 당시 알려진 계획; 미래 actual과 분리 |
| 실제 수요 | `100 * exp(epsilon - sigma^2/2)`, `epsilon~N(0,sigma^2)`, sigma=0.10 | 기대값 100 t, 월별 독립을 기본 가정으로 둠 |
| 초기 재고 / pipeline | 200 t / 0 t | 모든 정책 동일; 과거 취득원가는 공통 sunk cost |
| 창고 용량 | 400 t | 월말 수요 출고 후 저장 용량; 월초 입고 staging 공간은 무제한 가정 |
| 보관비 | 월말 재고에 3 USD/t/월 | 매입비와 별도 |
| 부족 비용 | lost sales 1 t당 1,500 USD, 해당 월 1회 | backlog 없음; 실제 기업의 손실액 추정 아님 |
| 초과 재고 | 수요 충족 후 400 t 초과분 폐기, 1 USD/t 처리비 | 전량 매입비는 그대로 지불; 회수 수익 0 |
| 종료 조건 | 평가창 밖 납품 발주 금지, 미도착 주문 0, 잔여 재고 회수 수익 0 | 마지막 주문은 최대 지연 고려; `9*abs(I_T-200)` 종료비 추가 |
| 위험 | CVaR alpha=0.90, lambda=0.20 | validation 후보의 시작값; 최종 holdout에서 튜닝 금지 |

단가는 실제 납품월 지수에 premium을 곱합니다. 지연은 가격 확정월도 바꾸므로 가격 위험과 공급 위험이 연동됩니다. 발주월 지수 고정 계약을 가정한 결과와 직접 혼합할 수 없습니다.

### RNG와 경로 생성 계약

기본 seed는 20261024입니다. 향후 NumPy `SeedSequence` 등의 명시적인 stream 분리를 사용하고 RNG/패키지 버전을 기록합니다. 개발 seed는 설정 파일에, 최종 seed bank는 별도 잠금 manifest에 저장합니다.

외생 경로는 먼저 `(replication, supplier_id, order_month)`와 `(replication, demand_month)` 인덱스로 생성합니다. 정책에 주문이 없더라도 같은 인덱스는 보존합니다. 각 정책은 같은 실현 경로를 사용하고, planning scenario에는 다른 stream을 씁니다. 실험이 끝나기 전 미래 경로나 seed를 policy context에 전달하지 않습니다.

## 스트레스 시나리오 제안

발생 월은 운영창의 6~12번째 달 중 동일확률로 추첨하고 사전에 그 분포만 알려줍니다. 12개월 미만 창에서는 별도 규칙을 고정하기 전 실행하지 않습니다. 개발 단계에서 길이·분포·민감도 범위를 고정합니다.

| 시나리오 | synthetic 변경 | 공유/관측 규칙 |
|---|---|---|
| 기본 | 실제 기준 가격, 기본 수요·지연 | 가격은 원본 유지 |
| 가격 급등 | 3개월 동안 실제 기준가격에 1.30 배 | 파생 stressed series; 실제 시장 관측으로 표시하지 않음 |
| 납기 지연 | 3개월 발주 cohort에 A 지연확률 0.35, B 0.15 | 최대 추가 지연은 여전히 1개월; 발주월 기준 추첨 |
| 수요 증가 | 3개월 실제 수요를 1.20 배 | 기존 발행 forecast를 사후 수정하지 않음 |
| 복합 | 같은 onset에 위 세 충격 동시 적용 | 정책 간 동일 경로; 별도 완전정보를 주지 않음 |

충격은 공표/관측되어야 가격·수요 모델 입력에 반영됩니다. 납기 지연은 실제 미납 사실까지만 공개합니다. 계획 단계의 충격확률과 관측 후 갱신 규칙은 validation에서 고정하고 실제 onset을 미리 주지 않습니다. premium·용량·비용을 바꾼 민감도는 스트레스 경로와 별도 축으로 저장합니다.

## Rolling-horizon 최적화: 계획 명세

의사결정 월말 `t`, 계획기간 `U={t+1,...,t+H}`, `H=min(3, 남은 평가월수)`입니다. 예측은 다음 납품월을 대상으로 하며 매월 재계획해 **현재 월 `t`의 발주만 실행**합니다. 미래 계획을 확정 주문처럼 시뮬레이션하지 않습니다.

업체 `s`, 발주월 `k in K={t,...,t+H-1}`, planning scenario `omega` (확률 `pi_omega`, 합=1)를 둡니다.

입력:

- `I_t`: 현재 on-hand; `b_u^omega`: 기존 pipeline에서 예상되는 수령량. future actual 대신 조건부 planning distribution에서 계산합니다.
- `P_u^omega`: 납품월 가격 경로, `D_u^omega`: 수요, `L_s+delta_(s,k)^omega`: 리드타임.
- `C_s`: 업체 발주용량, `B=400`: 월말 저장용량, `a_s`: premium.
- `A_(s,k,u)^omega = 1[u=k+L_s+delta_(s,k)^omega]`: 발주가 월 u에 도착하는 지시값.
- 알려진 최대 지연을 고려해 계획창 끝 이후 도착할 수 있는 신규 주문은 계획에 넣지 않습니다. 전체 평가창 끝에서도 같은 제한을 적용합니다. H=3으로 잘리는 효과는 H=6 민감도로 점검합니다.

변수:

- `q_(s,k)>=0`: 업체별 계획 발주량. 모든 scenario에 **공유**하는 비예견적 물량입니다. 시나리오별 미래를 미리 아는 발주변수를 쓰지 않습니다.
- `I_u^omega>=0`, `z_u^omega>=0`, `w_u^omega>=0`: 월말 재고, lost sales, 폐기량.
- `eta`와 `xi_omega>=0`: CVaR 선형화 보조변수.

제약:

```math
0 \le q_{s,k} \le C_s
```

```math
I_u^\omega = I_{u-1}^\omega + b_u^\omega
 + \sum_{s,k} A_{s,k,u}^\omega q_{s,k}
 - D_u^\omega + z_u^\omega - w_u^\omega
```

```math
0 \le I_u^\omega \le B,\quad 0 \le z_u^\omega \le D_u^\omega,\quad w_u^\omega \ge 0
```

현 가정에서 부족 패널티 1,500은 추가 재고의 보관/종료 비용보다 충분히 크고 폐기에는 수익이 없어 LP가 불필요한 부족/폐기를 선택할 이점이 없습니다. 구현 시 엔진은 항상 가능한 수요부터 충족한 뒤 초과분만 폐기하며, solver의 월별 재고/부족이 그 물리 결과와 일치하는지 검증합니다. 비용계수를 크게 바꾸면 이 성질이 깨질 수 있으므로 서비스 우선 제약 또는 lexicographic 목적을 검토하고, 단순 LP 그대로 일반화하지 않습니다.

`V(I_end)=gamma*abs(I_end-I_target)`이며 기본 `gamma=9 USD/t`, `I_target=200 t`입니다. 절댓값은 양·음 편차의 비음수 변수로 선형화합니다. 계획창 말에는 장기 재고 가치의 단순 근사이고, 실제 평가창 말에 한 번만 최종 비용으로 부과합니다. 중간 재계획의 V를 월별 실현비용에 누적하지 않습니다.

시나리오 비용:

```math
C^\omega(q)=\sum_{u\in U}\left[
 \sum_{s,k} A_{s,k,u}^\omega P_u^\omega(1+a_s)q_{s,k}
 + h I_u^\omega + p z_u^\omega + d w_u^\omega\right]
 + V(I_{t+H}^\omega)
```

기존 pipeline 매입비는 현재 q에 대해 고정이지만 scenario별 가격위험을 CVaR에 반영해야 하므로 업체·주문별 기존 수령량에 해당하는 매입비도 `C^omega`에 더합니다. 실제 운영 ledger에서도 모든 수령분을 빠짐없이 한 번만 계상합니다.

Forecast-Aware는 단일 point scenario에서 `min C(q)`를 풉니다. Risk-Aware는 다음을 최소화합니다.

```math
\min_{q,\eta,\xi} \sum_\omega \pi_\omega C^\omega(q)
 + \lambda\left[\eta+\frac{1}{1-\alpha}\sum_\omega\pi_\omega\xi_\omega\right]
```

```math
\xi_\omega \ge C^\omega(q)-\eta,\quad \xi_\omega\ge0
```

비용 단위는 USD로 통일하며 lambda는 무차원입니다. CVaR는 **총비용**의 상위 tail입니다. 안전재고는 재고 경로와 부족 비용/위험 목적에서 내생적으로 생깁니다. 별도 service-level 안전재고 제약은 MVP 기본에서 넣지 않고 필요시 validation에서 정책 변형으로 정의합니다.

모든 미래 q를 scenario 간 공유하는 것은 단순한 open-loop lookahead 근사입니다. 실제로는 매월 새 정보로 재계획하므로 완전한 다단계 stochastic program과 같지 않습니다. 향후 scenario tree를 도입하면 같은 정보 이력의 노드에 non-anticipativity 제약을 적용해야 합니다.

연속 t 단위 LP로 시작하므로 OR-Tools GLOP을 우선 검토합니다. Day 0에는 OR-Tools를 설치하지 않습니다. 발주 lot·정수 트럭·고정비가 필요해지면 MIP로 확장하며 이번 LP 결과를 실제 계약 최적화라고 부르지 않습니다.

## 구현 시 검증과 민감도

- 재고 보존, 납품월, 단가 단위, 비용 합계, 초과폐기, lost sales의 단일 계상을 작은 수계산 toy fixture로 검증합니다.
- solver 최적/실행가능/시간초과/infeasible 상태를 분리하고 허용된 fallback을 기록합니다.
- 리드타임·용량·premium·보관비·부족 패널티·수요 오차·가격 충격·초기 재고·종료 비용을 바꿉니다. 부족이 너무 싸서 고의 부족을 선택하는 경우 물리/서비스 가정부터 재검토합니다.
- horizon 3/6개월, 종료 목표·비용, 평가창 길이와 초기 상태 민감도로 경계효과를 확인합니다.
- 최적화의 예상 재고와 평가 엔진의 실현 재고 차이는 예측오차/지연 때문인지 구현 오류인지 분리합니다.
