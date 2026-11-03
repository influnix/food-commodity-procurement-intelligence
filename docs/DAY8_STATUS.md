# Day 8 실행 기록

2026-10-30 Asia/Seoul. **Day 8 완료**. Scenario-Based GLOP, CVaR, 비예견성 검증, Risk-Aware 정책, 동일 Synthetic Toy의 3정책 비교와 저장 Planning Scenario 연결을 구현하고 전체 테스트·독립 검산·반복 재현을 확인했습니다. 실제 Validation 구매평가와 Holdout은 수행하지 않았습니다. 수학적 사양은 [사전 명세](DAY8_CVAR_SPEC.md)입니다.

## 1. 생성·수정 파일

신규 파일은 `configs/day8.toml`, 본 문서와 `docs/DAY8_CVAR_SPEC.md`, `tests/test_day8_risk_optimization.py`, `scripts/verify_day8_results.py`입니다. 패키지 `src/food_procurement_intelligence/` 아래에 다음을 추가했습니다.

- `optimization/scenario_lp.py`: 가중 기대비용·CVaR·공유 물리 LP, 비용 재구성, 비예견성 validator
- `optimization/scenario_adapter.py`: 해시 연결된 planning-only adapter·OOF 공표/fit proof 검사
- `optimization/toy_cvar.py`: 6개 손계산·사전 고정 synthetic planning generator
- `policies/risk_aware.py`: 현재 주문만 실행하는 별도 정책
- `evaluation/day8.py`: 범위·보존 검사, 손계산, Toy 비교, 실제 저장 시나리오 계획 smoke, manifest

README·ROADMAP·AGENTS에는 Day 8 설명을 덧붙였으며 기존 바이트 prefix를 보존했습니다. 그 외 Day 0~7 코드·테스트·설정·데이터·아티팩트·문서·lock·pyproject **652개 파일**은 해시가 같습니다. 기존 Day 6 엔진·Fixed·Day 7 LP/Forecast-Aware를 수정하지 않았습니다.

## 2. CVaR 목적함수와 사전 설정

α=.90, λ=.50으로 `configs/day8.toml`에 고정했습니다. 해시: `6e0af6fe4e7f8e0fa9afa4dea27f9708b1d46c4f5b37aa29a1efb11f16a42619`. 목적함수는 `(1−λ)ΣpωCω + λ[η+Σpωξω/(1−α)]`, 제약은 `ξω≥Cω−η`, `ξω≥0`입니다. 두 항은 모두 USD입니다. η는 VaR 보조 자유변수이며 독립 계산하는 최소 누적분위 VaR와 최적 η가 반드시 유일하게 같아야 하는 것은 아닙니다.

독립 CVaR는 상위10% 확률질량을 적분하며 경계 원자를 일부만 사용합니다. 128개 동일 가중치에서는 12.8개 경로에 해당하므로 임의로13개 전체를 평균 내지 않습니다. 독립 검산기는 원시 비용을 가능한 η 후보별로 열거한 Rockafellar–Uryasev 표현의 최솟값을 사용해 다른 산술 경로로 검증합니다.

λ=0/1은 경계 검증만 했습니다. λ=0에서는 η/ξ의 최소성이 식별되지 않으므로 raw 값과 `eta_identified_by_objective=false`를 남기고, 반환 VaR/CVaR는 독립 비용 분포 값입니다. λ>0은 solver epigraph CVaR가 독립 값과 일치해야 실행합니다. 사후 λ·α 튜닝은 없습니다.

## 3. Scenario LP·물리 제약

Day 7 `build_problem`과 `inspect_solution`을 재사용합니다. 공유 신규 q(s,k), I/U/R/W, 말기 z+/z−를 두고 가격에만 시나리오 차원을 둡니다. 신규 capacity에서 이미 확정된 같은 업체/발주월 cohort를 차감합니다. 명목 lead로 예상수령월을 계산하며, 최대 delay를 포함해 계획창 안 도착하는 신규 주문만 허용합니다. 기존 pipeline은 상수 입고, overdue는 다음 달 예상, 창 밖은 deferred입니다. 글로벌 종료 뒤 미입고는 허용하지 않습니다.

