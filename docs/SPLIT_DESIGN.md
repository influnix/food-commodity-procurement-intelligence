# 실제 날짜 분할과 정보 가용성 계약

설계·설정 고정일: 2026-10-24 Asia/Seoul. 실제 데이터의 **달력·관측 개수**와 Day 0의 24개월 holdout/36 validation origins 규칙으로 선택했습니다. 가격 패턴·모델 점수·holdout 성과는 선택에 사용하지 않았습니다. 이는 현재 수행한 소급 날짜 설계이며, 2024년에 실제 사전 등록했다는 뜻은 아닙니다.

설정의 기준 파일은 `configs/splits.toml`입니다. 시계열 분할은 월 라벨과 target 기준이며 행 무작위 분할은 없습니다. `configs/day0.toml`은 당시 설계 snapshot으로 보존합니다.

## 후보 비교와 선택

| 항목 | A: 24개월 Holdout — 선택 | B: 36개월 Holdout — 대안 |
|---|---|---|
| Train 원시 관측 블록 | 1960-01~2021-06, 738개월 | 1960-01~2020-06, 726개월 |
| Validation origin | 2021-06~2024-05, 36개 | 2020-06~2023-05, 36개 |
| Validation target 합집합 | 2021-07~2024-08, 38개월 | 2020-07~2023-08, 38개월 |
| 정보 지연 bridge | 2024-09, 1개월 | 2023-09, 1개월 |
| 최종 Holdout target | 2024-10~2026-09, 24개월 | 2023-10~2026-09, 36개월 |
| Holdout 완전 3-horizon origin | 2024-09~2026-06, 22개 | 2023-09~2026-06, 34개 |
| 첫 Validation fit의 가용 관측 | ~2021-05, 737개월 | ~2020-05, 725개월 |
| 장단점 | 기존 24개월 설계 유지, 더 최근 validation, 기간 확장에 따른 추가 변경 최소화 | 더 긴 최종 평가창, 대신 선택용 validation이 1년 이전으로 이동 |

A를 권장·채택합니다. B보다 성능이 좋을 것이라는 이유가 아니라 기존 설계와의 일관성과 개발/최종 평가의 역할을 근거로 했습니다. B의 holdout 가격·성능을 비교해 A를 고르지 않았습니다. 변경 후 자료만 쓰는 대안은 전체 75개월로 초기 학습 120개월 요건을 충족하지 못해 기본 사양으로 삼지 않았습니다.

## Day 0 문서와의 중요한 정정

기존 EVALUATION_PROTOCOL은 holdout 시작월을 `a`라 할 때 validation 마지막 origin을 `a-4`로 잡았습니다. target overlap만 보면 마지막 target이 `a-1`이라 holdout target `a`와 겹치지 않습니다. 그러나 **선택을 끝내야 하는 첫 holdout 결정 시점은 `d_(a-1)`**이며, 이때 알 수 있는 가격은 `P_(a-2)`까지입니다.

따라서 마지막 validation vector의 조건은 다음과 같습니다.

```math
v_{last}+3 \le (a-1)-1 = a-2
\quad\Rightarrow\quad v_{last}\le a-5
```

최종 validation origin 36개는 `a-40 .. a-5`, 즉 **2021-06~2024-05**입니다. 기존 안은 2021-07~2024-06이었습니다. 한 달 앞당겨 origin 36개를 유지했고, 평가 성과를 보고 옮기지 않았습니다. 2024-06 origin의 h=3 target인 2024-09는 선택 시점에 미공표이므로 주 모델 선택 점수에 사용할 수 없습니다.

## 원시 월수, origin 수, target-pair 수

| 구간 | 원시 월수 | 완전 3-horizon origin | origin 기간 | target-pair 수 | target 합집합 |
|---|---:|---:|---|---:|---|
| Train 정적 후보 | 738 | 734 | 1960-02~2021-03 | 2,202 | 1960-03~2021-06, 736개월 |
| Validation | 38 | 36 | 2021-06~2024-05 | 108 | 2021-07~2024-08, 38개월 |
| Bridge | 1 | 주 평가 없음 | 해당 없음 | 0 | 2024-09 |
| Holdout 주 비교 | 24 | 22 | 2024-09~2026-06 | 66 | 2024-10~2026-09, 24개월 |

Train 734개는 **값을 사용하지 않은 달력상 지도학습 후보**입니다. 최소 1개 과거 관측이 있는 origin부터 만들었으며 실제 학습 행수나 모델 점수가 아닙니다. 각 모델의 lag·rolling 요건은 Day 3 이후 별도 마스크로 추가합니다. 최초 120개월은 **평가 fit에 필요한 최소 원시 학습 이력**이지 모든 과거 지도학습 후보를 120개월씩 제거하는 규칙이 아닙니다. 가격-only 시계열 모델은 해당 origin에서 사용 가능한 원시 이력 전체를 활용할 수 있습니다.

