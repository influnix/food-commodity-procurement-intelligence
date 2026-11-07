# 불확실성 및 공동 가격 시나리오

세 달의 가격을 한 값씩 제시하면 주문을 늦출 때 가격이 예상과 다르게 움직일 가능성이 계획에 드러나지 않습니다. 납기가 서로 다른 공급업체를 비교하려면 한 달씩의 오차 범위와 세 달이 함께 움직이는 경로가 모두 필요합니다. 이 문서에서 구간은 납품월별 오차를 설명하고, 공동 경로는 같은 주문 계획의 비용을 여러 가격 흐름에서 비교하는 데 쓰입니다.

## 원본 분위수와 유효성

SARIMAX는 기본 중앙 80% 구간과 Gaussian q10/q50/q90을 생성합니다. LightGBM은 기존 특징·사양으로 .1/.5/.9의 direct quantile objective를 사용합니다. L2 점예측과 q50을 구분하며, 원본 quantile crossing을 기록하고 정렬·clip하지 않습니다.

공용 validator는 bool을 제외한 숫자 Real, 유한한 양수 점예측, 유한하고 순서가 맞는 구간, q10≤q50≤q90 및 endpoint 일치를 요구합니다. 비유한 분위수를 base 필드로 옮겨 정상처럼 만들지 않습니다. 유한한 0·음수 통계 경계는 NONPOSITIVE_BOUND_REVIEW로 보존합니다. 실제·시나리오 가격은 항상 양수여야 합니다. 무효 구간은 score 보정에서 제외하지만, 유효한 양수 점예측은 완전 성숙 후 Joint 벡터에 사용할 수 있습니다.

## Horizon별 구간 보정

모델과 납품월마다 오차 양상이 다를 수 있으므로 모델·Horizon·원본 방법별로 따로 보정합니다. 과거에 발행한 구간의 양끝에서 실제 가격이 얼마나 벗어났는지를 score로 쌓습니다. origin o의 h는 `o+h≤t−1`, actual_available_at≤d_t일 때 공개됩니다. 최근 60개 적격 score를 사용하고, 최소 24개가 모여야 보정을 계산합니다.

```math
s_i=\max(L_i-y_i,\ y_i-U_i,\ 0),\qquad
k=\lceil(n+1)\times0.8\rceil,\qquad
[L',U']=[L-s_{(k)},U+s_{(k)}].
```

보간은 없습니다. 확장한 양끝은 새로 식별한 q10/q90이 아닙니다. 보정 q 필드는 null로 두고 원본 base quantile을 유지하며, 구간 양끝만으로 정의할 수 없는 Pinball loss는 NA입니다. pool 부족은 유효 raw 구간을 `insufficient_raw_fallback`으로 유지하고, raw 무효는 `raw_invalid_uncalibrated`로 기록합니다. 이러한 통계 상태와 solver·정책의 fallback 부재를 구분합니다.

한 달의 구간을 보정하는 데 세 달의 정답을 모두 기다릴 이유는 없습니다. `HorizonSequentialOOF`는 각 Horizon을 독립 공개하므로 H3가 아직 공개되지 않아도 성숙한 H1/H2의 score를 쓸 수 있습니다. 과거 완전 벡터 보정은 별도 호환 수명주기로 남깁니다. 16개 반례, 기존 구간/fallback 차이 4건, 공용 raw 유효성 수정은 두 방법의 검증 기록을 구분해야 하는 근거입니다.

## 완전 벡터 Joint 시나리오

세 달의 경로를 만들 때는 반대로 세 오차가 함께 필요합니다. 각 Horizon의 오차를 따로 뽑으면 같은 결정에서 가격이 동시에 예상보다 높거나 낮았던 패턴이 끊어집니다. Joint는 o+3≤t−1이고 세 target의 공표시각 조건을 모두 충족한 뒤, 과거 origin 하나의 H1/H2/H3 실제값 대 예측값 비율을 한 묶음으로 뽑습니다. 모델별로 원천·학습·발행 증거가 확인된 최근 60개 완전 벡터를 사용하며 최소 24개가 필요합니다.

```math
P^*_{t,h}=\hat P_{t,h}\frac{P_{o+h}}{\hat P_{o,h}},\qquad h=1,2,3.
```

동일 가중치의 128경로를 생성합니다. 같은 draw의 가산형 후보는 진단 전용입니다. 실제값·점예측의 양수를 검사하고 유효하지 않으면 clipping·재추출 없이 실패합니다. 세 분위수만으로 사건 확률이나 공동 분포를 만들지 않습니다.

Planning seed 2026102901, evaluation seed 2026102902와 origin/model/purpose SHA로 로컬 seed를 유도합니다. 명시적 RNG와 사전 고정 외생 경로를 사용해 정책 호출 순서가 경로를 바꾸지 않게 합니다. ID는 purpose/model/origin/draw를 구분합니다. 벡터 내부 의존성은 보존하지만 표집 origin 간·연속 의사결정 월 간 시간 의존성까지 보장하지 않습니다. 같은 pool을 다른 seed로 재표집한 결과는 독립 시장·OOS 평가가 아닙니다.

같은 모델의 RN/RA는 불변 Planning 세트를 공유합니다. Evaluation purpose·잘못된 origin/model·사용 불가능한 pool은 정책에서 거부합니다. 실제 미래 경로는 scenario adapter에 전달하지 않습니다.

## Legacy 복원과 Native 전환

세션 시계가 진행되기 전에 외부 archive digest로 정확한 Legacy 192개 batch를 검증하고, 전체 검사가 끝난 뒤 상태를 변경합니다. 첫 2024-09 결정에서는 공표 가정상 저장 시드 target이 모두 성숙할 수 있습니다. 2024-06..08 발행 공백은 채우지 않습니다. 새 발행은 현재 Native publisher와 성공한 학습 이벤트를 요구하고, 원래 Legacy hash·값·등급은 불변입니다.

기존 합성 검증은 신규 Native 44개 batch·286개 fit 이벤트, 보정 132행, 44×128=5632개 Joint 경로를 확인했습니다. 출처 계보 변화는 pool/planning digest를 바꾸지만 표집 origin·seed·비율·가격을 바꾸지 않았음을 구분해 검산했습니다. 실제 World Bank Runtime의 검증은 아닙니다.

## 관측된 Coverage 한계

보정 뒤 두 모델 모두 실제 가격을 더 자주 포함했지만 구간도 넓어졌습니다. SARIMAX는 Coverage 48.15%·폭 60.9970에서 61.11%·84.4602로, LightGBM은 58.33%·164.6295에서 65.74%·193.9608로 바뀌었습니다. 폭의 단위는 USD/t입니다. 두 모델 모두 명목 80%에 못 미쳤으며 이 결과로 window·모델·위험계수를 다시 선택하지 않았습니다. 겹치는 target, expanding 학습, 시간 의존성 때문에 교환가능성에 기댄 보장을 이 결과에 적용할 수 없습니다. 구간 무효·학습 실패·Joint 부족·원천 미검증은 서로 다른 상태로 기록합니다.