재고 보존·창고 상한·부족 범위·비음수·말기편차와 `W=0`을 유지합니다. 강제 overflow가 제한 LP에서 infeasible인 것은 엔진 자체의 불가능성을 뜻하지 않습니다. 실제 엔진의 greedy service/overflow 폐기는 그대로이며 LP 해도 같은 수식으로 검사합니다. 계획말기 비용과 실제 전체 최종월 종료비를 구분합니다.

## 4. Non-Anticipativity

현재 주문뿐 아니라 미래 계획 q와 모든 물리 흐름이 하나의 변수를 공유합니다. 시나리오별 q/재고 변수가 **0개**이며 형태 검사에서 scenario-indexed 값·추가 그룹을 거부합니다. 128개 실제 연결 문제는 공유 물리20개+η1개+ξ128개=**149변수, 135제약**입니다. 완전한 적응형 다단계 확률 프로그램은 아닙니다.

현재 q만 OrderRequest로 실행하고 미래 q는 로그에만 남깁니다. 다음 달 공개 context·새 planning으로 재최적화하며 현재/역순 origin 재실행은 거부합니다. 실제 미래 가격·수요·지연을 바꿔도 충격 이전 첫 두 결정이 동일했습니다. 미공표 현재가격과 공표가 늦은 과거가격은 DecisionContext가 차단합니다.

## 5. 확률·가격·출처 연결

Day 6 run `artifacts/day6/20261029T014002057377Z/`의 manifest SHA `f567e750796ace1ef716704cca1ca1b127e1b797eb04bb2697aecdd63b97872b`를 고정했습니다. CSV/OOF pool 해시·동일 model/origin/purpose/seed/method/unit·h=1/2/3와 target·양수 유한 가격·중복·확률합1·경로 가중치1/128·draw ID를 검사합니다. 같은 경로의 3개 가격 행에 반복된 probability는 한 번만 계산합니다.

선택 pool의 모든 vector는 o+3≤t−1, 세 공표시각≤d_t, 과거 fit cutoff/공표시각≤d_o, Train/Validation target을 통과해야 합니다. 요청하지 않은 pool의 가격 숫자는 문자열로 유지하고, 해당 origin의 성숙 proof를 확인한 뒤 필요한 hash용 값만 숫자로 해석합니다. 정책에는 해당 Planning ScenarioSet만 전달합니다. Evaluation set·다른 origin·Holdout은 거부합니다. 실제 정답 reader·전체 Day 1 CSV를 solver/정책에 전달하지 않습니다.

## 6. Solver·실패·수치

기존 `.venv` Python3.11.5 / OR-Tools9.14.6206 / `Glop solver v9.14.6206`을 사용했습니다. 신규 설치·기존 패키지 변경은 없습니다. `requirements/day7-lock.txt`도 보존했습니다.

손계산6+경계검증4+동일 평균가격 Day7 비교2+Toy FA25/RA25+실제 scenario smoke4=**66 OPTIMAL**, 최종월 무발주10개=TERMINAL_NO_ACTION입니다. 실패·fallback0입니다. 모든 실행 해는 VerifySolution·회계·비예견성·시나리오 비용·기대비용·CVaR 검사를 통과했습니다. FEASIBLE/INFEASIBLE/UNBOUNDED/ABNORMAL/MODEL_INVALID/NOT_SOLVED/미지 status·backend 없음·VerifySolution 실패는 테스트에서 실행 거부를 확인했습니다.

Primal/dual1e−8, 수량1e−7t, 비용 abs1e−4USD/rel1e−8, 시간제한10초입니다. 관측한 최대 수량 위반2.84e−14t, epigraph 위반2.05e−12USD, 목적값 재구성 차이1.46e−11USD입니다. 실제 RA 주문 정규화량은0t였습니다. LP 원문·원시 해·η/ξ·변수/제약 수·각 검증·상태·시간을 저장했습니다. GLOP의 지원되지 않는 thread 설정을 추가하지 않았습니다.

## 7. 손계산 결과

