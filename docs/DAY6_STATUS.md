# Day 6 실행 기록

2026-10-29 Asia/Seoul. **Day 6 완료**. 공동 가격 경로 생성·가용성 검증, 가상 계약, 월별 재고·비용 엔진과 Fixed 정책의 Toy 검산을 구현했습니다. 실제 Validation 구매 성과 비교·Holdout·최적화는 실행하지 않았습니다. Day 7은 미착수입니다.

## 1. 생성·수정 파일

신규 파일:

- `configs/day6.toml`: 방법·표본 수·두 seed·fallback·가상 운영조건의 사전 사양
- `uncertainty/joint_scenarios.py`: 공동 OOF vector, 저장 예측의 as-of view, 공동 bootstrap과 진단, planning-only 소비 경계
- `simulation/contracts.py`: Supplier·수량/단위·ToyWorld·공개 DecisionContext
- `simulation/engine.py`: 입고·수요·폐기·발주·미착 이월·비용 ledger
- `simulation/toy.py`: 명시적 Toy 입력과 실행 전 손계산 기준
- `simulation/__init__.py`, `policies/__init__.py`, `policies/fixed.py`
- `evaluation/day6.py`: Day 5 해시 확인, 시나리오 생성, Toy 실행, 새 산출물·manifest
- `tests/test_day6_scenarios_simulation.py`, `scripts/verify_day6_results.py`
- `docs/DAY6_DESIGN.md`, 본 문서

모듈 경로는 `src/food_procurement_intelligence/` 기준입니다. README·ROADMAP·PROJECT_CHARTER·SIMULATION_ASSUMPTIONS·DATA_DICTIONARY·DECISION_TIMELINE·EVALUATION_PROTOCOL·AGENTS에 새 단계의 구현 범위와 경계를 추가했습니다. 기존 Day 0~5 코드·테스트·설정·스크립트·원본/가공 데이터·결과 **203개 파일**은 해시가 그대로입니다.

## 2. 고정된 공동 경로 방식

사전 설계는 [DAY6_DESIGN](DAY6_DESIGN.md)입니다. config SHA-256은 `fe12d7be4ea4a7d6944a7c5e8874a5d6c683ac893fcf28cae97de33179d8aea9`입니다. Day 5 manifest SHA `18fb0a878adec27ea77197782653d32191ab8ed63804905c4c59a7e76d8b70a1`과 기존 split·모델·calibration을 고정했습니다.

`P*_(t,h)=point_(t,h)×actual_(o,h)/point_(o,h)`로 같은 과거 origin o의 세 비율을 함께 표집합니다. SARIMAX가 기본, LightGBM은 기존 L2 point 기반의 별도 대체 후보입니다. q10/q50/q90나 보정 구간을 분포로 바꾸지 않습니다. Additive는 같은 draw에서 `point_t+(actual_o−point_o)`를 진단했으며 방법 선택을 바꾸지 않았습니다. 실제 생성에서 두 방식 모두 invalid0이었고, 음수가 가능한 Additive는 별도 Toy에서 실패 진단을 검증했습니다.

각 모델의 point 잔차·양수 비율·재표집 비율·생성 가격의 평균/분산/공분산/상관을 저장합니다. 분산은 경험적 분포의 divisor n입니다. 같은 비율을 양수 상수로 h별 변환하므로 표집된 ratio의 Pearson 상관과 가격 상관은 같지만, 유한 재표집의 상관이 pool의 상관과 정확히 같을 필요는 없습니다. Signed USD 잔차와 비율의 상관도 서로 다를 수 있습니다. 평균을 point에 강제로 일치시키는 recentering은 하지 않았습니다.

## 3. OOF 벡터 가용성

Day 5의 실제값 없는 `all_oof_forecasts.csv`에서 point/fit proof를 읽습니다. 실제값은 현재 t의 guarded history에서만 재구성합니다. 동일 모델·origin·source method와 H1/H2/H3 정합성, `o+3<=t−1`, 세 실제 공표 timestamp<=d_t, fit 당시 label cutoff/publication, target의 Train/Validation 소속을 모두 검사합니다. Raw CSV나 validation 정답 reader를 생성기에 전달하지 않습니다.

