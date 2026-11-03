# Day 9 실행 기록

2026-10-30 Asia/Seoul. **Day 9 완료 — Historical Price-Based Simulated Procurement Backtest**입니다. World Bank 실제 Validation 가격과 가상 운영조건을 결합한 개발기간 평가이며 실제 기업의 구매 기록·실현 절감 실적·독립 OOS가 아닙니다. 기존 Day0~8 결과·모델·설정·데이터와 Holdout 잠금을 보존했습니다.

## 1. 생성·수정 파일

신규 설정은 `configs/day9.toml`, 사전 명세는 [DAY9_EVALUATION_PROTOCOL](DAY9_EVALUATION_PROTOCOL.md), 테스트는 `tests/test_day9_historical_backtest.py`, 독립 검산기는 `scripts/verify_day9_results.py`입니다. `src/food_procurement_intelligence/` 아래에 다음을 추가했습니다.

- `evaluation/historical_prices.py`: validation-only monthly capability·HistoricalEvaluationWorld
- `evaluation/policy_inputs.py`: 봉인된 point/planning 입력, 모델·origin 검증, 7정책 factory
- `optimization/order_calendar.py`: 기존 GLOP의 Runoff 신규q 상한0 adapter
- `evaluation/policy_backtest.py`: 첫 결정·공개 context·장기 엔진 연결, Active/Runoff·실패·paired 집계
- `evaluation/day9.py`: 고정 사양 검증·실행·산출물·manifest

기존 엔진·Fixed/FA/RA·예측·scenario·LP 구현을 수정하지 않았습니다. README/ROADMAP/AGENTS는 설명만 덧붙이고 이전 바이트 prefix를 보존했습니다. 그 외 기존 **1,331개 파일**의 해시는 같습니다. 새 패키지·데이터 다운로드·모델 재학습·Git commit/push는 없습니다.

## 2. 사전 고정과 해시

실제 구매성과 계산 전2026-10-30T08:59:19.323552Z에 `artifacts/day9/protocol_freeze.json`을 기록했습니다.

- Day9 config SHA-256: `9310a210dd0a12ff68a4b027a96e4d9bcb8f9ccf7377a6d1ea69ccfa7f160d31`
- 평가 프로토콜 SHA-256: `4e0b3588d12cc47822dd122bd29b3f6dea73dd817e23a37ee04201336d3d9a05`
- 기존 Day8 config: `6e0af6fe4e7f8e0fa9afa4dea27f9708b1d46c4f5b37aa29a1efb11f16a42619`
- 기존 split: `209f2a35dea2bc0afc19461b6f780deb61d27b8cf5acaf5a2aaa10e5cd963741`

α=.90, RNλ0/RAλ.50, 동일7정책·달력·초기/말기·외생조건을 고정했습니다. 30개 Toy 검증을 실제 평가 전에 통과했고 이후 Runoff 실패일 보고 경계와 paired fill-rate 산출을 보강했습니다. 이 보강은 정책·제약·기간·비용·성과를 바꾸지 않았습니다. 초기 gate와 점검 run도 보존합니다.

## 3. Active / Runoff / 전체 기간

| 구분 | 날짜 | 개수 |
|---|---|---:|
| 최초 상태·첫 발주 | 2021-06 월말 | 원장에 포함하지 않는 초기 결정 |
| Active Decision Origins | 2021-06~2024-05 | 36 |
| Active Operating Ledger | 2021-07~2024-05 | 35개월 |
| Runoff | 2024-06~2024-08 | 3개월 |
| Full Evaluation Ledger | 2021-07~2024-08 | 38개월 |
| 실제 종료비 귀속 | 2024-08 | 한 번 |

Runoff에 정책/forecast provider를 호출하거나 신규 주문을 넣지 않습니다. 2024-05의 H1/2/3은6/7/8월입니다. 누락된 뒤쪽 forecast를 새로 생성하지 않았습니다. 기존 LP가 계획할 수 있는 k>2024-05의 q는 Day9 adapter에서 상한0으로 막습니다. 이후 확정 pipeline만 수령·수요·비용 정산합니다. Runoff는 고정 forecast 달력을 위한 실험적 종료 규칙입니다.

