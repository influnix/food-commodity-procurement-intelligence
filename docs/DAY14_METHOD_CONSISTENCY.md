# Day14 방법론 정합성 감사

2026-10-31 Asia/Seoul. **감사는 완료했지만 최종 방법론은 ACTION_REQUIRED**입니다. MVP COMPLETE와 Day12의 합성 기술적 READY는 보존합니다. 오늘은 기존 코드·설정·Day0~13 결과를 변경하지 않고 작은 합성 반례와 저장된 Day12 합성 발행물을 검사했습니다. 실제 원천·Bridge·Holdout 접근, 신규 fit, 실제 Validation 구매 재평가, solver 호출은 없습니다.

## 계약 우선순위와 판단

[Day5 사전 설계](DAY5_UNCERTAINTY_DESIGN.md)와 [day5 설정](../configs/day5.toml)은 성과 확인 전에 horizon별 Calibration을 고정했습니다. [Day6](DAY6_DESIGN.md)는 공동 시나리오만 완전한 벡터를 요구하며 보정구간을 입력하지 않습니다. [Day11](DAY11_PRE_HOLDOUT_PROTOCOL.md)의 `rolling.calibration_spec`은 Day5, `scenario_spec`은 Day6를 참조합니다.

Day12 요청에는 “기존 Day5~6 규칙을 변경하지 않고”라는 원칙과 “전체 벡터를 Calibration 또는 Joint Scenario Pool에 포함하려면 o+3≤t−1”이라는 구체적 조건이 함께 있었습니다. [Day12 문서](DAY12_PRODUCTION_INTEGRATION.md)·[설정](../configs/day12.toml)·AGENTS의 Day12 계약은 이 차이를 명시적으로 공개하고 새 합성 adapter에만 구현했습니다. 따라서 은폐된 구현 실수로 판정하지 않습니다. 그러나 합성 통합 지시가 원래 통계 방법론과 같은 것은 아니며, 최종 평가의 Calibration을 자동 대체한다는 승인도 아닙니다. 현재 Day14 지시는 Day5의 사전 방법론 보존을 원칙으로 하되 이번에는 감사·제안만 허용합니다.

**권고안 A: 향후 승인된 변경에서 Calibration은 Day5의 horizon별 공개로 분리하고 Joint는 완전 벡터를 유지합니다.** Validation 오차·비용이 좋은 방식을 고른 것이 아닙니다. 이번에 코드를 고치거나 선택안을 승인·동결하지 않았습니다.

## 코드 수준 차이 표

o는 과거 발행 origin, t는 현재 origin, d_t는 월말 UTC 의사결정 timestamp, h∈{1,2,3}입니다. target=o+h이고 실제 관측 cutoff는 t−1입니다. 표의 원천은 [기존 calibration](../src/food_procurement_intelligence/uncertainty/calibration.py), [새 sequential](../src/food_procurement_intelligence/uncertainty/sequential.py), [joint](../src/food_procurement_intelligence/uncertainty/joint_scenarios.py)입니다.

| 항목 | Day5 | Day12 | 판정 |
|---|---|---|---|
| Forecast Origin | 과거 raw forecast o<t | immutable issued batch o<t | 발행 envelope가 다름 |
| Target Horizon | o+h, h1/2/3 | 동일 | 일치 |
| Actual Availability Cutoff | o+h≤t−1 및 a_(o+h)≤d_t | o+3≤t−1 및 모든 a_(o+j)≤d_t | H1/H2가 더 기다림; H1 공표 지연은 H3도 지연 가능 |
| Residual Release | 각 h가 처음 적격인 방문 clock | 전체 벡터가 처음 적격인 방문 clock | 최종 우선순위 확정 필요 |
| OOF Membership | valid raw interval·finite point, model/h/method 분리 | 완전 벡터 후 각 h score가 None이 아닌 것 | Joint membership은 interval validity와 별개 |
| Window / Minimum | 적격 score 최근60, 최소24 | 동일 | 공개 필터 이후 구성원이 달라질 수 있음 |
| Finite-Sample Rank | k=ceil((n+1)×.8), 1부터 셈 | 같은 함수(.8 고정) | 보간 없음, k>n도 부족 |
| Fallback | 부족이면 insufficient_raw_fallback | 동일 | invalid raw는 raw_invalid_uncalibrated, 성공 fallback 아님 |
| Point Forecast | 보정 중 변경 없음 | 동일 | q50과 L2 point도 구별 |
| Joint 연결 | raw point·actual의 완전 벡터를 별도로 구성 | raw point 대비 실제값 비율을 사용 | Calibration output을 소비하지 않음 |

