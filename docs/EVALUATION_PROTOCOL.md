# 예측·구매 정책 평가 프로토콜

상태: Day 2 split/누수 검증, Day 3 Seasonal Naive, Day 4 SARIMAX/LightGBM의 동일36 origins/108쌍 비교를 완료했습니다. Holdout·정책 평가는 없습니다. 날짜는 `configs/splits.toml`, 기준 예측은 [Day 3 명세](FEATURES_AND_BASELINE.md), 새 모델 사양과 결과는 [Day 4 비교](MODEL_COMPARISON.md)를 따릅니다.

Day 5 갱신: [불확실성 비교](UNCERTAINTY_COMPARISON.md)의 native/quantile·rolling OOF 구간과 확률예측 지표를 추가했습니다. 원래 점예측·split을 보존했고 Holdout·정책 평가는 계속 없습니다.

## 시간 분할과 holdout 잠금

1. Day 1~2에 원천 기간·결측·단위를 감사합니다. 그래프/가격 수준으로 유리한 테스트 기간을 고르지 않습니다. 최종 holdout의 값·성과를 모델/가정 결정에 사용하지 않습니다.
2. 기본 분할: 최소 초기 학습 120개월, validation 결정 origin 36개월, 최종 연속 24개월의 **target/운영월** holdout입니다. 데이터가 부족하면 명시적인 설계 변경 후 날짜를 다시 고정합니다.
3. 최신 완결 관측월을 `b`, holdout 시작월을 `a=b-23`으로 잡습니다. holdout 예측 타깃과 운영월은 `[a,b]`입니다. 정책 결정은 월말 `a-1`부터이며 마지막 납품 허용월은 `b`입니다.
4. Day 2 정정: validation의 모든 타깃이 첫 holdout 결정 `d_(a-1)`까지 공표돼야 합니다. 그때 관측 가능한 월은 `a-2`이므로 마지막 validation origin은 **`a-5`**, 36개 origin은 **`a-40..a-5`**입니다. 기존 `a-4` 안은 마지막 target `a-1`의 공표 지연을 놓쳤습니다. 실제 선택은 validation origin 2021-06~2024-05, target 2021-07~2024-08; bridge 2024-09; holdout target 2024-10~2026-09입니다. 2024-06/07/08 origin은 완전 horizon 주 선택 표본에서 제외하되 개별 날짜 pair와 원본 가격 행은 보존합니다. 첫 validation fit의 가용 이력은 2021-05까지 737개월입니다.
5. direct 다중 horizon 학습 행은 **그 행의 모든 학습 타깃이 해당 fold의 정보 cutoff 이전에 공표된 경우만** 학습에 넣습니다. 단순 origin 날짜 split으로 미래 label을 허용하지 않습니다. 재귀 모델도 관측 cutoff까지만 fit합니다.
6. validation에서 모델, 특징, 재학습 주기, 구간 보정, 정책·시뮬레이션 범위, seed bank 구성, terminal/fallback 규칙을 정하고 잠금 manifest를 남깁니다.
7. holdout은 잠근 파이프라인을 한 번 실행합니다. 월별 자동 재학습은 사전 고정한 expanding-window 규칙으로 그때까지 공개된 관측만 추가할 수 있습니다. 이는 이전 holdout 월이 나중에 알려진 경우를 포함하지만 하이퍼파라미터·가정·보정법을 다시 선택하지 않습니다. 중간 성과를 보고 사람이 튜닝하지 않습니다.
8. holdout 결과를 본 뒤 변경한 실험은 탐색 결과로 별도 표시합니다. 같은 holdout을 새로운 독립 검증이라고 재사용하지 않습니다.

완전 vector의 과거 학습 origin `o`는 평가 origin `t`에서 `o+3<=t-1` 및 모든 label의 `available_at<=d_t`를 충족해야 합니다. 기본 지연에서 `o<=t-4`이며 정적 Train 블록에 속해도 이 조건을 면제하지 않습니다. 첫 validation fit에는 달력상 734개 정적 train vector 중 733개만 성숙합니다. 개별 모델의 lag 요건은 별도입니다. 이미 공표된 과거 validation target을 이후 origin에서 자동 expanding fit에 넣는 것은 허용하되 현재 fold target과의 overlap은 금지합니다. 상세 purge/최소 bridge 및 불필요한 embargo를 피하는 규칙은 [분할 설계](SPLIT_DESIGN.md)를 따릅니다.