## 4. 초기·공급·수요·회계

첫 결정 전 재고200t·빈pipeline, 창고400t입니다. A는premium2%·lead2·cap80t, B는8%·lead1·cap100t/월입니다. 계획/실현수요100t/월, 실현 추가delay0, 발주 허용은 최대delay1까지 고려합니다. Seed bank는 결정적 primary 한 경로로 RNG·추가 stress 없이 고정했습니다.

보관3·부족1500·폐기1·말기편차9USD/t, lost sales, 종료목표200t·잔여재고 회수수익0입니다. 초기 재고 취득비는 공통 sunk cost입니다. 실제 매입은 수령월 지수×(1+premium), 운송 별도이며 비용은 수령월 한 번입니다. 계획말기 근사는 실제 원장에 누적하지 않습니다.

기존 엔진은 월 운영 후 정책을 호출하므로 첫6월 주문을 먼저 확정하고7월 시작 엔진에 전달합니다. `initial_pipeline=false`와 `engine_opening_from_first_decision`을 함께 기록해 **첫 결정 직후 pipeline**과 외생 초기 pipeline을 구분합니다. Day6 Toy의 A80/B20 opening을 가져오지 않았습니다. 실제 가격 world는 별도 HistoricalEvaluationWorld이며 synthetic-only ToyWorld로 위장하지 않았습니다.

## 5. 실제 가격 접근 통제

`GuardedValidationPrices`는 기존 validation-only reader에 단일 target ForecastSample을 요청하여38개 고유 월을 한 번씩 취득합니다. 평가 clock은2024-09 선택freeze이고 정책 decision clock과 구분됩니다. Bridge/Holdout/Train target은 이 evaluator capability가 거부합니다. 원본 무결성 검사는 기존 로더 내부에 유지하며 새 코드가 전체 Day1 CSV를 정책 입력으로 읽지 않습니다.

정책은 기존 DecisionContext만 받고 world/evaluator/미래수요/delay/미공표 정산단가를 받지 않습니다. 공개 history는 별도 as-of provider가 채우며 첫 origin의 최신 가격은2021-05입니다. t−1 월 제한과 available_at≤d_t를 모두 유지합니다. Spy/Fake reader, 미래 가격·수요·delay 변경, Holdout100→1e90 합성 변경 테스트가 통과했습니다. 수정된 실제 Holdout 값은 만들거나 읽지 않았습니다.

## 6. 완전성과 입력 재사용

7정책 각각36결정·38원장월, 합계252결정·266원장행입니다. 비용 가격은38개 고유 월이며 겹치는 예측 target을 중복 정산하지 않습니다. SARIMAX/LightGBM 각36개 Planning bundle을 같은 모델의 RN/RA가 동일하게 사용했고, 경로·확률·origin/model/purpose·공표/fit proof·해시를 검사했습니다. 정책마다 재고/pipeline은 독립적으로 상태 전이합니다.

## 7. 정책별 전체 비용

아래 비용은 USD입니다. 모든 정책의 운송·폐기비는0, 실제 말기비는1,800이며 마지막 월 한 번만 계상했습니다.

| 정책 | 매입비 | 보관비 | 부족비 | 말기비 | 총비용 |
|---|---:|---:|---:|---:|---:|
| Fixed | 1,336,441.68 | 13,260.00 | 0 | 1,800 | **1,351,501.68** |
| FA SARIMAX | 1,328,834.16 | 5,280.00 | 30,000 | 1,800 | **1,365,914.16** |
| RN SARIMAX | 1,338,035.76 | 12,660.00 | 0 | 1,800 | **1,352,495.76** |
| RA SARIMAX | 1,335,903.84 | 13,200.00 | 0 | 1,800 | **1,350,903.84** |
| FA LightGBM | 1,326,162.24 | 6,000.00 | 0 | 1,800 | **1,333,962.24** |
| RN LightGBM | 1,326,162.24 | 6,000.00 | 0 | 1,800 | **1,333,962.24** |
| RA LightGBM | 1,335,220.82 | 11,213.38 | 0 | 1,800 | **1,348,234.20** |

