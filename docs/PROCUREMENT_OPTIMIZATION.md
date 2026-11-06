# 구매 의사결정 최적화와 재고 회계

## 정책과 공개 입력

7개 고정 정책은 Fixed, SARIMAX FA/RN/RA, LightGBM FA/RN/RA입니다. Fixed는 입고 허용 조건 아래 A/B에 80/20t를 발주합니다. FA는 점예측 결정론적 LP, RN은 시나리오 평균비용(λ0), RA는 CVaR 혼합(λ.50,α.90)을 사용합니다. RN/RA는 모델별 같은 128개 Planning 경로를 공유합니다. FA→RA 차이에는 예측 분포와 위험 목적의 변화가 함께 있고, 같은 입력의 RA→RN 비교는 위험 목적의 차이를 구분합니다.

공개 context에는 현재 재고·예정/overdue pipeline·공급 계약·수요계획·공표 이력·현재 origin 예측이 있습니다. 평가 엔진만 실제 미래 가격·수요·지연을 소유합니다. Overdue 입고는 미래 실제 지연을 읽지 않고 다음 달로 계획합니다.

## 고정 운영 가정

비교 초기재고 I200t·빈 pipeline, 수요계획 100t/월, 창고 400t입니다. A는 premium 2%·lead 2·월 capacity 80t, B는 8%·lead 1·100t입니다. 명목 지연 0, 최대 추가 지연 1, MOQ/multiple/운송비 0입니다. 보관 3·lost sales 1500·폐기 1·말기편차 9 USD/t, 목표재고 200t, 잔존가치 0입니다. 초기재고 취득비는 매몰비용입니다. 별도 Fixed 손계산 fixture의 초기 A80/B20 pipeline은 비교의 기본값이 아닙니다.

## 결정론적 계획 LP

origin t에서 납품월 m=t+1..e, e=min(t+3,T), 발주월 k=t..e−1을 계획합니다. 비음수 변수는 q(s,k), 입고 R, 월말재고 I, 부족 U, 폐기 W, 말기편차 z+/z−입니다. q(s,t)만 실행하고 나머지는 재최적화하며 확정 pipeline으로 넘기지 않습니다.

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

목적함수에는 신규 주문과 **확정된 기존 pipeline**의 수령월 예측가격×공급업체 premium, 운송·보관·부족·폐기·계획 말기편차를 포함합니다. 발주가 시장가격을 고정하는 것은 아닙니다. 계획창 밖 pipeline은 취소하지 않고 deferred로 남기며 전체 종료 T 뒤의 pipeline은 거부합니다.

W=0은 보수적인 제한입니다. 자유롭게 저렴한 폐기를 허용하면 엔진의 greedy 수요 충족·초과재고만 폐기하는 동작과 충돌할 수 있습니다. 강제 pipeline overflow는 실제 엔진이 처리할 수 있어도 제한 LP를 infeasible로 만들 수 있습니다. 이를 정책 fallback으로 숨기지 않습니다.

## 시나리오 목적함수와 CVaR

현재·미래의 q, 입고, 재고, 부족·폐기, 말기 변수는 **모든 가격 시나리오가 공유**합니다. 미래를 미리 아는 시나리오별 recourse는 없습니다. 시나리오별로 달라지는 Cω에는 기존 pipeline의 가격 상수도 포함됩니다.

```math
\min (1-\lambda)\sum_\omega p_\omega C_\omega+
\lambda\left(\eta+\frac{1}{1-\alpha}\sum_\omega p_\omega\xi_\omega\right),
\quad \xi_\omega\ge C_\omega-\eta,\quad\xi_\omega\ge0.
```

이산 CVaR는 경계 원자의 일부 질량까지 포함해 상위 1−α 질량을 적분합니다. 128경로에서 큰 값 13개의 단순평균이 아닙니다. λ0에서는 η/ξ가 목적함수로 식별되지 않으므로 raw epigraph와 독립 계산한 VaR/CVaR를 구분합니다. RN은 같은 시나리오의 평균가격 LP와 일치하며 원래 점예측 LP와 반드시 같지는 않습니다.

GLOP9.14.6206의 기존 seed, dual simplex, 10초 제한, primal/dual 1e−8, 수량 1e−7t, 목적 abs1e−4USD/rel1e−8를 유지합니다. OPTIMAL에 더해 VerifySolution·공유 변수·물리/greedy 회계·시나리오 비용·기대비용/CVaR/목적 재구성을 통과해야 실행합니다. FEASIBLE은 최적이 아닙니다. 실행 수량의 작은 정규화는 선언된 허용오차 안에서만 적용하며 그 밖의 실패는 숨은 fallback 없이 비교를 중단합니다.

## 엔진과 종료 회계

월별 순서는 입고→실현 수요 출고→초과재고 폐기→비용 귀속→공개 상태로 결정→발주입니다. 실제 입고월은 발주월+lead+평가 엔진 전용 delay입니다. Fulfilled=min(beginning+receipts,demand), 부족은 당월 한 번만 계상하는 lost sales이며 다음 달 backlog가 아닙니다. Ending=beginning+receipts−fulfilled−disposed입니다.

매입비는 **수령월** 지수×premium으로 한 번 계상합니다. 보관비는 월말재고, 부족·폐기비는 실현 수량을 사용합니다. 전체 마지막 월에만 9×abs(ending−200)을 청구합니다. 매월 계획 목적함수의 말기 근사를 실제 원장에 누적하지 않습니다.

Validation은 36개 결정/38개월 원장, Active35/Runoff3입니다. 잠긴 최종 달력은 22/24, Active21/Runoff3입니다. Runoff에는 provider/정책 호출과 신규 q가 없고 마지막 origin 이후 미래 계획 q도 금지합니다. 종료 pipeline은 비어야 합니다. 동일 외생 조건 아래 정책 상태는 독립적이며, 실패는 시점·원인·확인 가능한 prefix를 남기고 없는 부분 원장을 만들거나 완전 성과처럼 순위화하지 않습니다.
