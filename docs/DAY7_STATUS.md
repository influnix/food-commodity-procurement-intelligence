# Day 7 실행 기록

2026-10-29 Asia/Seoul. **Day 7 완료**. Deterministic GLOP 구매LP, Forecast-Aware receding-horizon 정책, 손계산·동일Toy 비교·저장Forecast adapter smoke를 구현하고 독립 검산·반복 재현을 확인했습니다. 실제 Validation 구매성과·Holdout·Risk-Aware·CVaR·Day 8은 실행하지 않았습니다.

## 1. 파일과 보존

신규 파일은 `configs/day7.toml`, `requirements/day7-lock.txt`, `optimization/__init__.py`, `optimization/deterministic.py`, `optimization/forecast_adapter.py`, `optimization/toy_lp.py`, `policies/forecast_aware.py`, `evaluation/day7.py`, `tests/test_day7_optimization.py`, `scripts/verify_day7_results.py`, 본 문서·[LP 명세](DAY7_LP_SPEC.md)·[환경 기록](DAY7_ENVIRONMENT.md)입니다. 모듈 기준은 `src/food_procurement_intelligence/`입니다.

README·ROADMAP·AGENTS와 관련 헌장/평가/정보시점/사전 문서에 새 단계 설명만 추가했습니다. 기존 Day 0~6 구현·테스트·설정·데이터·결과·스크립트·lock·pyproject **296개 파일**의 해시를 유지했습니다. 기존 엔진과Fixed 정책은 수정하지 않았습니다.

## 2. 환경·고정 설정

OR-Tools9.14.6206 / `Glop solver v9.14.6206`, 기존프로젝트Python3.11.5입니다. 필수4개만`.venv`에 추가했고 기존패키지·전역 환경은 그대로입니다. Day 7 config SHA-256은 `2a3b95e66ea2aaa48441be994cfb8d4eb79889b380af6308eed529685eb24418`입니다. [정확한 설치·검증 기록](DAY7_ENVIRONMENT.md)을 참고하세요.

## 3~4. LP와 납품월 계약

[사전 수식](DAY7_LP_SPEC.md)을 코드보다 먼저 작성했습니다. q_(s,k),I_m,U_m,R_m,W_m,z+/z−를 연속 비음수 변수로 사용합니다. Receipt는기존pipeline+명목lead에따른새입고, 재고는이전재고+입고−수요+부족−폐기입니다. Capacity·lead·창고상한·수요상한·말기편차·현재cohort의이미확정된수량을검사합니다. 신규주문은계획창말까지최대delay를포함해도착할수있어야합니다.

목적함수는새발주매입/운송비+변경불가pipeline상수+보관+부족+폐기+계획말기편차비입니다. 단가는**예상수령월 point×(1+premium)**입니다. 선발주가가격을고정하지않습니다. 실제정산은변경없는Day6엔진이실제수령월지수로처리합니다.

자유 W가정상재고를임의폐기하는충돌을막기위해기본LP는W=0으로제한했습니다. 강제초과입고에서는보수적인LP가INFEASIBLE일수있습니다. 엔진은여전히실제초과분을폐기하며모델이엔진규칙을바꾸지않습니다. U/I/W를greedy수요충족회계로다시검사하고불일치한LP최적해도실행하지않습니다.

## 5~6. 초기상태·확정주문·월별 실행

정책 비교는두정책모두초기재고200t·**빈pipeline**입니다. Day6검산용opening A80/B20은별도회귀검사에서만유지했고5개결과가원래손계산과일치했습니다.

기존주문은취소하지않고예상입고상수로처리합니다. overdue는공개된미납상태만보고다음달로예상합니다. 실제미래delay는읽지않습니다. 계획창밖기존pipeline은deferred로남기며글로벌종료밖입고는거부합니다.

매월t+1~t+3의계획을풀지만현재t의q만OrderRequest로확정합니다. 정상Toy첫계획의미래B(2000-02)는100t였으나등록하지않았고, 실제2월에다시풀어B20t만확정했습니다. 같은origin중복실행/역순재생은거부합니다. 나중에pipeline에서주문이사라지거나기존미래계획이중복입고되지않음을검산했습니다.

계획말기9×|I_e−200|는매fold의근사목적함수에만있습니다. 실제ledger종료비는전체최종월에한번이며모든Toy정책비교의실제종료비는1,800USD였습니다. 계획비용을ledger에누적하지않았습니다.

## 7. Solver·실패·수치