최초2021-06의 공동 vector는 모델별**59개**, 마지막 origin2021-02까지입니다. 2021-03 origin의 H3 target2021-06이 미공표라 전체 vector를 제외했습니다. 개별h 보정의60/60/59와 다릅니다. 다음2021-07에는 Historical60개가 모두 성숙합니다. 마지막2024-05에는 window 적용 전92개(역사60+validation32), 최근60개만 사용합니다. 모델·시점별 pool72개, 저장한 window별 vector record는4,318개이며 반복 등장하는 vector를 독립 표본4,318개로 세지 않습니다. 최소24개 부족 fallback은 실행0회, Toy에서 명시적 실패를 확인했습니다.

## 4. 수·가중치·품질 진단

36 origins ×2 models ×2 purposes =**144세트**, 각128개3개월 경로, 합계**18,432경로 /55,296가격 행**입니다. 각 경로 가중치는1/128, 세트별 합은 정확히1입니다. 3개h 행에 같은 경로 확률을 반복 표기하므로 CSV 전체의 probability 열을 합산하면 안 됩니다. 확률 질량의 단위는 scenario_id 하나입니다.

비양수·비유한 경로0, duplicate ID0이며 개별 draw의 h마다 같은 source origin을 쓰는 것을 독립 검산했습니다. 전체 생성 최소가격은 SARIMAX196.9040 /LightGBM206.2258 USD/t입니다. 이는 실제 target 가격의 최솟값이나 미래 가격의 하한 보장이 아닙니다.

첫2021-06 planning 세트의 예시:

| 모델 | H1/H2/H3 평균 USD/t | H1/H2/H3 분산 (USD/t)² | 상관 H1-H2 /H1-H3 /H2-H3 |
|---|---|---|---|
| SARIMAX | 308.0318 /310.6370 /314.2331 | 547.9211 /907.4653 /1426.6041 | .8384 /.7400 /.9008 |
| LightGBM | 305.5229 /325.8666 /345.9638 | 929.3585 /1810.8900 /2412.4721 | .8750 /.8093 /.9041 |

144세트 전체 수치는 `scenario_diagnostics.json`에 있습니다. 진단은 가격 경로의 산술·형태 검사이며 실제 target을 이용한 확률예측 성능 평가가 아닙니다.

## 5. Planning / Evaluation 분리

Base seed는 planning2026102901, evaluation2026102902입니다. origin/model/purpose별 SHA-256으로 파생 seed를 만들고 새 `random.Random`을 명시적으로 전달합니다. 전역 RNG를 바꾸지 않으며 정책 호출 횟수와 생성 순서에 의존하지 않습니다. ID namespace가 서로 다르고, `ScenarioSet.for_policy`는 evaluation 세트나 다른 origin의 세트를 거부합니다. Fixed 정책의 DecisionContext에는 evaluation 경로·seed가 없습니다.

같은 empirical OOF pool을 사용하므로 서로 다른 seed를 통계적 독립성이나 OOS 증거로 해석하지 않습니다. 진정한 OOS/별도 stress 평가 설계는 후속 단계입니다.

## 6~7. 가상 공급·수요·재고 가정

| 항목 | A | B |
|---|---:|---:|
| premium | 2% | 8% |
| lead | 2개월 | 1개월 |
| 월 발주 capacity | 80t | 100t |
| MOQ /multiple | 0 /0 — 연속 물량 | 0 /0 — 연속 물량 |
| 기본 /최대 추가 delay | 0 /1개월 | 0 /1개월 |
| 운송비 USD/t | 0 | 0 |
| Fixed 월 배분 | 80t | 20t |

계획 수요100t/월, 초기 재고200t, 창고400t, Lost Sales, 보관3 USD/t/월·부족1500 USD/t·폐기1 USD/t·종료편차9 USD/t입니다. 확률 지연/수요 추첨은 구현하지 않았습니다. Toy2000-01~06에서 초기 미수령 발주 A80/B20을 명시적으로 입력했습니다. 향후 정책 비교의 빈 pipeline 기본값과 구분합니다. 모든 입력은 `data/synthetic/day6/<run>/`에 가상 자료로 저장합니다.

## 8. Ledger와 회계

월초 입고 → 수요 충족 → Lost Sales·초과폐기 → 월말 비용 귀속 → 공개 상태로 정책 결정 → 발주·미착 이월 순서입니다. 재고와 pipeline 수량 보존을 매월 검사합니다. 실제 도착월은 k+lead+외생delay이며 정책에는 promised·overdue 상태만 보입니다.