FA/RN LightGBM의 이번 총비용은 같았습니다. 이를 강제로 다른 결과로 만들지 않았고 기본 SARIMAX나 모델 사양을 성과에 맞춰 교체하지 않았습니다.

## 8. 서비스·재고·발주

| 정책 | 부족t | Fill Rate | Stockout 월 | 평균말재고t | A/B 총발주t |
|---|---:|---:|---:|---:|---|
| Fixed | 0 | 100% | 0 | 116.3158 | 2880 /720 |
| FA SARIMAX | 20 | 99.4737% | 1 | 46.3158 | 2880 /700 |
| RN SARIMAX | 0 | 100% | 0 | 111.0526 | 2880 /720 |
| RA SARIMAX | 0 | 100% | 0 | 115.7895 | 2880 /720 |
| FA LightGBM | 0 | 100% | 0 | 52.6316 | 2880 /720 |
| RN LightGBM | 0 | 100% | 0 | 52.6316 | 2880 /720 |
| RA LightGBM | 0 | 100% | 0 | 98.3630 | 2559.2592 /1040.7408 |

전체 수요는모두3800t입니다. FA SARIMAX 충족3780t, 나머지3800t입니다. 최종재고와미착pipeline은모두0입니다. 부족20t는전부2024-08의Runoff입니다. 매월 발주·재고·pipeline·실제offset별입고와매입비는 정책별CSV와 `receipt_horizon_audit.csv`에 보존했습니다. 보관·부족 같은 월 운영비를 겹치는 forecast horizon에 중복 배분하지 않습니다.

## 9. Fixed 대비 변화

| 정책 | 총비용 차이 USD | Fixed 대비 % |
|---|---:|---:|
| FA SARIMAX | +14,412.48 | +1.0664% |
| RN SARIMAX | +994.08 | +0.0736% |
| RA SARIMAX | −597.84 | −0.0442% |
| FA LightGBM | −17,539.44 | −1.2978% |
| RN LightGBM | −17,539.44 | −1.2978% |
| RA LightGBM | −3,267.48 | −0.2418% |

음수는 이 시뮬레이션 경로에서 낮은 비용이라는 뜻입니다. 기업 실적·인과효과로 표현하지 않습니다.

## 10. RA 대비 FA — 전체 입력 차이 포함

SARIMAX RA−FA는 **−15,010.32USD(−1.0989%)**, 부족−20t·fill rate+0.5263%p입니다. LightGBM RA−FA는 **+14,271.96USD(+1.0699%)**, 서비스 변화0입니다. Point와 scenario mean 차이도 포함하므로 이를 전부 순수 CVaR 효과로 해석하지 않습니다.

## 11. 같은 Scenario의 위험 목적 추가 효과

SARIMAX RA−RN은 **−1,591.92USD(−0.1177%)**입니다. 매입−2,131.92·보관+540USD이며 두 정책 모두 부족0입니다. 평균재고는111.0526→115.7895t로 늘었습니다.

LightGBM RA−RN은 **+14,271.96USD(+1.0699%)**입니다. 매입+9,058.58·보관+5,213.38USD이며 두 정책 모두부족0입니다. 평균재고는52.6316→98.3630t로 늘었습니다. 따라서 이한경로에서 위험회피목적의 추가효과는 모델에 따라 부호가달랐습니다.

첫 공통 상태 I200·빈pipeline의 계획 진단도 각 rolling_plans 첫 행에 저장했습니다. SARIMAX RN/RA의 E는34,457.74/34,461.47, CVaR는40,270.07/39,774.22USD입니다. LightGBM E는35,650.01/35,696.47, CVaR는42,846.71/42,073.71USD입니다. 계획 tail을낮추면서 E가오를수있고, 이 계획 CVaR를 장기 실현CVaR로 취급하지 않습니다.

