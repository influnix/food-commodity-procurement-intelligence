# Day 8 사전 CVaR·비예견성 명세

2026-10-30 Asia/Seoul. 구현·손계산 실행·정책 비교 전에 이 명세와 `configs/day8.toml`을 고정합니다. α=0.90, λ=0.50이며 λ=0/1은 경계 검증용입니다. 성과를 보고 조정하지 않습니다. Day 0~7 코드·설정·데이터·결과, 분할과 Holdout 잠금을 보존하며 새 패키지를 설치하지 않습니다.

## 공유 물리 모델

Day 7 `build_problem`의 공개 context·수령월·capacity·lead·cohort 잔여량·계획창 허용성과 `inspect_solution`의 재고/greedy 검사를 재사용합니다. 월말 t의 실제가격은 t−1까지이며 미래 계획은 t+1..e, e=min(t+3,T)입니다. 모든 신규 발주 q(s,k), k=t..e−1, 입고 R, 재고 I, 부족 U, 폐기 W와 말기편차 z는 **전체 시나리오가 하나의 변수를 공유**합니다. 시나리오별 주문·재고 recourse가 없습니다. 시나리오는 가격·비용만 다르고 수요·명목납기·현재 재고·pipeline은 같습니다. 미래 가격을 즉시 관측하는 분기를 만들지 않습니다.

제약은 Day 7과 같습니다: 0≤q≤capacity−committed, 최대 delay까지 e 안에 도착하는 신규주문만 허용, R=기존pipeline+명목납기 신규입고, I=이전I+R−계획수요+U−W, 0≤I≤창고상한, 0≤U≤수요, W=0, I_e−목표=z+−z−. 모든 수량은 t입니다. 자유 폐기를 추가하지 않으며 강제 overflow는 제한 LP의 infeasible로 보고합니다. 별도 greedy/overflow 검산에 실패한 OPTIMAL도 실행하지 않습니다. 기존 pipeline의 계획창 밖 비용은 Day 7처럼 deferred이며 글로벌 종료 뒤 입고는 거부합니다.

현재 q(s,t)만 실행하고 미래 q는 다음 달 재최적화합니다. 정책은 공개 DecisionContext와 현재 origin의 `ScenarioSet.for_policy`만 받습니다. Evaluation set·다른 origin·Holdout을 거부합니다. 원본 세트는 H1/H2/H3 공동 경로 128개이며 가격은 nominal USD/metric tonne입니다. 확률은 경로당 한 번만 합산하며 세 horizon 행의 반복 기재를 합산하지 않습니다.

## 비용과 위험 목적함수

각 ω에서 신규 매입은 Σq(s,k)Pω(arrival(s,k))(1+premium_s), 기존 pipeline 매입은 ΣB(s,m)Pω(m)(1+premium_s)입니다. 기존 pipeline 상수도 시나리오마다 다릅니다. 운송비(신규+pipeline), 보관 hΣI, 부족 pΣU, 폐기 dΣW, 계획말기 γ(z++z−)를 더한 총 계획비용을 Cω로 둡니다. 가격에 확률을 곱하는 시점은 기대비용 계산 한 번뿐입니다. 납품월 지수 연동이며 선발주가 가격을 고정하지 않습니다. 계획말기 비용은 각 계획창 목적함수의 근사이며 실제 ledger는 전체 최종월에만 종료비를 청구합니다.

```math
\min (1-\lambda)\sum_\omega p_\omega C_\omega
+\lambda\left[\eta+\frac{1}{1-\alpha}\sum_\omega p_\omega\xi_\omega\right],
\qquad \xi_\omega\ge C_\omega-\eta,\quad\xi_\omega\ge0.
```