날짜 고정 전에 가격값을 살펴볼 필요가 있으면 개발 구간만 분석합니다. 결측/기간 감사와 holdout 성과 탐색을 구분합니다. 데이터 버전 한계는 모든 결과에 `latest-vintage / pseudo-real-time`으로 표시합니다.

## 예측 백테스트

Day 4 비교 규칙: 세 모델의 actual/target/unit/scale을 키별 대조합니다. 실패 시 baseline 대체 없이 coverage와 missing keys를 공개합니다. 전체108개가 불완전한 모델의 자체 성공 표본 성과를 완전 모델과 직접 순위 매기지 않고, 모델 전체 개선율은 null로 둡니다. 모든 모델 공통 성공 키의 교집합 비교는 별도 표본·파일로 보고합니다. 이번 실제 실행은 모두108개 완전하므로 교집합도108개입니다. 108개 오차가 독립 표본이라는 가정은 사용하지 않습니다.

- 매월 월말 origin, expanding train, 1개월 재학습을 기본으로 합니다. 비교 모델은 Seasonal Naive, SARIMAX, LightGBM입니다. 모든 모델은 동일 origin·정보 cutoff·target에서 비교합니다.
- 비즈니스 horizon `h=1,2,3`은 납품월 `t+h`입니다. 최신 관측이 `t-1`이면 모델 step은 `h+1`입니다. holdout full-horizon 비교 origin은 `a-1..b-3`이며 모든 타깃이 `[a,b]`에 있어야 합니다.
- 운영 시뮬레이션은 마지막 `b`까지 진행하고 끝부분 계획 horizon을 줄입니다. 그 짧은 origin의 예측은 별도 보조 점수로 표시하여 full-horizon 모델 비교 표에 섞지 않습니다.
- 전처리·lag·rolling·특징 선택·하이퍼파라미터 탐색은 fold의 사용 가능 관측 안에서만 수행합니다. LightGBM 학습 label도 공표 시점으로 필터링합니다.
- 타깃 결측은 보간해 정답을 만들지 않습니다. 누락 origin/target을 모든 모델의 공통 평가 마스크로 처리하고 누락률을 보고합니다. 모델 자체 실패는 유리하게 삭제하지 않고 사전 고정한 Seasonal Naive fallback으로 대체해 실패율을 보고합니다.

### 점예측 지표

`e_(t,h)=P_(t+h)-yhat_(t,h)`.

- `MAE_h = mean_t |e_(t,h)|`, 단위 USD/t.
- `scale_t = mean_{m in train_t, m-12 in train_t} |P_m-P_(m-12)|`.
- `MASE_h = mean_t (|e_(t,h)| / scale_t)`. 분모는 origin별 학습 자료에서만 계산합니다. 유효 계절 차분이 없거나 scale=0이면 MASE는 NA와 원인을 보고하며 임의 epsilon으로 우회하지 않습니다.
- horizon별 값과 사전에 고정한 동일 가중 macro 평균을 함께 보고합니다. 수준이 다른 원재료를 MAE만으로 섞지 않습니다.

Day 3 집계: fold MASE는 3개 horizon ratio 평균, horizon MASE는 36 origins 동일 가중 평균, 전체는 108개 pair ratio 평균입니다. `전체 MAE/평균 scale`은 사용하지 않습니다. 정의 불가능한 MASE는 null과 사유·개수를 공개하며 이번 실제 결과의 undefined는 0입니다. 비교용 고정 scale은 첫 validation origin의 가용 이력(~2021-05)에서만 계산했고, 미공표 2021-06을 포함한 명목상 Train 전체 scale은 사용하지 않습니다. 주 scale 방식은 수치를 보고 고른 것이 아니라 기존 fold-as-of 프로토콜을 유지했습니다.