첫 validation origin **2021-06**에는 2021-05까지 **737개월** 가격을 이용할 수 있습니다. Train 블록의 마지막 2021-06 가격은 아직 사용할 수 없습니다. 정적 후보 734개 중 2021-03 origin의 마지막 target은 2021-06이라 미확정입니다. 따라서 첫 fit에는 **733개 성숙한 vector 후보 / 2,199 target-pairs**, 마지막 학습 origin **2021-02**만 허용합니다. 이 수 역시 실제 특징/모델 요건 적용 전입니다.

Holdout 마지막 2개 origin을 horizon별로 보면 2026-07에는 h=1,2, 2026-08에는 h=1만 실제 관측 종료월 안에 있습니다. 보조 구조상 origin 24개, h별 개수는 **24/23/22**, 합계 69쌍입니다. 주 비교는 공통 완전 origin 22개/66쌍이며 보조 tail 3쌍과 혼합하지 않습니다. 2026-10 이후 target은 생성하지 않습니다. 지금은 날짜 metadata만 만들었으며 holdout 예측·정답 조회·점수 계산은 없습니다.

## Origin과 정보 집합

`t`는 결정이 이루어지는 월 라벨이며 `d_t`는 UTC 월말 23:59:59의 decision event입니다. 같은 timestamp의 공표는 결정 직전에 일어난 것으로 간주하는 Day 0 순서를 유지합니다.

```math
\mathcal{F}_t=\{P_m:m\le t-1,\ available\_at(P_m)\le d_t\}
```

- Feature 관측 마감은 `t-1`입니다. `P_t`는 금지합니다. 실제/가정 공표 timestamp가 더 늦으면 달력상 과거여도 제외합니다.
- business horizon `h=1,2,3`의 target은 `t+h`입니다. 최신 관측 `t-1` 기준 model step은 `h+1=2,3,4`입니다.
- 관측월 `m`의 target label은 다음 달 말에 알려진다는 가정이므로 `available_at(P_m)=d_(m+1)`입니다. 최신 수정본의 과거값에 적용한 pseudo-real-time 가정입니다.
- origin `o`의 특징은 `F_o`만으로 계산하고, 이후 재학습 때도 그 샘플의 특징을 미래 값으로 다시 계산하지 않습니다. 스케일러/대체/특징 선택은 현재 fold 학습 자료에서만 fit합니다.

## 학습 target의 성숙도와 purge

평가 origin `t`에서 과거 학습 origin `o`의 완전 vector를 사용할 필요충분한 날짜/공표 조건은 다음과 같습니다. 별도의 특징 유효성 조건은 추가로 충족해야 합니다.

```math
o<t,\qquad \max_{h\in\{1,2,3\}}(o+h)\le t-1,
\qquad \max_h available\_at(P_{o+h})\le d_t
```

기본 1개월 공표 지연에서는 **`o<=t-4`**입니다. 원시 Train/Validation 날짜만 구분하거나 `o<t`만 확인하는 것으로는 부족합니다. 지연 timestamp가 더 늦을 때는 `o<=t-4`만으로도 부족해 timestamp 검사가 추가로 필요합니다.

개별 horizon 학습기를 따로 쓰면 `o+h<=t-1`로 검사할 수 있습니다. 완전 vector와 개별 horizon 마스크를 혼합해 일부 미확정 타깃을 끼워 넣지 않습니다. `eligible_training_samples`는 전달된 sample의 **모든 실제 target**을 검사하며, 완전 vector의 날짜를 partial처럼 위장하지 못하도록 `ForecastSample`이 origin/target 관계를 검증합니다.

### 구간 간 overlap과 적용 범위

1. 고정 Train/Validation 구간은 target 집합이 서로 겹치면 안 됩니다. 첫 validation target을 `v`라 할 때 Train 완전 vector는 `o+3<v`, 즉 `o<=v-4`여야 합니다. 경계에 걸치는 혼합 vector는 어느 한 고정 구간에 끼워 넣지 않습니다.
2. 추가로 첫 평가 origin의 target 성숙도 조건을 적용합니다. 선택안에서 정적 Train 마지막 origin 2021-03은 첫 validation의 정보 cutoff에 걸려 일시 제외됩니다. 다음 달 target이 공표되면 재사용할 수 있습니다.
3. 매월 expanding 재학습에서는 과거 validation target도 그때까지 공표됐다면 학습에 추가할 수 있습니다. 동일한 고정 모델 설정 아래의 정상적인 prequential 평가입니다. 과거 validation 전체와 영원히 target을 분리하는 방식은 사용하지 않습니다.
4. 대신 **현재 fold**의 미래 평가 target과 학습 target의 overlap은 금지합니다. `assert_no_target_overlap`은 이 상황과 정적 구간 분리에 사용합니다. 과거 validation 전부를 금지 목록으로 넣는 용도가 아닙니다.
5. validation origin 간에는 horizon이 겹쳐 같은 가격을 여러 horizon/origin에서 평가할 수 있습니다. 이는 의도된 다중 horizon 평가이며 독립 표본이라고 가정하지 않습니다.

