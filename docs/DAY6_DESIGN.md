# Day 6 사전 설계와 범위 조정

2026-10-29 Asia/Seoul. 시나리오와 Toy ledger 생성 전에 `configs/day6.toml`을 고정했습니다. 기존 모델·calibration·분할·결과를 바꾸지 않고 신규 의존성 없이 구현합니다.

## 공동 OOF와 가격 경로

Day 5 `all_oof_forecasts.csv`의 원본 point와 fit proof를 재사용합니다. 이 파일에는 실제 target 가격이 없습니다. 현재 t의 실제값은 `load_development_store`의 as-of history에서만 가져옵니다. 같은 모델·과거 origin o의 h=1,2,3을 묶고, `o+3<=t−1` 및 세 target의 `available_at<=d_t`, fit 당시 `fit_information_end<=o−1`와 최대 label 공표시각<=d_o를 모두 검사합니다. 개별h 잔차가 성숙해도 미완성 vector는 제외합니다. Bridge/Holdout은 거부합니다.

최근60개 완전 vector, 최소24개를 고정합니다. 부족·비양수·비유한 경로는 명시적 실패이며 clip이나 재추첨으로 숨기지 않습니다. 기본 모델은 SARIMAX, LightGBM L2 point 기반 vector는 별도 대체 후보로 같은 생성기를 통과시킵니다. q50과 L2를 바꾸거나 Day 5 quantile/보정 구간을 분포로 변환하지 않습니다.

| 방식 | 정의 | 선택 근거와 한계 |
|---|---|---|
| Additive | P*_(t,h)=point_(t,h)+(actual_(o,h)−point_(o,h)) | USD/t 오차를 직접 해석할 수 있으나 nominal 가격 수준에 민감하고 음수가 가능 |
| Multiplicative — 기본 | P*_(t,h)=point_(t,h)×actual_(o,h)/point_(o,h) | 양수 point/actual이면 양수, 상대오차 vector를 함께 이동; 상대오차의 기간 안정성은 미검증 |

한 번의 draw로 과거 origin 하나를 뽑아 세h 모두 사용합니다. 같은 draw의 additive 후보도 진단하되 결과를 보고 방법을 고르지 않습니다. 128개 시나리오, 각1/128 가중치입니다. signed residual·가격 비율·생성 가격의 평균/분산/상관을 기록합니다. 벡터 내부 의존성은 함께 표집하지만 과거 origin 사이의 시간 순서나 의사결정 월 사이의 공동 의존성까지 보존하지는 않습니다. 중복·겹치는 target과 작은 OOF pool의 한계를 유지합니다.

Planning seed2026102901 / evaluation seed2026102902를 분리하고 origin·모델·purpose별 SHA-256으로 로컬 seed를 파생합니다. 전역 RNG 없이 명시적인 새 `random.Random`을 전달하며 정책 호출 순서에 의존하지 않습니다. ID에 purpose·모델·origin·draw를 포함합니다. 같은 pool의 다른 재표집이므로 seed가 달라도 독립적인 시장 표본이나 진정한 OOS 평가가 아닙니다. 오늘은 실제 validation target에 대한 구매 성과 평가가 없습니다.

## 기존 문서와의 차이

로드맵 Day 6의 실제 가격 기반 Fixed validation 운영 평가는 이번 사용자 지시에 따라 **Toy만** 실행합니다. Day 0의 확률 지연0.10/0.03·lognormal 수요 추첨은 제안 상태로 보존하며 오늘은 기본 지연0, 최대1개월의 외생 지정 지연과 명시적인 Toy 수요를 사용합니다. 확률이나 가격-납기 상관을 추정·생성하지 않습니다.

공급업체 A/B의 premium2%/8%, lead2/1개월, capacity80/100t, 월100t 수요 계획, Fixed80/20배분, 재고200t·capacity400t, 보관3·부족1500·폐기1·종료편차9 USD/t는 기존 가정을 유지합니다. MOQ0·multiple0은 연속 물량, 운송비0입니다. 모델은 공급업체 실제 정보가 아닙니다.