단가는 실제 수령월 index×(1+premium), 매입비는 입고분을 해당 월 말에 한 번만 귀속합니다. 초기 재고는 sunk cost, 초기 pipeline은 도착할 때 비용에 포함합니다. 해당 월 가격은 다음 달 공표되므로 현재 정책에 매입단가·비용을 노출하지 않습니다. 보관비는 월말 재고, 부족비는 해당 월 unmet에 한 번, 총비용은 매입+운송+보관+부족+폐기+최종월 종료비입니다. Backorder는 없습니다.

신규 발주는 최대 delay까지 고려해 창 안 도착할 수 있어야 하고, 마지막 미착0을 요구합니다. 위반하는 사용자 발주나 초기 pipeline은 오류입니다. 종료재고 회수수익0,9×|I_T−200|는 최종월 한 번입니다. 아직 입고되지 않은 발주를 재고로 쓰거나 창 밖 비용을 숨기지 않습니다.

## 9~10. Fixed Toy 실행·손계산 검산

모든 사례에서 신규 발주량은100/100/100/20/0/0t, 초기 pipeline 포함 총입고420t입니다. 창 밖 도착 가능성이 있는 업체 발주는 생략하며 다른 업체로 재배분하지 않았습니다.

| Case | 매입비 USD | 보관비 | 부족t /부족비 | 종료비 | 총비용 USD |
|---|---:|---:|---:|---:|---:|
| A 정상 | 43,440 | 1,860 | 0 /0 | 1,620 | **46,920** |
| B 지연 | 43,440 | 1,620 | 0 /0 | 1,620 | **46,680** |
| C 수요 급증 | 43,440 | 720 | 180 /270,000 | 1,800 | **315,960** |
| D 가격 상승 | 69,240 | 1,860 | 0 /0 | 1,620 | **72,720** |
| E 복합 | 73,320 | 1,200 | 180 /270,000 | 1,800 | **346,320** |

A의 월말 재고는120/120/120/120/120/20t입니다. B는3월 도착 A80t가4월로 이동하고, 버퍼가 있어 부족0입니다. 별도 무버퍼 테스트는 지연으로 첫 두 달 부족80/20t를 검증합니다. C는3월 수요300t로 부족80t, 종료월100t; E는3월160t, 종료월20t입니다. C/E의 총부족이 같은 것은 총가용620t·총수요800t가 같고 창 안에 지연분이 도착했기 때문입니다.

D는 가격만 변경했고 Fixed 발주·재고는 A와 같습니다. E에서는 A의1월 발주80t가3월150달러 대신4월200달러 지수로 정산되어 매입비가D보다4,080달러 커졌습니다. 이는 단가 계약 검산이며 가격과 납기의 확률적 상관을 추정했다는 뜻이 아닙니다. B의 낮은 보관비도 실제 기업 절감이나 정책 우월성 주장이 아닙니다.

## 11. 테스트와 독립 검증

신규 **31 passed in1.16s**, 최종 전체 **173 passed in85.45s**, exit0입니다. 기존142개를 모두 포함합니다. Toy 데이터만 사용하며 네트워크가 필요하지 않습니다.

검증 범위는 공동 vector 정렬·전h 성숙·실제 지연 timestamp·OOF fit proof·미래 source point poison·36개 origin 전체 Holdout 변경 불변성·양수/비유한/확률합·동일 draw 의존성·seed/ID/정책 경계·capacity/MOQ/lot·lead·재고/pipeline 보존·미착 지연·lost sales·단가·단일 비용 계상·말기 처리·5개 손계산·동일 외생 경로 재현입니다.

독립 스크립트는 실제 저장 시나리오의 source draw를 seed로 다시 찾고 수식·확률합·모든 moment·공표/학습 proof를 확인했습니다. 각 Toy의 주문·입고·월별 수량/비용을 별도 산술과 사전 손계산 값으로 검산해 passed입니다. 실제 OOF 통합 검증은 pytest Toy fixture와 분리했습니다.

## 12. 무결성·반복 재현·산출물

최종 run: `artifacts/day6/20261029T014002057377Z/`.
반복 run: `artifacts/day6/20261029T014040768236Z/`.
가상 입력: 각각의 같은 run ID 아래 `data/synthetic/day6/`입니다.