실제실행은손계산5개+Toy25개+Forecast smoke4개=**34개OPTIMAL**, 최종월무발주5개=TERMINAL_NO_ACTION입니다. 실행실패0·fallback0, 실제current수량정규화량0t입니다. raw변수·목적함수·구성요소·제약수·최대위반·VerifySolution·시간·LP text를저장했습니다.

FEASIBLE은별도상태이며기본실행에허용하지않습니다. INFEASIBLE/UNBOUNDED/ABNORMAL/MODEL_INVALID/NOT_SOLVED/미지상태·backend미설치·입력오류를분리합니다. 실패는정책비교를중단하고결과를성공처럼보고하거나Fixed로대체하지않습니다. Fake backend로각분기를검증했습니다.

Primal/dual tolerance1e−8,수량1e−7t,목적함수abs1e−4USD/rel1e−8입니다. raw값과현재실행수량을분리하고수치경계내에서만0/capacity정규화하며차이를기록합니다. 테스트에서는더큰초과를거부했고낮은부족패널티로greedy서비스를위반한LP최적해도차단했습니다.

## 8. 손계산 LP

| 사례 | 해 | 목적함수USD |
|---|---|---:|
| A 단일수요/재고부족 | 신규8t | 80 |
| B 서로다른lead | 현재A10/B10t | 220 |
| C 저가업체capacity4 | A4/B6t | 112 |
| D 납품가격10→20,보관1 | 현재20t수령용발주,미래0 | 210 |
| E capacity4/수요10 | 신규4,부족6t | 6,040 |

다섯해모두사전계산과일치했습니다. D는저렴한납품월에수령해서재고를보유하는검산이며발주월가격고정효과가아닙니다. 이작은LP의max delay0/단순말기조건은손계산전용으로정책비교계약과구분합니다.

## 9~10. Synthetic Toy Policy Comparison

동일한Day6 world A~E,같은계약·실현가격·수요·발주월별delay·창고·비용·기간·말기조건을사용했습니다. 계획수요100t,가격belief는사전고정한전h100USD/t입니다. 실제future world를oracle예측으로변환하지않았습니다. SARIMAX를Toy예측인것처럼사용하지않습니다.

| Case | 정책 | 매입비 | 보관비 | 부족비 | 총비용USD | 부족t | 평균재고t |
|---|---|---:|---:|---:|---:|---:|---:|
| 정상 | Fixed | 33,120 | 540 | 120,000 | 155,460 | 80 | 30.00 |
| 정상 | Forecast-Aware | 41,760 | 780 | 0 | 44,340 | 0 | 43.33 |
| 지연 | Fixed | 33,120 | 840 | 120,000 | 155,760 | 80 | 46.67 |
| 지연 | Forecast-Aware | 35,280 | 840 | 90,000 | 127,920 | 60 | 46.67 |
| 수요급증 | Fixed | 33,120 | 360 | 420,000 | 455,280 | 280 | 20.00 |
| 수요급증 | Forecast-Aware | 43,920 | 720 | 270,000 | 316,440 | 180 | 40.00 |
| 가격상승 | Fixed | 58,920 | 540 | 120,000 | 181,260 | 80 | 30.00 |
| 가격상승 | Forecast-Aware | 76,200 | 780 | 0 | 78,780 | 0 | 43.33 |
| 복합 | Fixed | 63,000 | 840 | 420,000 | 485,640 | 280 | 46.67 |
| 복합 | Forecast-Aware | 67,320 | 840 | 390,000 | 459,960 | 260 | 46.67 |

운송·폐기비는모두0,종료비는모두1,800USD이며총비용에포함됩니다. Fixed의A/B발주합계는모든case240/80t입니다. Forecast-Aware는정상·가격상승240/160,지연·복합240/100,수요급증240/180t였습니다. Solver실패는모두0입니다.

| 정책·case | 1~6월 신규발주t |
|---|---|
| Fixed 전부 | 100/100/100/20/0/0 |
| Forecast-Aware 정상·가격상승 | 100/100/100/100/0/0 |
| Forecast-Aware 지연·복합 | 100/100/80/60/0/0 |
| Forecast-Aware 수요급증 | 100/100/120/100/0/0 |

정상Toy의차이는주로4월B발주20→100t가말기부족80t를줄인데서발생했습니다. 이는특정합성조건·큰부족패널티·말기제약에의존합니다. 모든case에서낮은비용이관측됐지만실제회사절감이나SARIMAX의예측효과를측정한결과는아닙니다. 가격belief가100이어도실제200달러납품월에는200×premium으로지불했습니다.

## 11. 실제 Forecast adapter smoke

