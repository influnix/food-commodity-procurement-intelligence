# 불확실성 및 공동 가격 시나리오

## 원본 분위수와 유효성

SARIMAX는 기본 중앙 80% 구간과 Gaussian q10/q50/q90을 생성합니다. LightGBM은 기존 특징·사양으로 .1/.5/.9의 direct quantile objective를 사용합니다. L2 점예측과 q50을 구분하며, 원본 quantile crossing을 기록하고 정렬·clip하지 않습니다.

공용 validator는 bool을 제외한 숫자 Real, 유한한 양수 점예측, 유한하고 순서가 맞는 구간, q10≤q50≤q90 및 endpoint 일치를 요구합니다. 비유한 분위수를 base 필드로 옮겨 정상처럼 만들지 않습니다. 유한한 0·음수 통계 경계는 NONPOSITIVE_BOUND_REVIEW로 보존합니다. 실제·시나리오 가격은 항상 양수여야 합니다. 무효 구간은 score 보정에서 제외하지만, 유효한 양수 점예측은 완전 성숙 후 Joint 벡터에 사용할 수 있습니다.

## Horizon별 구간 보정

모델·Horizon·원본 방법을 분리하고, 과거에 발행돼 현재 공표된 관측과 결합할 수 있는 잔차만 사용합니다. origin o의 h는 `o+h≤t−1`, actual_available_at≤d_t일 때 공개됩니다. 최근 60개 적격 score를 선택하며 최소 24개가 필요합니다.

```math
s_i=\max(L_i-y_i,\ y_i-U_i,\ 0),\qquad
k=\lceil(n+1)\times0.8\rceil,\qquad
[L',U']=[L-s_{(k)},U+s_{(k)}].
```

보간은 없습니다. 확장한 양끝은 새로 식별한 q10/q90이 아닙니다. 보정 q 필드는 null로 두고 원본 base quantile을 유지하며, 구간 양끝만으로 정의할 수 없는 Pinball loss는 NA입니다. pool 부족은 유효 raw 구간을 `insufficient_raw_fallback`으로 유지하고, raw 무효는 `raw_invalid_uncalibrated`로 기록합니다. 이러한 통계 상태와 solver·정책의 fallback 부재를 구분합니다.

과거 완전 벡터 보정은 별도 호환 수명주기로 남깁니다. `HorizonSequentialOOF`는 각 Horizon을 독립 공개하므로 늦은 H3가 성숙한 H1/H2를 막지 않습니다. 16개 반례·기존 구간/fallback 차이 4건·공용 raw 유효성 수정은 과거 기록과 구분하며, 이전 방법과 같은 결과였다고 소급해 표시하지 않습니다.

## 완전 벡터 Joint 시나리오

Joint는 세 target과 공표시각이 모두 성숙한 o+3≤t−1을 요구합니다. 모델별로 원천·학습·발행 증거가 확인된 최근 60개 완전 벡터를 사용하며 최소 24개가 필요합니다. 한 번의 추출로 과거 origin 하나의 H1/H2/H3 비율 벡터 전체를 사용합니다.

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

Validation의 명목 80% 구간은 과소포함했습니다. SARIMAX raw는 Coverage 48.15%·폭 60.9970, 보정 후 61.11%·84.4602입니다. LightGBM은 raw 58.33%·164.6295, 보정 후 65.74%·193.9608 USD/t입니다. 이를 숨기려고 window·모델·위험계수를 재선택하지 않았습니다. 겹치는 target·expanding 학습·시간 의존성 때문에 교환가능성 기반 보장을 주장하지 않습니다. 구간 무효·학습 실패·Joint 부족·원천 미검증은 서로 다른 상태입니다.