평가 정답은 모든 예측 생성 후 validation 전용 reader에서 결합합니다. 가격 정보 cutoff는 각 origin의 t-1이며 최종 채점 clock은 2024-09 말 선택 freeze입니다. 이전 validation 관측이 이후 공개되어 다음 fold의 이력에 들어가는 것은 허용하고, 현재 origin 미래 target의 선행 사용은 계속 금지합니다.

### 불확실성 지표

- quantile `q in {0.1,0.5,0.9}`, pinball loss `rho_q(y-yhat_q) = (y-yhat_q)*(q - 1[y<yhat_q])`.
- 80% 구간 coverage = `mean(1[q10 <= y <= q90])`, 평균 폭 = `mean(q90-q10)`. coverage만 높이려고 무한히 넓히지 않고 폭과 pinball loss를 함께 봅니다.
- 가격 상승 사건은 `P_(t+h)>P_(t-1)`입니다. 확률은 quantile 세 개만으로 임의 산출하지 않고 보정된 경로 표본에서 계산합니다. 필요시 Brier score를 보조 지표로 둡니다.
- calibration residual은 해당 origin 이전에 정답이 공표된 out-of-fold 예측에서만 수집합니다. 미래 horizon 정답이 아직 안 나온 잔차는 사용할 수 없습니다.
- horizon 간 독립 표본으로 경로를 합치면 위험이 왜곡될 수 있으므로 과거 오차 벡터의 블록 재표집 등을 validation에서 검토합니다. 정상성/coverage 보장을 가정하지 않고 실제 coverage를 보고합니다.

## 정책 백테스트의 공정성

| 정책 | 고정된 정의 | 사용 정보 |
|---|---|---|
| Fixed Procurement | 매월 총 100 t, A 80 t/B 20 t 발주. 유한 평가창 종료 규칙에 해당하는 발주는 생략하고 다른 업체에 재배분하지 않음 | 계약·달력·현재 상태; 가격 예측 미사용 |
| Forecast-Aware | 동일한 재계획 horizon에서 점가격·평균 수요·기본 lead로 비용 최소화 | 현재 context와 point forecasts |
| Risk-Aware | 같은 기본 비용과 제약에 가격/수요/납기 시나리오 및 CVaR 추가 | 동일 context와 예측분포·사전에 알려진 확률 |

- 정책 간 초기 재고 200 t, 빈 초기 pipeline, 창고 400 t, 비용계수·정보공개·계약·기간·회계 규칙을 통일합니다. 초기 재고의 취득원가는 비교기간 이전의 공통 sunk cost로 제외합니다.
- 평가용 실제 가격 경로, 수요 오차, 공급업체별 **발주월 기준** 지연, 충격 onset/크기를 외생적으로 먼저 생성해 공유합니다. 정책 호출 수나 주문량에 따라 RNG를 다시 소비하지 않습니다.
- evaluation seed와 planning seed는 분리합니다. 정책에는 평가용 seed와 미래 실현 경로가 보이지 않습니다.
- holdout 운영을 validation의 정책별 재고로 이어 시작하지 않습니다. 공통 재고와 pipeline으로 재시작합니다. 초기 재고 100/200/300 t 및 평가창 길이 민감도로 시작 상태의 영향을 확인합니다.
- 마지막 주문은 최대 지연 1개월까지 고려해 `k+L_s+1 <= b`일 때만 허용합니다. 모든 정책에 같은 달력 제약을 적용하여 창 밖 매입비용 은닉을 막습니다. 마지막에는 미도착 주문이 없어야 합니다.
- 종료 재고는 매각 수익을 주지 않고 동일한 목표 200 t에 대한 `9 USD/t * |I_b-200|` 비용을 추가합니다. 해당 수치는 가상 경계조건이며 비용 구성에서 분리합니다. 0/9/30 USD/t, 종료 목표·평가창 길이 민감도를 보고하여 종료효과에만 의존하는 개선을 배제합니다.
- 발주를 하지 않으면 재고가 소진될 수 있습니다. 회피하려고 미래 실제 수요를 넣지 않습니다. 과잉 수령·solver 실패 처리는 모든 정책에 동일한 물리/회계 규칙을 적용합니다.
- solver 실패 시 허용된 Fixed 배분으로 fallback합니다. 실패 origin·원인·fallback 물량을 기록하고 결과에 포함합니다. infeasible을 성공으로 처리하거나 해당 월을 제외하지 않습니다.