Day4원본pointCSV의해시를검사하고point/schema/origin/horizon/unit/logical issue time만export합니다. actual/error/score열은정책에전달하지않습니다. Source는SARIMAX와LightGBM각각이며2021-06/2024-05의**4개계획**이OPTIMAL·검증통과였습니다. 현재재고200·빈pipeline은명시적가상상태입니다. 실제가격을사용한구매ledger나실제Validation조달개선율은계산하지않았습니다. Holdout/non-validation origin은adapter가거부합니다.

## 12. 자동·독립 검증

신규 **30 passed,3 warnings in0.24s**, 최종전체 **203 passed,3 warnings in78.70s**, exit0입니다. 기존173개를모두포함합니다. 경고는OR-Tools SWIG import의세deprecation이며solver오류가아닙니다.

실제GLOP손계산·pipeline상수/committed capacity·lead·terminal절댓값·강제overflow제한LP의infeasibility·수치/목적함수변조·미래발주미실행·재최적화·최종비용단일계상·엔진수령단가일치·미래실현값변경불변·Holdout차단을검증했습니다. Fake backend는status·backend실패·VerifySolution실패·수량경계처리를분리검증했습니다. 실제시장가격은pytestfixture에없습니다.

독립스크립트는30개월별결정의LP·실제입고·재고·비용·확정주문을별도수식으로재구성하고5개손계산과4개smoke를확인했습니다. Solver통과여부만으로성공이라고하지않았습니다.

## 13. 산출물·재현성

최종 run은 `artifacts/day7/20261029T022953285525Z/`, 반복 run은 `artifacts/day7/20261029T022956116131Z/`입니다. 가상 입력은 같은 ID의 `data/synthetic/day7/`에 있습니다. LP 모델34개, hand 결과, 정책별 orders/receipts/ledger, 월별 rolling_plans, 실행 current 주문, 비용 비교, adapter smoke, 시간, manifest를 저장했습니다. Solver 시간은 손계산·Toy·smoke의34개 해와 최종월 무발주5개에 대해 기록했습니다.

설정·코드 해시가 같으며 **75개 결정적 파일**이 가상 입력까지 바이트 동일했습니다. 시간·spec 생성시각·manifest는 동일성 대상에서 제외했습니다. 각 run의 독립 검산과296개 기존 파일 해시 보존을 확인했습니다. 검증 결과는 `verification_20261029T022953285525Z_repeat.json`, `verification_20261029T022956116131Z.json`입니다. 앞선 두 점검 run도 보존했으며 전체 Solver 시간 기록을 보강한 뒤 최종 두 run을 검증했습니다. 사양·주문·비용은 그대로입니다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m food_procurement_intelligence.evaluation.day7 --config configs/day7.toml
.\.venv\Scripts\python.exe scripts/verify_day7_results.py --run artifacts/day7/20261029T022953285525Z --repeat artifacts/day7/20261029T022956116131Z
```

기존 파일을 덮어쓰지 않습니다. 다시 실행할 때는 새 run의 경로를 전달해 검증합니다.

## 14. 남은 한계

명목lead는실제delay를예측하지않으며overdue의다음달입고는가정입니다. 계획창3개월과최대delay허용경계가발주를보수적으로제한합니다. 계획폐기0은보수적부분모델이므로forced overflow를포함하는물리적으로가능한상태에서도제한LP는infeasible일수있습니다. Greedy서비스검사로비물리해를거부하며일반비용계수에서자동실행가능성을보장하지않습니다.

계획말기재고가치는근사이고큰부족패널티·단순수요·짧은Toy기간에민감합니다. 같은표본의모델선택·최신수정본·가정공표시각·2020-07정의변경한계는그대로입니다. 이번Toy비교는가격예측정확도의운영효과에대한실증실험이아닙니다. Day6경로와Day5 Coverage는변경하지않았습니다.

## 15. Day 8에 필요한 작업 — 미착수

공동시나리오의planning-only계약과동일외생평가경로를유지하면서shared q/non-anticipativity,scenario별입고·수요·재고·기존pipeline비용과CVaR를수식으로먼저정의해야합니다. 의존OOF pool과미검증tail/coverage를확률보장으로사용하지않고,폐기·서비스의물리규칙·수치실패·비교조건을고정한작은손계산부터검증합니다. Risk-Aware·stochastic/CVaR·실제Validation정책평가·Holdout은이번에구현하지않았습니다.

납품월연동계약에서Forecast-Aware가바꿀수있는것은**업체·수량·예상납품시점·재고보유와부족의trade-off**입니다. 선발주가과거가격을고정하지않으며실제단가는수령월에정해집니다.