## 12. 모델 변경 비교

LightGBM−SARIMAX의 총비용 차이는 FA **−31,951.92USD(−2.3392%)**, RN **−18,533.52USD(−1.3703%)**, RA **−2,669.64USD(−0.1976%)**입니다. FA에서 부족−20t, RN/RA에서는서비스변화0입니다. 모델·예측 입력·모델별 OOF scenario 분포가 함께 달라지므로 알고리즘/특징 하나의 인과효과를 측정한 것이 아닙니다.

## 13. Active / Runoff 영향

| 정책 | Active35개월 비용 | Runoff3개월 비용 | Runoff 부족t |
|---|---:|---:|---:|
| Fixed | 1,300,391.28 | 51,110.40 | 0 |
| FA SARIMAX | 1,261,975.92 | 103,938.24 | 20 |
| RN SARIMAX | 1,301,385.36 | 51,110.40 | 0 |
| RA SARIMAX | 1,299,793.44 | 51,110.40 | 0 |
| FA LightGBM | 1,282,851.84 | 51,110.40 | 0 |
| RN LightGBM | 1,282,851.84 | 51,110.40 | 0 |
| RA LightGBM | 1,303,035.72 | 45,198.48 | 0 |

Active의모든정책부족0입니다. FA SARIMAX의Active비용만보면Fixed보다38,415.36USD낮지만5월말재고는20t 대120t였고, Runoff비용은52,827.84USD높았습니다. Active절감만보고운영우월성을주장하지않습니다. 정책별종료상태가다르므로두기간은상태이월을함께해석해야합니다.

## 14. 실패·누락·Solver

실제 실행은 누락 forecast/scenario0, as-of 실패0, solver 실패0·fallback0,6최적화정책각36=**216 OPTIMAL**입니다. Fixed는36결정, 전체정책의Runoff무발주합계21회입니다. 모든 solution은 VerifySolution·기존물리/greedy검사·calendar·비용·CVaR검사를통과했습니다. 실제주문수치정규화량0t입니다.

최대수량위반5.68e−14t, epigraph위반2.91e−11USD, 목적값재구성차이5.82e−11USD입니다. 기존 GLOP9.14.6206·primal/dual1e−8·수량1e−7·비용abs1e−4/rel1e−8를유지했습니다.

실패테스트는첫실패시점·공통확인가능prefix·완료정책과미실행범위·partial결정로그를남기고완전성과비교를차단합니다. 기존엔진이실패시원자적으로중단하므로실패정책의부분비용원장은반환되지않으며이를추정해만들지않습니다. 보존한결정로그와보수적인확인기간만보고하고실패월을건너뛰거나Fixed로대체하지않습니다. Runoff최종엔진실패는마지막Activeorigin으로오표기하지않도록추가검증했습니다.

## 15. 자동·독립 검증

신규 **31 passed, 3 warnings in1.23s**, 최종 전체 **295 passed, 3 warnings in103.05s**, exit0입니다. 기존 Day0~8 테스트264개를 모두 포함합니다. 경고3개는 OR-Tools SWIG의 `__module__` deprecation이며 solver 실패가 아닙니다. 실제 World Bank 가격은 pytest fixture에 넣지 않았고 실제 연결 실행과 분리했습니다.

독립검산기는solver/정책/엔진코드를호출하지않고, 기존독립Day8산술을재사용해216개계획과38개월별입고·발주capacity/lead·재고보존·greedy출고·lost sales·수령월단가·비용구성·말기단일계상을재계산했습니다. 실제가격은원천CSV에서날짜필터후Validation38개만숫자로해석해대조했습니다. 418개paired월행·396개paired발주행, 동일모델RN/RA scenario동일성, 기간별집계도검증합니다.

