# 구매 의사결정 최적화와 재고 회계

조달에서는 단가가 낮아도 필요한 달에 도착하지 않으면 쓸 수 없습니다. 업체 A와 B를 나누고 주문한 달과 입고되는 달을 분리한 이유입니다. LP는 세 달 동안 감당할 수 있는 주문 계획을 계산하고, 엔진은 그중 지금 주문할 물량만 확정해 장부를 이어갑니다.

## 정책과 공개 입력

Fixed는 입고 허용 조건 아래 A/B에 80/20t를 발주하는 비교 기준입니다. 같은 주문 문제에 SARIMAX와 LightGBM의 예측을 각각 넣어 FA/RN/RA를 만들면 총 7개 정책이 됩니다. FA는 점예측 결정론적 LP, RN은 시나리오 평균비용(λ0), RA는 평균비용과 고비용 꼬리 평균인 CVaR의 혼합(λ.50, α.90)을 사용합니다. RN/RA에 모델별로 같은 128개 Planning 경로를 주므로, 같은 재고·주문 상태에서는 목적함수에 따른 차이를 볼 수 있습니다. FA와 RA 사이에서는 가격 입력과 목적함수가 함께 바뀝니다.

공개 context에는 현재 재고·예정/overdue pipeline·공급 계약·수요계획·공표 이력·현재 origin 예측이 있습니다. 평가 엔진만 실제 미래 가격·수요·지연을 소유합니다. Overdue 입고는 미래 실제 지연을 읽지 않고 다음 달로 계획합니다.

## 고정 운영 가정

비교 초기재고 I200t·빈 pipeline, 수요계획 100t/월, 창고 400t입니다. A는 premium 2%·lead 2·월 capacity 80t, B는 8%·lead 1·100t입니다. 명목 지연 0, 최대 추가 지연 1, MOQ/multiple/운송비 0입니다. 보관 3·lost sales 1500·폐기 1·말기편차 9 USD/t, 목표재고 200t, 잔존가치 0입니다. 초기재고 취득비는 매몰비용입니다. 별도 Fixed 손계산 fixture의 초기 A80/B20 pipeline은 비교의 기본값이 아닙니다.

## 결정론적 계획 LP

origin t에서 납품월 m=t+1..e, e=min(t+3,T), 발주월 k=t..e−1을 계획합니다. 비음수 변수는 q(s,k), 입고 R, 월말재고 I, 부족 U, 폐기 W, 말기편차 z+/z−입니다. 이번 달 q(s,t)만 확정 pipeline에 넣습니다. 나머지 주문은 이번 결정이 다음 달의 선택에 어떤 제약을 남기는지 계산하기 위한 변수입니다.

```math
0\le q_{s,k}\le C_s-committed_{s,k},\quad
k+L_s+maximumDelay_s\le e\quad\text{or }q_{s,k}=0,
```

```math
R_m=\sum_s B_{s,m}+\sum_{s,k:k+L_s+nominalDelay_s=m}q_{s,k},
\quad I_m=I_{m-1}+R_m-D_m+U_m-W_m,
```

```math
0\le I_m\le V,\quad0\le U_m\le D_m,\quad W_m=0,
\quad I_e-I^*=z^+-z^-.
```

신규 주문과 확정된 기존 pipeline에는 수령월 예측가격에 공급업체 할증을 적용한 비용을 붙입니다. 목적함수에는 운송·보관·부족·폐기·계획 말기편차도 들어갑니다. 계약 가정상 가격 기준월은 주문월이 아니라 수령월입니다. 계획창 밖에 도착할 주문은 deferred로 남기고 전체 종료 T 뒤에 도착하는 pipeline은 거부합니다.

W=0은 보수적인 제한입니다. 자유롭게 저렴한 폐기를 허용하면 엔진의 greedy 수요 충족·초과재고만 폐기하는 동작과 충돌할 수 있습니다. 강제 pipeline overflow는 실제 엔진이 처리할 수 있어도 제한 LP를 infeasible로 만들 수 있습니다. 이를 정책 fallback으로 숨기지 않습니다.

## 시나리오 목적함수와 CVaR

어떤 가격 경로가 실현될지 주문할 때는 알 수 없습니다. 그래서 현재·미래의 q와 입고, 재고, 부족·폐기, 말기 변수는 모든 경로에 같은 값을 적용합니다. 경로마다 다른 주문을 허용하면 실현 가격을 알고 계획한 셈이 됩니다. 달라지는 것은 동일 계획의 비용 Cω이며, 여기에는 기존 pipeline의 가격 상수도 포함됩니다.

```math
\min (1-\lambda)\sum_\omega p_\omega C_\omega+
\lambda\left(\eta+\frac{1}{1-\alpha}\sum_\omega p_\omega\xi_\omega\right),
\quad \xi_\omega\ge C_\omega-\eta,\quad\xi_\omega\ge0.
```

이산 CVaR는 경계 원자의 일부 질량까지 포함해 상위 1−α 질량을 적분합니다. 128경로에서 큰 값 13개의 단순평균이 아닙니다. λ0에서는 η/ξ가 목적함수로 식별되지 않으므로 raw epigraph와 독립 계산한 VaR/CVaR를 구분합니다. RN은 같은 시나리오의 평균가격 LP와 일치하며 원래 점예측 LP와 반드시 같지는 않습니다.

GLOP9.14.6206의 기존 seed, dual simplex, 10초 제한, primal/dual 1e−8, 수량 1e−7t, 목적 abs1e−4USD/rel1e−8를 유지합니다. OPTIMAL에 더해 VerifySolution·공유 변수·물리/greedy 회계·시나리오 비용·기대비용/CVaR/목적 재구성을 통과해야 실행합니다. FEASIBLE은 최적이 아닙니다. 실행 수량의 작은 정규화는 선언된 허용오차 안에서만 적용하며 그 밖의 실패는 숨은 fallback 없이 비교를 중단합니다.

## 엔진과 종료 회계

월별 순서는 입고→실현 수요 출고→초과재고 폐기→비용 귀속→공개 상태로 결정→발주입니다. 실제 입고월은 발주월+lead+평가 엔진 전용 delay입니다. Fulfilled=min(beginning+receipts,demand), 부족은 당월 한 번만 계상하는 lost sales이며 다음 달 backlog가 아닙니다. Ending=beginning+receipts−fulfilled−disposed입니다.

장부의 매입비는 입고된 달에 그달의 실현 지수에 할증을 적용해 한 번 계상합니다. 보관비는 월말재고, 부족·폐기비는 실현 수량을 사용합니다. 매달 푸는 LP의 말기편차 비용은 계획을 위한 항목입니다. 실제 원장에는 전체 마지막 월의 9×abs(ending−200)만 들어갑니다.

Validation은 36개 결정/38개월 원장, Active35/Runoff3입니다. 잠긴 최종 달력은 22/24, Active21/Runoff3입니다. Runoff에는 provider/정책 호출과 신규 q가 없고 마지막 origin 이후 미래 계획 q도 금지합니다. 종료 pipeline은 비어야 합니다. 동일 외생 조건 아래 정책 상태는 독립적이며, 실패는 시점·원인·확인 가능한 prefix를 남기고 없는 부분 원장을 만들거나 완전 성과처럼 순위화하지 않습니다.