Toy A~E는2000-01~06의 명백한 인공 가격을 사용합니다. 초기재고200t에 **Toy 전용 초기 pipeline A80/B20**을 입력해 정상 사례가 수요를 충족하게 합니다. 이는 미래 정책 비교의 빈 초기 pipeline 기본값을 바꾼 것이 아닙니다. 정상과 지연 사례에서는 버퍼가 부족을 막을 수 있으며, 부족이 없으면 그대로 기록합니다. 수요 급증·복합 사례와 작은 단위 테스트에서 실제 lost sales를 검산합니다.

## 월별 이벤트와 정책 경계

월초 입고 → 실현 수요 출고 → 초과 재고 폐기 → 월말 비용 귀속 → 공개정보만으로 정책 결정 → 신규 발주 순서입니다. 발주 k의 promised=k+lead, 실제수령=k+lead+외생delay입니다. Delay는 발주월·업체별로 미리 고정합니다. 정책에는 promised·미납/overdue 상태만 전달하며 실제 미래 도착월·delay·미래수요·월t 가격·비용 역산 정보·evaluation seed는 주지 않습니다.

시장가격은 월평균입니다. 단가는 납품월 P_r×(1+premium), 비용은 수령월 말 accrual로 한 번 계상합니다. 실제 지수 공개는 다음 달이므로 정책에 현재 월 구매단가/비용을 공개하지 않습니다. 초기 재고 취득비는 sunk cost, 초기 pipeline은 미수령 발주이므로 도착할 때 비용에 포함합니다. 지급·현금흐름·세금·환율은 미구현입니다.

`available=beginning+received`, `fulfilled=min(available,demand)`, `unmet=demand−fulfilled`, `disposed=max(available−fulfilled−capacity,0)`, `ending=available−fulfilled−disposed`입니다. Lost sales는 해당 월 한 번만 부족 패널티를 부과하고 다음 달 수요에 더하지 않습니다.

월말 보관비=3×ending, 부족비=1500×unmet, 폐기비=1×disposed입니다. 총비용은 premium 포함 매입비+운송비+보관비+부족비+폐기비+최종월에만9×|ending−200|입니다. 잔여재고 매각수익은0입니다. 신규 발주는 알려진 최대delay를 고려한 `k+lead+max_delay<=T`만 허용합니다. Fixed는 이 규칙 때문에 제외된 업체 물량을 다른 업체에 재배분하지 않습니다. 마지막 pipeline이 비면 완료하며, 외부 초기 pipeline/사용자 정책이 이 조건을 깨면 실패로 처리합니다. 창 밖 미도착 비용을0으로 숨기지 않습니다.

## Toy 사전 입력과 손계산 기준

공통 가격은100 USD/t, 수요100t/월, 초기 pipeline은1999-12 발주의 A80(2000-02 예정), B20(2000-01 예정)입니다. 신규 발주량은월별100/100/100/20/0/0t입니다. Case B는A의2000-01 발주80t만3월→4월 지연, C는3월 수요300t, D는가격100/100/150/200/200/200, E는B+C+D를 결합합니다. 복합 충격은 명시적인 스트레스 입력이며 확률적 상관관계의 주장이 아닙니다.

| Case | 매입비 | 보관비 | 부족량(t)/비용 | 종료비 | 총비용 USD |
|---|---:|---:|---:|---:|---:|
| A 정상 | 43440 | 1860 | 0 /0 | 1620 | 46920 |
| B 지연 | 43440 | 1620 | 0 /0 | 1620 | 46680 |
| C 수요 급증 | 43440 | 720 | 180 /270000 | 1800 | 315960 |
| D 가격 상승 | 69240 | 1860 | 0 /0 | 1620 | 72720 |
| E 복합 | 73320 | 1200 | 180 /270000 | 1800 | 346320 |

이는 엔진 실행 전 계산한 기준이며 실행 후 독립 검산으로 확인해야 합니다. 지연 B의 낮은 보관비를 실제 비용절감 실적이나 정책 우월성으로 해석하지 않습니다.