## 16. 산출물·재현·보존

최종run은 `artifacts/day9/20261030T090528446877Z/`, 반복run은 `artifacts/day9/20261030T090555925506Z/`입니다. 가상운영입력은같은ID의 `data/synthetic/day9/`에있습니다. 앞선두점검run도보존했습니다. 두최종run의독립검산이통과했고 **269개 결정적 파일**이 가상입력까지 바이트동일합니다. 기존1,331개파일·문서3개원문prefix보존을확인했습니다. 검증보고서는 `artifacts/day9/verification_20261030T090528446877Z_repeat.json`과 `verification_20261030T090555925506Z.json`입니다.

주요파일은 `evaluation_prices.csv`, `evaluation_reader_audit.json`, `input_availability_audit.json`, 정책별 `decision_audit/rolling_plans/runoff/ledger/orders/receipts`,216개LP, `policy_metrics.json/csv`, `paired_monthly.csv`, `paired_summary.json`, `paired_decision_orders.csv`, `receipt_horizon_audit.csv`, `completeness.json`, `solver_timing.json`, `spec_freeze.json`, `manifest.json`입니다. Manifest는원본/설정/split/모델/scenario/Day8/gate/프로토콜/코드/solver binary/환경/출력해시를연결합니다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_day9_historical_backtest.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m food_procurement_intelligence.evaluation.day9 --config configs/day9.toml
.\.venv\Scripts\python.exe scripts/verify_day9_results.py --run artifacts/day9/20261030T090528446877Z --repeat artifacts/day9/20261030T090555925506Z
```

재실행은새run폴더에만저장합니다. Solver시간·생성시각·manifest는바이트동일성대상에서제외합니다. 초기사양과Day0~8산출물은보존합니다.

## 17. 해석상 한계와 결론

같은Validation에서SARIMAX를이미선택했으므로개발·선택편향이있습니다. 한역사적가격경로와가상운영조건의탐색적결과이며독립Holdout검증이아닙니다. 월별38개차이는lead·재고에의존하므로독립표본으로보거나유의확률/신뢰구간을계산하지않았습니다. 시장가격CVaR도추정하지않았습니다.

Day5 coverage미달,검증되지않은OOF bootstrap확률/tail,최신수정snapshot·가정공표시각·2020정의변경·결정적수요/납기·폐기0보수성·3개월말기근사·Runoff가정이남습니다. 위험회피가서비스를자동개선하거나모든가격경로에서총비용을줄인다고주장하지않습니다.

질문의답: **가격예측기반정책은Fixed보다재고를줄였지만, SARIMAX FA는Runoff부족으로전체비용이1.0664%높았고 LightGBM FA는서비스100%를유지하며비용이1.2978%낮았습니다. 같은scenario에서λ0→.5의추가효과는 SARIMAX에서비용−1,591.92USD·재고증가, LightGBM에서비용+14,271.96USD·재고증가였으며두모델모두서비스변화0이었습니다.** 위험목적의추가효과와point/scenario·모델변경효과를분리해서해석해야합니다. 이는실제기업의절감실적이나일반화보장이아닙니다.

## 18. Day 10 사전 설계 과제 — 미실행

별도지시후초기재고100/200/300t, 말기편차계수0/9/30·종료목표·Runoff길이·계획horizon, 보관/부족비·업체premium/capacity/lead, 공통수요/delay stress,1/2개월공표지연등을사전정의grid로잠가야합니다. 지원되는예측달력과가용한horizon을확인하고,추가forecast가없으면3/6개월또는지연2개월분석을지원한다고가정하지않습니다.

외생경로는정책호출전생성·공유하고seed bank·실패/불완전비교·paired지표·종료재고상태를고정합니다. 좋은셀만선택하지않고전부보고하며,같은시나리오λ0/.5·모델변경·운영가정을분리합니다. 누적PlanningCVaR를실현CVaR로쓰지않고Holdout잠금을유지합니다. **Day 10은시작하지않았습니다.**