### 운영 지표

총 운영 조달비용 = 매입비 + 보관비 + 부족 비용 + 초과 재고 폐기비 + 종료 재고 비용. 매입비와 “총 운영비”를 별도 표기합니다. 비용은 납품월 기준 accrual USD이며 할인·환율·세금은 제외합니다.

- 미충족량 = `sum lost_sales_tonnes`, 미충족률 = `sum lost_sales / sum demand`.
- fill rate = `sum served / sum demand`, 품절월 비율 = `count(lost_sales>0)/월수`, 평균/최저 재고, 공급업체별 on-time receipt 비율을 보조 지표로 보고합니다. 수요 합이 0이면 비율은 NA입니다.
- 비용 변화율 = `(policy_cost-fixed_cost)/fixed_cost`; 음수는 절감입니다. 서비스 차이는 미충족률의 percentage point 변화입니다. 분모가 0이면 변화율은 NA이며 절대차만 표시합니다.
- tail risk: 같은 경로 집합에서 비용 VaR/CVaR90, 최악의 부족량. 경로 수가 작은 경우 tail 추정 한계를 함께 표시합니다.

## 시나리오와 민감도

기본, 가격 급등, 납기 지연, 수요 증가, 복합 시나리오를 별도 보고합니다. 가격 급등 경로는 실제 경로를 기반으로 만든 **합성 스트레스**입니다. 정책이 실제 발생 월을 미리 알 수 없습니다.

개발은 고정 seed 3개로 구조를 검증하고, 최종 평가는 최소 100개 외생 경로의 별도 seed bank를 사전 고정합니다. 동일 실제 가격 경로에서 반복한 합성 공급·수요 실험이라는 조건부 의미만 갖습니다. 미래 시장가격에 대한 100개의 독립 실증 표본이 아닙니다.

공통 경로별 비용·부족량 차이를 계산하고 scenario replication 단위 paired bootstrap 구간을 제시합니다. 월별 자기상관은 별도의 연속 월 block bootstrap 민감도로 검토하되 전체 운영을 일관되게 재실행합니다. 월별 비용행을 독립으로 섞어 재고 의존성을 무시하지 않습니다. bootstrap seed·반복수는 최종 결과 확인 전에 잠급니다.

민감도 축: 공급업체 premium/용량/lead·지연확률, 보관비, 부족 패널티, 수요 오차, 초기 재고, 창고 용량, CVaR 가중치, 종료 비용, 공표 지연 1/2개월. 한 번에 한 축과 사전 정의한 조합을 보고하고 유리한 셀만 선택하지 않습니다.

## 예측 개선과 의사결정 개선의 분리

1. **예측 효과:** Forecast-Aware 정책·제약을 고정하고 Seasonal Naive/SARIMAX/LightGBM 점예측만 교체합니다. 동일 예측 평가와 비용 평가를 연결합니다.
2. **위험 처리 효과:** 점예측·공급계약을 고정한 채 point-only, price uncertainty only, supply/demand uncertainty only, full risk를 비교합니다.
3. **위험 선호 효과:** 동일 시나리오로 `lambda=0`과 validation에서 고른 `lambda>0`을 비교합니다. Forecast-Aware와 Risk-Aware의 차이를 전부 CVaR 효과라고 부르지 않습니다.
4. **날씨 효과:** 동일 모델·정책에 weather on/off를 비교하고 추가 정보의 가용성 제약을 유지합니다.
5. 완전한 미래 가격·수요·납기 oracle은 선택적 진단 상한입니다. 정책 선정에 사용하지 않으며 실현 가능한 정책의 성과와 섞지 않습니다.

최종 보고는 모델별 MAE/MASE와 정책별 비용·서비스를 함께 표시합니다. 낮은 MAE가 낮은 구매비용을 보장한다고 가정하지 않습니다.

## Day 5 구간 평가의 추가 계약