수학적으로 Day5의 공개 집합은 I5_h(t)={o: 발행·fit proof 유효, o<t, o+h≤t−1, a_(o+h)≤d_t, raw interval 유효}입니다. Day12는 여기에 모든 j의 o+j≤t−1 및 a_(o+j)≤d_t를 요구합니다. 두 집합에서 같은 model/h/method의 최근60 score를 골라 n≥24일 때 `s=max(L−y,y−U,0)`의 k번째 값을 사용합니다. 보정은 [L−s_k,U+s_k]의 확장뿐입니다. 이것은 새로운 주변 q10/q90가 아니므로 보정 행의 q10/q50/q90는 null, 원래 값은 base_*로 보존합니다.

Joint는 두 경로 모두 J(t)={동일 model·origin의 H1/2/3이 발행되고 모두 관측·공표·fit 조건을 충족}의 최근60개, 최소24개입니다. 가격은 `current_point_h × historical_actual_h / historical_point_h`입니다. 구간 crossing만으로 유효한 point-error vector를 제외하지 않습니다. 그런 필터를 새로 넣으면 별개의 방법론 변경입니다.

## 합성 반례

새 [감사 코드](../scripts/day14/audit.py)는 기존 OOFPool.release/calibrate, SequentialOOF.tick/calibrate/scenarios, SavedOOFForecasts 및 Day6 generator를 직접 호출합니다. 임의 생성한 실제 가격은 없으며 모든 값은 명시적 toy입니다. Toy point100·raw[90,110], actual=120+2015-01 기준 월 index입니다. IssuedForecast의 native tag는 기존 API를 통과하기 위한 **수동 toy envelope**이며 `toy_manual_no_fit` proof/events가 붙습니다. native fit 증거로 사용하지 않습니다. 실제 native 증거는 기존 Day12 합성 저장물만 사용합니다.

| 경우 | Day5 허용 잔차 | Day12 허용 잔차 / 결과 |
|---|---|---|
| o=2020-01, t=2020-03 | H1 | 없음 |
| t=2020-04 | H1/H2 | 없음 |
| t=2020-05 | H1/H2/H3 | 전체 |
| H3 공표=d_t+1초 | H1/H2 | 없음 |
| H3 공표=d_t 정확히 | 전체 | 전체 |
| H1만 늦게 공표 | H2/H3 | 없음 |
| 완전23개 | 각23, raw fallback | 동일; Joint도 부족 실패 |
| 완전24개 | 각24, k20 | 동일, 보정 |
| 완전59개 | 각59, k48 | 동일 |
| 완전60개 | 각60, k49 | 동일 |
| 완전61개 | 최초 제외·최근60, k49 | 동일; window 갱신 확인 |
| 완전23+2021-03 H1/H2만 성숙, t=2021-06 | H1/H2 24개, 보정30/31 | 23개라 raw fallback |
| 완전60+같은 부분 성숙 origin | H1/H2 최근60, 보정60/61 | 최근60이지만 보정59/60 |
| 이전 예측 미발행 | 0개 | 0개; 생성·보충 없음 |
| 2개 모델 | 같은 모델24개만 사용 | 동일; 48개로 합치지 않음 |
| H1 crossing인 완전24개 | H1 score0개, H2/H3 24개 | 동일; Joint24개는 유지 |