| 사례 | E 비용 | VaR90 | CVaR90 | 혼합 목적 USD |
|---|---:|---:|---:|---:|
| A 동일128경로 | 80 | 80 | 80 | 80 |
| B 고비용 tail | 190 | 100 | 1,000 | 595 |
| C 업체·수령시점 trade-off | 250 | 250 | 250 | 250 |
| D lead/capacity | 220 | 220 | 220 | 220 |
| E 공급 부족 | 6,060 | 6,080 | 6,080 | 6,070 |
| F 비예견성 | 250 | 250 | 250 | 250 |

A는q8, B는q10, C/F는현재B20/A0, D는현재A10/B10, E는q4/부족6t입니다. C의λ0은현재A10/B10, E240/CVaR420/목적240으로 같은 평균가격 Day7 LP와 일치했습니다. λ1은CVaR250과 목적250이 일치했습니다. 모든 경로가 같을 때 Day7/Day8 목적값은 같으며 비유일한 해의 주문량 일치를 강요하지 않습니다.

F에서 미래 시나리오를 아는 불법 현재주문은 정상 A10/B10(220), tail A0/B20(250)로 E223/CVaR250/목적236.5입니다. 공유 주문만 허용한250보다 낮지만 실제 허용 해가 아니며 형태 검사가 차단했습니다.

## 8. 동일 Synthetic Toy 총비용

세 정책 모두 초기재고200t·빈pipeline, 동일 A~E world·수요·발주 cohort별 실제 지연·계약·기간·말기 회계입니다. FA belief는 기존100USD/t입니다. RA planning은 world/Validation을 읽지 않는 별도 generator로 비교 전에 모든 origin의128경로를 저장했습니다. 96×(100,100,100),24×(90,120,140),8×(100,200,300), 각1/128이며 seed2026103008에서 origin별 순열을 파생합니다. 경험적 시장 확률 추정값이 아닙니다. H별 평균98.125/110/120으로 FA point100과 다릅니다.

| Toy | Fixed USD | Forecast-Aware USD | Risk-Aware USD |
|---|---:|---:|---:|
| A 정상 | 155,460 | 44,340 | **46,440** |
| B 지연 | 155,760 | 127,920 | 46,200 |
| C 수요 급증 | 455,280 | 316,440 | 94,320 |
| D 가격 상승 | 181,260 | 78,780 | 68,760 |
| E 복합 | 485,640 | 459,960 | 242,640 |

정상에서는 RA가FA보다2,100USD 비쌌습니다. 결과를 보고 generator·risk weight를 바꾸지 않았습니다. 더 이른 수령·비싼 B 배분은 보관/매입비를 늘릴 수 있습니다. 다른 Toy의 부족 감소는 합성 가격 시나리오 아래 선택한 재고가 실제 충격을 완충한 결과이며 수요/지연 확률을 학습하거나 예측했다는 뜻이 아닙니다.

## 9. 공통 상태의 계획 E/CVaR

2000-01 결정 직전 I100·빈pipeline에서 두 정책의 **계획 전체**를 같은 RA 세트로 다시 가격 계산했습니다.

| 계획 | 기대비용 USD | VaR90 | CVaR90 | λ=.5 목적 |
|---|---:|---:|---:|---:|
| Forecast-Aware 계획 | 25,135.50 | 26,856 | 36,471 | 30,803.25 |
| Risk-Aware 계획 | 24,349.50 | 24,504 | 30,339 | 27,344.25 |

같은 상태·세트의 수식 진단입니다. 월별 목적값을 누적한 실현 총비용/CVaR가 아니며 이 계획을 그대로3개월 확정 실행하지 않습니다. A~E는 확률분포를 부여하지 않은 스트레스 world라 5개 총비용의 평균을 시장 기대비용, 최악값을 CVaR라고 부르지 않았습니다. FA/RA 차이에는 평균가격 가정 차이와 CVaR가 함께 들어가므로 순수 위험 목적 효과의 식별은 Day 9의 같은 세트 λ0 비교 설계에 남깁니다.

## 10. 부족·서비스·업체 배분과 비용 구성

서비스율=전체 fulfilled/전체 demand이며 C/E 수요800t, 나머지600t입니다. 아래 값은 Fixed/FA/RA 순서입니다.