사전 사양은 `configs/day5.toml`과 [불확실성 설계](DAY5_UNCERTAINTY_DESIGN.md)를 따릅니다. Day 4의 점예측과 기존 결과는 보존합니다. 같은 validation 108개 키에서 SARIMAX native, LightGBM quantile과 각각의 rolling OOF 보정 구간을 구분합니다. 기존 로드맵의 가격 경로 생성은 이번 사용자 지시에서 제외됐으므로 공동 시나리오를 생성하지 않습니다.

Train 내부2016-04~2021-03 origins의 historical OOF를 생성하고, 각 validation origin에서 당시 공표된 잔차만 추가합니다. 모델·horizon별 최근60개, 최소24개, 비음수 구간 초과 score와 유한표본 order statistic 규칙은 Coverage를 보기 전에 고정합니다. 실제 공표 timestamp와 t−1 월 제한, OOF 학습 정보 cutoff를 모두 검사합니다. 미래 target이 아직 공개되지 않았으면 과거에 생성된 예측이어도 보정에 넣지 않습니다.

보정 구간은 interval-only이므로 Pinball Loss를 임의로 만들지 않습니다. 원본 분위수 Pinball과 원본/보정 Coverage·Width의 유효 분모, invalid·missing·crossing·음수·fallback 빈도를 함께 보고합니다. 음수 경계는 clip하지 않고 기하학적 구간 평가에는 남기되 가격 경로로 사용할 수 없다는 상태를 기록합니다. 시계열 의존성과 월별 재학습 때문에 일반 split conformal의 exchangeability 보장을 적용하지 않습니다. 108쌍/38고유 target의 작은 표본이며 사후 수정본·가정 공표시각을 쓰는 pseudo-real-time 결과입니다.

Day 5 가격 상승 신호는 `P_target > 1.10 * 마지막 공개가격`이라는 사건의 임계값 대비 raw q90 또는 interval upper의 초과 여부입니다. 확률은 추정하지 않습니다. 이는 Day 0의 일반 상승 사건에 10% 크기 기준을 추가한 별도 진단이며 공급 부족·비용 절감을 뜻하지 않습니다.

## Day 6 공동 경로·Toy 검산

[구현 기록](DAY6_STATUS.md)의 공동 bootstrap은 같은 origin의 완전 성숙 vector를 모델별로 사용합니다. Multiplicative를 사전에 고정했으며128 draw×동일1/128 가중치입니다. 양수/유한성·합계1·source provenance·평균/분산/상관을 검사하지만 새 확률 Coverage나 구매 리스크 보장을 검증하지 않습니다. Planning과 evaluation의 seed/ID/소비 경계는 분리하되 같은pool에 대한 재표집이라는 한계를 남깁니다.

이번 사용자 지시에 따라 기존 로드맵의 실제가격 Fixed validation 운영 평가는 실행하지 않았습니다. 가상 가격으로 정상·지연·수요급증·가격상승·복합 5개 Toy만 손계산 검산했습니다. 초기미착발주A80/B20은 Toy 입력이며 실제 정책 비교의 초기조건 변경이 아닙니다. 같은 외생 입력과 Fixed 규칙의 결정적 ledger를 검증했으며 최적화 정책·실제 성과 비교·Holdout은 없습니다.

## Day 7 제한적 정책 비교

비교는초기재고200t·빈pipeline·같은Toy world의Fixed/Forecast-Aware만대상입니다. Day6opening pipeline검산과구분합니다. 같은실현가격·수요·발주cohort delay·계약·회계·기간을고정하고결과를본뒤튜닝하지않습니다. Toy가격belief는사전에정한100USD/t이며실제future world를예측으로쓰지않습니다. 따라서이번비교는SARIMAX예측정확도의운영효과실험이아닙니다.

GLOP OPTIMAL이어도수치·greedy재고흐름검사를통과해야실행합니다. FEASIBLE/실패를최적으로부르지않으며기본fallback은없습니다. 계획폐기0제한은엔진의정상재고임의폐기를추가하지않기위한보수적부분모델입니다. 실제저장Forecast는4개가상상태계획만smoke검사했고실제Validation구매ledger/개선율·Holdout평가는금지범위를유지했습니다.