총16경우×3h=48개 비교입니다. 네 행(H1/H2×두 반례)의 구간 또는 fallback이 달랐습니다. 일곱 경우에서 Day6/12의128경로씩 **896쌍 가격·표집 origin이 일치**했습니다. Pool digest는 직렬화/provenance schema가 달라 일치하지 않습니다. 같은 멤버·비율·draw를 비교하며 hash만으로 수치 불일치를 주장하지 않습니다. 새 구매 결정이나 비용은 계산하지 않았습니다.

## Crossing·Invalid·Fallback 감사

저장된 Day12 합성236batch·708raw행을 다시 읽어 **14개 고유 LightGBM crossing**을 확인했습니다. Historical1·Validation형9·Final형4이며 여기의 Final형은 실제 Holdout이 아닌 합성 달력입니다. 보정348행은335 calibrated·13 raw_invalid_uncalibrated이고 insufficient fallback은0입니다. Historical crossing1개는 당시 current calibration 요청이 없어14와13의 분모가 다릅니다. 348행 모두 point가 raw와 일치합니다.

모든708raw행의 point/quantile/bounds는 유한합니다. Crossing14개는 동일h score 사용0회, 완전 성숙하면 Joint에는 포함됩니다. q10/q50/q90를 재정렬·clip하지 않았습니다. 동일 발행물이 현재 invalid 상태와 후속 pool에서 여러 번 보이는 것을 새 crossing 사건으로 중복 계산하지 않았습니다. `(model,origin,h)`와 immutable issuance SHA로 연결합니다. 상세14행·후속 pool 횟수는 `quantile_crossing_fallback_audit.json`에 있습니다.

**CR-02 발견:** 공용 `interval_usable`은 유한한 lower/upper와 crossing 여부만 검사합니다. q50=NaN이지만 유한한 [90,110]이면 crossing=False, interval_usable=True입니다. 두 calibrator 모두 raw fallback으로 통과시키며 q를 null로 옮긴 뒤 `validity_status=valid`가 될 수 있습니다. 비유한 point도 직접 calibrate 호출에서는 interval_usable=True이고 명시 오류 flag는 유지되지만 구간을 반환합니다. 이는 올바른 입력 계약이라고 승인한 것이 아닙니다. 새 테스트는 **결함의 재현과 ACTION_REQUIRED 기록**을 검증하며 기대값을 “정상”으로 바꾸지 않습니다.

Day12 NativeForecastPublisher는 이보다 강하게 point·quantile·bounds의 finite/positive를 모두 검사하므로 해당 비유한 반례를 발행 전에 거부합니다. 이번 저장물708행에 비유한 값은 없습니다. 따라서 저장된 Day12 native 결과가 이 결함으로 오염됐다고 단정하지 않습니다. 일반 direct API/이후 연결에서 raw point·interval·quantile의 유효성 계약을 분리·통일해야 합니다. 유한 음수 경계는 Day5에서 보존·flag·구간평가 가능하지만 Day12 native ingress는 비양수 경계도 거부합니다. 이것도 원래 사양과 최종 ingress의 우선순위를 명시해야 하는 차이입니다.

Crossing/역전/비유한 경계는 두 calibrator 모두 raw_invalid_uncalibrated로 구간을 비우며, 부족 raw fallback·raw fitting failure·Joint/solver failure와 다릅니다. Fit/Joint/solver에는 숨은 대체가 없습니다. raw crossing에서 개별 유한 quantile Pinball만 별도 분모로 계산할 수 있지만 오늘 성과를 다시 측정하지 않았습니다. 과거 interval score가 invalid면 제외하고, 현재 interval만 invalid면 그 현재 구간 보정은 실패 상태로 유지합니다.

## OOF·Seed·Native 발행 출처

기존 Historical OOF60(2016-04~2021-03)과 Validation36(2021-06~2024-05)은 사후 rolling/as-of 재구성 기록입니다. 그 논리 origin에서 fit정보가 미래를 참조하지 않았다는 proof와 **그 역사적 날짜 당시 실제 운영 발행했다는 증거는 구분**합니다. contemporaneous live issuance는 NOT_VERIFIED입니다. 실가격 seed archive의 새 batch envelope 연결·출처/원래 fit proof 검증도 NOT_VERIFIED입니다.