| Toy | 부족t | 서비스율 % | RA A/B 총발주t | RA 평균재고t |
|---|---|---|---|---:|
| A | 80 /0 /0 | 86.67 /100 /100 | 100 /300 | 113.33 |
| B | 80 /60 /0 | 86.67 /90 /100 | 100 /300 | 100.00 |
| C | 280 /180 /20 | 65 /77.5 /97.5 | 180 /400 | 53.33 |
| D | 80 /0 /0 | 86.67 /100 /100 | 100 /300 | 113.33 |
| E | 280 /260 /100 | 65 /67.5 /87.5 | 180 /320 | 66.67 |

Fixed의 A/B는 전부240/80t, FA는A/D240/160, B/E240/100, C240/180t입니다. RA 월별 발주는 A/B/D에서180/120/100/0/0/0, C에서180/120/180/100/0/0, E에서180/120/180/20/0/0t였습니다. 미래 계획이 확정 발주로 중복 실행되지 않았습니다.

| RA Toy | 매입 | 보관 | 부족비 | 최종 종료비 | 총 USD |
|---|---:|---:|---:|---:|---:|
| A | 42,600 | 2,040 | 0 | 1,800 | 46,440 |
| B | 42,600 | 1,800 | 0 | 1,800 | 46,200 |
| C | 61,560 | 960 | 30,000 | 1,800 | 94,320 |
| D | 64,920 | 2,040 | 0 | 1,800 | 68,760 |
| E | 89,640 | 1,200 | 150,000 | 1,800 | 242,640 |

모든정책의 운송·폐기비0, 실제 종료비1,800USD이며 전체 최종월에만 한 번 청구했습니다. Fixed/FA의 상세 비용은 Day7과 그대로이며 새 `toy_comparison.json/csv`에도 저장했습니다. 실제 수령월 지수를 사용하며 발주가 과거 가격을 고정하지 않습니다. 모든 정책 solver failure count0입니다.

## 11. 실제 저장 Planning Scenario smoke

| 모델·origin | 현재 A/B t | E 계획비 USD | CVaR90 USD |
|---|---|---:|---:|
| SARIMAX 2021-06 | 80 /20 | 34,461.47 | 39,774.22 |
| SARIMAX 2024-05 | 80 /20 | 30,989.31 | 38,021.33 |
| LightGBM 2021-06 | 0 /100 | 35,696.47 | 42,073.71 |
| LightGBM 2024-05 | 17.2515 /82.7485 | 36,095.93 | 48,952.92 |

4개 모두128개 Planning 경로, OPTIMAL·물리·비예견성·독립 CVaR 검산을 통과했습니다. I200·빈pipeline은 명시적 합성 상태이며 실제 회사 상태가 아닙니다. 실제 target·구매 ledger·성과를 읽거나 만들지 않았습니다. Origin 간 경로를 장기 시계열로 이어 붙이지 않았습니다.

## 12. 자동 테스트

신규 **61 passed, 3 warnings in1.20s**, 최종 전체 **264 passed, 3 warnings in92.15s**, exit0입니다. 기존203개를 모두 포함합니다. 경고3개는 OR-Tools SWIG의 `__module__` deprecation이며 solver 실패가 아닙니다.

합성 fixture로 CVaR fractional atom/가중합, 확률·단위·origin/model/purpose·horizon 혼합 차단, shared q/flow, λ0/1·동일128경로, pipeline상수·cohort capacity, lead·재고·greedy/overflow, 수치·비용 변조·status·VerifySolution, 현재 주문만 실행·재최적화, 미래 실제충격 불변성, Holdout100→1e90변조 불변성, 파일 reader가 없는 solver, proof 숫자의선택후해석을 검증했습니다. 실제 World Bank 가격은 pytest에 내장하지 않았고 실제 저장 세트 smoke는 실행 드라이버에서 분리했습니다.

## 13. 독립 검산·재현·보존

최종 run: `artifacts/day8/20261030T070224306255Z/`, 반복: `artifacts/day8/20261030T070249313512Z/`. 가상 입력은 같은 run ID의 `data/synthetic/day8/`입니다. 앞선 점검 run도 보존했습니다. 최종 adapter는 요청하지 않은 OOF pool 숫자를 문자열로 유지하도록 경계를 강화했으며 시나리오·주문·비용·risk 사양을 바꾸지 않았습니다.