```text
spec_freeze.json, manifest.json
joint_price_scenarios.csv, joint_oof_vectors.json
availability_audit.json, scenario_diagnostics.json
A_normal / B_delay / C_demand_spike / D_price_rise / E_combined:
  *_ledger.csv, *_orders.csv, *_receipts.csv
toy_cost_breakdown.json, hand_calculation_expectations.json
data/synthetic/day6/<run>/supplier_assumptions.json, toy_worlds.json
```

두 run의 코드·설정 해시가 같고 **23개 결정적 파일**(가상 입력2개 포함)이 바이트 동일했습니다. 각 run의 독립 검산도 passed이며 기존203개 파일 해시는 유지했습니다. Manifest에는 Day 5 연결·원본/가공 해시·split·설정 사본·코드 해시·Python/RNG·각 출력 해시를 남겼습니다. 모델은 재학습하지 않았고 새 패키지·외부 데이터 다운로드는 없습니다. 기존 `.venv` Python3.11.5와 표준 라이브러리를 사용했습니다.

검증 보고서:

- `artifacts/day6/verification_20261029T014002057377Z.json`
- `artifacts/day6/verification_20261029T014002057377Z_repeat.json`
- `artifacts/day6/verification_20261029T014040768236Z.json`
- 기존 파일 목록: `artifacts/day6/preservation_before.json`

최초 점검 run `20261029T013633837773Z`도 보존했습니다. Planning-only 소비 경계를 추가한 뒤 위 두 최종 run을 검증했습니다. 이 경계 보강은 설정·생성식·시나리오·비용 조정이 아닙니다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_day6_scenarios_simulation.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m food_procurement_intelligence.evaluation.day6 --config configs/day6.toml
.\.venv\Scripts\python.exe scripts/verify_day6_results.py --run artifacts/day6/20261029T014002057377Z --repeat artifacts/day6/20261029T014040768236Z
```

각 실행은 새 폴더를 생성합니다. 검증 JSON도 덮어쓰지 않으므로 다시 실행할 때는 새 run의 경로를 전달합니다.

## 13. 남은 한계

공동 경로는 공개된 과거 OOF 구조를 이용한 경험적 시뮬레이션이며 확률적으로 검증된 미래 시장가격 분포가 아닙니다. Day 5의80% 보장도 없고 이번에 그 Coverage를 재조정하지 않았습니다. 작은·겹치는 target의 pool, 시계열 의존성, 장기 nominal 수준/정의 변경, 사후 수정본과 가정 공표시각이 남습니다. 완전 vector 내부 의존성만 함께 재표집하며 origin 간 장기 시간 순서나 서로 다른 결정 월의 경로 일관성은 보장하지 않습니다. 새로운 tail을 학습하지도 않습니다.

공급업체·비용·Toy 수요는 실제 기업 자료가 아닙니다. 확률 수요·납기·가격-납기 상관 추정, 실제 Validation 구매 성과, 서비스 수준·위험 제약 보장, 최적화 성과·비용절감은 검증하지 않았습니다. Seed 분리만으로 독립/OOS라고 주장하지 않습니다.

## 14. Day 7 다음 작업 — 미착수

1. Fixed와 공유할 초기 재고·빈 pipeline 또는 명시적 warm start, 기간·단위·말기·실패 규칙을 다시 고정합니다. Toy의 초기 pipeline을 몰래 정책 비교에 채택하지 않습니다.
2. 알려진 가격 point/수요 계획/현재 재고/pipeline만 받는 rolling-horizon LP 입력과 수량·capacity·lead·재고·부족·종료 제약을 수식으로 확정합니다. 현재 t의 발주만 실행하고 미래 계획은 확정 주문으로 처리하지 않습니다.
3. Solver 설치·버전·상태·infeasible/실패 fallback 규칙을 해당 단계 지시 안에서 확정하고 작은 손계산 LP부터 검증합니다. 실제 미래 가격·수요·납기를 optimizer에 전달하지 않습니다.
4. 승인된 범위에서 Forecast-Aware를 추가하고 동일 외생 경로의 Fixed와 수량·비용을 비교합니다. Risk-Aware/CVaR·실제 Validation 정책 평가·Holdout은 별도 단계입니다.

오늘 OR-Tools·Forecast-Aware·Risk-Aware·실제 정책 성과 비교·대시보드·Git commit/push는 수행하지 않았습니다.