Day12 합성은 같은60+36 달력과 최종22origin에서 실제 native backend로 계산해 저장한236batch입니다. 이번에는 파일 hash·immutable digest·fit timestamp proof를 검증했을 뿐 다시 fit하지 않았습니다. 120 historical+72 validation형+44 final형batch, 2024-06~08 발행0입니다. Synthetic 논리 발행시각과 실제 계산 wall-clock, 실제 시장 공표시각은 같지 않습니다.

`restore_seed_archive`는 외부 archive hash, 모델별 정확한60+36 달력(총192batch), source/knowledge/backend, fit/발행 proof를 요구합니다. 복원된 과거 session ID를 보존할 수 있지만 현재 발행·Calibration/scenario는 현재 session ID를 검사합니다. 미발행2024-06~08과2021-04~05를 보충하지 않습니다. 원래 archive가 없거나 출처가 맞지 않으면 중단해야 하며 새로운 fit으로 복원했다고 표시할 수 없습니다. 향후 실제 신규 origin fit·공표·source 연결 성공은 이번에 입증하지 않았습니다.

## 최종7정책에 미치는 영향

| 경로 | Calibration 공개 규칙만 바꿀 때 |
|---|---|
| SAR/LGB point, FA 입력 | 불변; q50/L2 교환 없음 |
| Horizon별 보정구간·fallback·해석 | 구성원/최신성/유효 표본 수가 달라져 변경 가능 |
| Joint pool | 둘 다 완전 vector, raw actual/point; 구간 보정과 독립 |
| RN/RA Planning | 같은 raw point·Joint member·ratio·seed라면 같은 가격경로 |
| CVaR | α=.9/λ0,.5·이산 tail 계산 불변; 보정구간의 직접 경로 없음 |
| FA와 RA | 점예측 LP와 경험적 공동 가격 LP 차이; 순수 CVaR 효과는 같은 모델 RA−RN으로만 분리 |
| Validation↔최종 uncertainty 비교 | Day5/12 Calibration은 현재 같은 방법론이 아님 |
| 실제 비용·서비스 결과 | 미평가; 불변 가정하의 입력 경로 분석이지 성과 보장 아님 |

새 validity 필터로 Joint에서 crossing vector를 제외하거나, 보정 interval을 scenario로 변환하거나, 실패 처리를 바꾸면 member/ratio/draw·정책 입력·비용이 달라질 수 있습니다. 그런 변경은 이번에 승인/적용하지 않았습니다. Day11의7정책·calendar22/24·I200·빈pipeline·수요100·업체·말기·metric·α/λ·seed를 모두 보존합니다.

## Methodological Decision Record — 제안만

| 선택지 | 근거·호환성 | 변경·재동결 |
|---|---|---|
| A 권고: Calibration은 horizon별, Joint는 full-vector | Day5 사전 방법론/Day6 시나리오와 일치 | Day12 신규 adapter 분리 필요; 합성 재검증·새 Freeze·새 digest 승인 필요 |
| B: 둘 다 full-vector | Day12 합성 통합과 일치하지만 보정 표본 최신성/추정 대상 변경 | Day5와 같은 방법론으로 부를 수 없음; 변경 명시·재검증·새 Freeze·새 승인 |
| C: 둘을 별도 민감도 사양으로 유지 | 저장 결과는 보존하지만 단일 최종 primary 사양 미정 | 최종 primary를 먼저 정해야 함; 성과를 본 뒤 선택 금지; 새 Freeze/승인 |

CR-01은 Calibration/Joint 공개 분리와 최종 우선순위, CR-02는 raw point/quantile/interval validation 및 비양수 경계 ingress 원칙, CR-03은 실제 seed 출처/변환 연결 검증입니다. 모두 **PROPOSED_NOT_IMPLEMENTED**입니다. 새 승인 요청이나 실제 접근은 시작하지 않았습니다. 기술적 통합의 완료와 최종 통계 계약 확정은 별도이며 기존 freeze를 덮어쓰지 않습니다.