독립 검산기는 solver/최적화 함수를 import하지 않고 주문·lead·기존pipeline·capacity·재고·greedy 흐름·수령월 매입비·운송·보관·부족·폐기·말기·scenario별 비용·가중 E/CVaR를 재구성했습니다. 6손계산/4경계/25RA rolling/4실제smoke와 공통상태 계획비교를 확인했습니다. Fixed/FA의 주문·입고·원장30파일은 Day7과 바이트 동일합니다.

두 run의 **129개 결정적 파일**이 synthetic 입력까지 바이트 동일합니다. Manifest·spec freeze의 생성시각·solver 시간은 동일성 대상에서 제외합니다. 각 run의 독립 검산 및 기존652개 파일·3개 문서 원문 prefix 보존을 확인했습니다. Python/패키지·solver binary·코드·설정 사본·원본 및 기존 Day6/7/split 연결 해시를 manifest에 보존했습니다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_day8_risk_optimization.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m food_procurement_intelligence.evaluation.day8 --config configs/day8.toml
.\.venv\Scripts\python.exe scripts/verify_day8_results.py --run artifacts/day8/20261030T070224306255Z --repeat artifacts/day8/20261030T070249313512Z
```

재실행은 새 run 폴더에만 저장합니다. 모델 재학습·새 데이터/패키지 다운로드·Git commit/push는 없었습니다.

## 14. 경제적·통계적 한계와 질문의 답

CVaR는 경험적 가격 시나리오의 총계획비용 tail입니다. Day5 보정 구간도80% coverage에 미달했고, Day6 bootstrap의 tail 확률·상대오차 안정성은 검증되지 않았습니다. Planning/evaluation seed 분리는 통계적 독립/OOS를 뜻하지 않습니다. 최신 수정본과 가정 공표시각의 pseudo-real-time 한계를 유지합니다.

현재 수요·lead가 결정적이므로 부족량 자체는 시나리오 사이에 같고, 부족 penalty는 총비용의 공통항입니다. CVaR가 부족을 자동으로 감소시키지 않습니다. 수요/지연 분포·가격과의 상관을 추정하지 않았으며, 창고·공급능력·3개월창·말기근사·폐기0제한·미래계획 비확정 때문에 실제 성과가 달라질 수 있습니다. 모든Toy에서 개선하거나 업체 배분이 달라져야 한다고 가정하지 않습니다.

질문의 답: **RA는 수령월 가격 급등에 노출되는 발주량과 수령시점·업체 배분을 바꿔, 제시된 시나리오에서 높은 총비용의 tail을 줄이려 합니다.** 조기수령·재고 보유로 일부 노출을 옮길 수 있지만 납품월 연동가격을 고정/헤지하지 못합니다. 이미 확정한 pipeline을 취소할 수 없고, 모델 밖의 가격 충격·수요 급증·납기 지연·공급능력 한계와 실제 미래 CVaR/서비스를 보장하지 못합니다. 정상Toy의 비용 증가는 위험 대비에 추가 비용이 들 수 있음을 보여줍니다.

## 15. Day 9 설계 과제 — 미실행

별도 지시 후 Validation에서 공통 초기200·빈pipeline·실제가격 귀속·같은 외생 수요/발주cohort지연·동일 회계/실패규칙으로 장기 정책 평가창을 먼저 고정해야 합니다. 종료월 부분 horizon 예측의 가용성과 terminal admission이 일관되게 처리되는지 검증하고 origin 내부 Day6 경로를 장기 실현가격으로 이어 붙이지 않아야 합니다.

같은 시나리오에서 λ0 대 λ.5로 위험 목적 효과를, 같은 정책에서 SARIMAX 대 LightGBM으로 예측 효과를 분리합니다. 사후 α/λ 튜닝을 하지 않고 paired 비용차·서비스분모·실패포함·종료조건·초기재고/창길이 민감도와 평가 seed bank를 사전에 정의해야 합니다. 장기 realized CVaR는 공통 평가경로 전체 운영비 분포에서 별도로 정의하고 planning 목적과 구분합니다. Holdout은 계속 잠금입니다. **Day 9는 시작하지 않았습니다.**