η는 자유 실수, ξ는 비음수 USD입니다. 이 목적함수와 모든 제약은 선형입니다. [Rockafellar–Uryasev 원 논문 목록](https://uryasev.github.io/publications/)과 [일반 이산 손실분포 논문](https://www.sciencedirect.com/science/article/pii/S0378426602002716)을 근거로 합니다. 원자 질량을 갖는 분포에서 단순히 `C≥VaR`인 표본 전체의 평균을 쓰지 않고, 상위 1−α 질량의 경계 원자를 필요한 만큼만 포함해 CVaR를 독립 계산합니다. VaR는 누적질량이 α 이상인 최소 비용이며 η 최적해가 비유일하면 η=이 VaR를 강제하지 않습니다.

λ=0에서는 η/ξ가 목적함수에서 사라져 solver 값이 CVaR 최소 표현일 필요가 없습니다. 원시 η/ξ·epigraph 유효성을 남기고, 반환하는 VaR/CVaR는 비용 분포의 독립 산술값입니다. λ>0은 solver η+가중 ξ 표현과 독립 CVaR가 일치해야 실행합니다. λ=0도 기대비용·전체 목적함수·물리 제약 검산은 면제하지 않습니다. λ=0 결과는 같은 가중평균 가격을 넣은 Day 7 LP와 비교하며 원래 point와 같다고 가정하지 않습니다.

## 검증·수치·사전 Toy

기존 GLOP9.14.6206, primal/dual 1e−8, 수량1e−7t, 비용 abs1e−4USD/rel1e−8, 10초·기존seed를 재사용합니다. OPTIMAL+VerifySolution+공유 변수 구조+물리 회계+시나리오별 비용+기대비용+CVaR+혼합 목적함수가 모두 일치해야 실행합니다. FEASIBLE/실패·비물리해는 명시적으로 중단하고 fallback하지 않습니다. raw 수치와 실행 수치 정규화를 구분합니다.

손계산은 별도의 작은 synthetic 설정으로 α=.9, λ=.5입니다.

| 사례 | 사전 계산 |
|---|---|
| A 동일 가격 | Day7 A: q8, 모든 비용80, E=VaR=CVaR=목적80 |
| B 하나의 tail | 수요10, 가격10(.9)/100(.1), q10, 비용100/1000, E190, VaR100, CVaR1000, 목적595 |
| C 공급·시간 trade-off | 2개월 각수요10, A lead2/0% cap10, B lead1/20% cap20, 보관1. P1=10, P2=10(.9)/30(.1). 기본은 현재B20/A0, 비용250 고정. λ0은 B10/A10, 비용220/420, E240, CVaR420 |
| D lead/capacity | Day7 B 동일 경로, 현재A10/B10, 모든 비용220 |
| E 공급 부족 | cap4/수요10, 가격10/20(.5씩), 부족6×1000, 비용6040/6080, E6060, VaR/CVaR6080, 목적6070 |
| F 비예견성 | C와 같은 허용 해의 최적값250. 불법 시나리오별 현재주문은 정상A10/B10(220), tail A0/B20(250), E223/CVaR250/목적236.5로 낮아지므로 반드시 차단 |

비교 Toy는 Day 7과 같은 초기200·빈pipeline·world A~E·계약·회계입니다. Forecast-Aware belief는 기존100, Risk-Aware는 별도 고정 generator의96×(100,100,100),24×(90,120,140),8×(100,200,300)을128개 동등 가중치로 만들고 명시적 seed로 순열만 바꿉니다. world나 Validation을 읽지 않고 모든 origin의 planning을 비교 실행 전에 저장합니다. 불확실성·평균가격의 차이가 섞이므로 RA 대 FA 차이를 전부 CVaR 효과라 부르지 않습니다. 같은 RA 세트에 FA 발주 계획을 고정해 E/CVaR를 계산하는 진단은 별도로 표시합니다. 월별 계획비용을 합해 장기 실현 CVaR라고 부르지 않습니다.

실제 저장 Day 6 SARIMAX/LightGBM의2021-06/2024-05는 가상재고200·빈pipeline의4개 계획 smoke만 풉니다. 정답·실제 구매 ledger를 읽지 않고 origin 간 경로를 장기 시계열로 이어 붙이지 않습니다. 세트 hash·공동 OOF 성숙 증거·clock·seed·단위·확률을 검증합니다.

현재 위험은 경험적 가격 비용의 tail이며 수요/납기 확률분포는 추정하지 않았습니다. Day 5의80% coverage 미달, OOF 의존성, 사후 수정 snapshot, planning/evaluation seed 분리의 비독립성을 유지합니다. 실제 미래 비용·서비스를 보장하지 않으며 full adaptive stochastic program도 아닙니다. Day 9 실제 Validation 구매평가는 별도 지시 후 설계합니다.