### 최소한의 bridge와 불필요한 embargo 방지

첫 holdout 결정 `2024-09`에 2024-09 가격은 모릅니다. 그래서 그 한 달을 model selection target에서 제외하고 bridge로 표시했습니다. 원본에서 지운 달이 아니며, 향후 잠긴 holdout 실행의 origin 2024-10에는 2024-09 가격이 공개되면 사전 고정된 자동 fit 이력에 포함할 수 있습니다. 오늘 개발 API에서는 bridge 가격도 숨깁니다.

2024-06/07/08 origin은 완전 vector 기준 주 validation에 들어가지 않습니다. 일부 성숙한 horizon까지 가격 행 전체를 삭제한 것은 아니며, 날짜 catalog에는 개별 pair가 유지됩니다. 비교 가능한 완전 horizon 36개를 주 선택 표본으로 사용하고, 부분 horizon 실험은 별도로 사전 정의할 때만 보조로 사용합니다.

추가적인 전후 ±3/12개월 embargo나 holdout 종료 뒤의 embargo는 없습니다. 학습이 항상 과거에서 미래로만 이동하고 공표 성숙도를 직접 검사하므로 뒤쪽 학습 자료를 쓰는 양방향 CV의 규칙을 기계적으로 가져오지 않습니다. 2020-07 정의 경계 제외는 별도의 민감도 가정이며 누수 purge와 구분합니다.

## 구현 인터페이스와 holdout 잠금

| 기능 | 구현 | 가격 노출 |
|---|---|---|
| 날짜·분할 계획 | `evaluation/splits.py`: load_split_plans, summarize_plan | 없음 |
| Origin/target 생성 | forecast_samples, sample_metadata | 없음; catalog에 price/raw_price 없음 |
| 미성숙 target 제거 | eligible_training_samples, assert_training_available | 날짜·공표 timestamp만 검사 |
| Overlap 검출 | assert_no_target_overlap, samples_in_partition | 겹친 월 라벨만 오류에 표시 |
| 값 접근 | `data/availability.py`: DevelopmentPriceStore.history_as_of / feature / training_targets | 허용된 origin의 공개된 과거값만 |
| 실제 입력 연결 | `data/audit.py`: load_development_store | 해시 검증 후 guarded store 반환 |

DevelopmentPriceStore에는 unfiltered 가격 export나 unlock 메서드가 없습니다. 첫 holdout origin 2024-09부터의 값 접근을 거부하며, bridge/holdout 가격 요청도 거부합니다. repr은 가격을 숨깁니다. 미래 Feature와 미성숙 학습 target 요청은 예외를 냅니다. 실제 원본/CSV가 로컬 파일로 존재하므로 이것은 **프로그래밍 인터페이스 경계**이며 OS 차원의 접근통제나 악의적 우회 방지는 아닙니다. 모델 코드는 Day 1 CSV를 직접 읽지 않고 이 경계를 사용해야 합니다.

현재 `holdout_locked=true`를 false로 바꾸면 설정 검증 자체가 실패합니다. 최종 모델·정책·시뮬레이션 가정·seed bank까지 잠그는 Day 10과 별도 승인된 최종 evaluator가 생기기 전에는 holdout 값을 공개하지 않습니다. 날짜 분할의 오늘 잠금과 최종 분석 계획 잠금은 서로 다른 단계입니다.

## 검증한 불변식과 남은 범위

Toy 테스트로 시간 순서, 경계 월, 연말/윤년, t-1 Feature cutoff, target 성숙도, 실제 지연 timestamp, target overlap, partial tail, 관측 종료 이후 target 차단, 설정 복제, holdout 값 변조에 대한 개발 view/감사 출력 불변성을 검증했습니다. 보고서 integration test에서도 holdout에 큰 합성 값을 넣어 출력에 노출되지 않음을 확인했습니다. 실제 시장가격은 테스트 fixture에 넣지 않았습니다.

Day 3에서 lag/rolling과 Seasonal Naive를 추가할 때 그 파생 feature의 모든 원천 월을 검사하고, fold별 학습 자료에서만 전처리·MASE 분모를 계산해야 합니다. 오늘 학습·예측·점수·정책 결과는 없습니다.

Day 3 후속 기록(2026-10-27): 위 Day 2 날짜와 purge는 변경하지 않았습니다. 이제 [특징·기준 예측 명세](FEATURES_AND_BASELINE.md)의 validation 평가를 구현했습니다. 개발 as-of 가격 접근은 그대로 유지하고, 모든 예측 생성 후에만 사용하는 validation-only 정답 reader를 별도로 추가했습니다. 이 reader도 bridge/holdout을 거부하며 분할 잠금을 해제하지 않습니다. Day 2 당시 기록은 보존했습니다.
