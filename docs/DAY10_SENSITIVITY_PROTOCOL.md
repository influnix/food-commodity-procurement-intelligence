# Day 10 셀별 결과 계산 전 사양 고정

2026-10-30 Asia/Seoul. Day9 결과를 이미 관측한 뒤 설계하는 **사후 민감도 진단**입니다. 독립 사전등록·OOS 실험이 아닙니다. Day10 셀별 결과를 보기 전에 `configs/day10.toml`과 본 문서의 SHA-256을 고정합니다. 어떤 유리한 셀도 새 기본 설정으로 채택하지 않습니다. Day0~9 구현·설정·데이터·성과와 Holdout 잠금은 보존합니다.

## 선행 Baseline Gate

먼저 Day10 코드 경로로 기존7정책을 재실행했습니다. Day9 `20261030T090528446877Z`의 주문/입고/원장21파일은 바이트 동일하고, Full/Active/Runoff 지표21행은 정확히 일치했습니다. 결과는 `artifacts/day10/baseline_regression.json`입니다. 이후의 각 실행도 Baseline을 다시 풀어 같은 gate를 통과해야 다른 셀을 실행합니다. 차이가 나면 중단하고 셀 성과를 생성하지 않습니다.

## 달력·정보·공통 입력

초기2021-06월말·빈pipeline,36개 결정2021-06~2024-05, 실제 Validation가격38개월2021-07~2024-08, Active원장35개월/Runoff3개월을 유지합니다. Runoff 신규 주문과 미래 계획 q의 상한은0입니다. 실현 종료비는8월에한번, 계획창말기근사는목적함수에만있습니다. 초기재고 취득비는공통 sunk cost이고 다른초기재고셀의총비용감소를무료자산의경제적절감으로해석하지않습니다.

기존7정책·α.90·RNλ0/RAλ.5·3개월계획·명목lead·최대delay1·폐기W0·greedy검사를그대로사용합니다. Point/Planning은 기존검증된저장입력만사용합니다. Baseline의72개모델/origin입력을압축불변캐시에보존하고,해시·기존source연결을확인한후재구성합니다. 모델재학습·새OOF·가격생성은없습니다. 같은모델의RN/RA는동일시나리오를받습니다. 실제가격reader는evaluator만소유하고정책은t−1/공표timestamp를통과한이력·공개재고/pipeline만받습니다. 미래수요·실제도착월·delay와평가원가는전달하지않습니다.

## 전체 셀 목록

Baseline1 + OAT8 + Stress2 =11개실행셀, 지원감사3개로총14개입니다. Baseline고정값은I200·부족1500·말기9·보관3·Bcap100입니다. OAT는명시된입력하나만변경하고가격·수요·실현delay·다른계약·창고400·말기목표200·정보시점을유지합니다. Cell ID/world ID는추적메타데이터이며운영변수변경으로세지않습니다.

| ID | 변경값 | 종류 |
|---|---|---|
| baseline | 없음 | 회귀기준 |
| inventory_100 / inventory_300 | 초기재고100 /300t | OAT |
| unmet_750 / unmet_3000 | 부족비750 /3000USD/t | OAT |
| terminal_0 / terminal_30 | 말기편차계수0 /30USD/t | OAT |
| holding_6 | 보관6USD/t/월 | OAT |
| capacity_b_60 | B 월capacity60t | OAT |
| stress_demand_120 | 2022-01~03 실현수요120t, 계획100유지 | Stress |
| stress_delay_a_1 | A의2022-01~03 발주cohort 추가delay1 | Stress |
| audit_horizon_2 | 입력H1/H2는존재하나현재solver3개월강제 | 미지원감사 |
| audit_horizon_6 | H4~H6입력·검증된planner없음 | 미지원감사 |
| audit_lag_2 | t−1 fit/OOF를t−2로재라벨링불가 | 미지원감사 |

비용계수는동일SimulationSettings로LP와실제engine에함께전달합니다. 말기계수변경은계획근사와실제최종비용모두에적용합니다. 공급capacity는동일Supplier객체로양쪽에전달하며Fixed의배분80/20은바꾸지않습니다. 기존객체를변이하지않고Day10명시적replace adapter만사용합니다.

Stress는가격38개월과계획수요100·명목지연0을유지합니다. 실제수요120은1~3월에만적용하고수요예측을갱신하지않습니다. A delay는 `(supplier_id,order_month)`의동일키에모든정책이같은1개월충격을받으며나머지는0입니다. 임의주문순번/RNG소비에의존하지않습니다. RNG·추첨seed는사용하지않는결정적규칙이며기존Planning seed는그대로입니다. 이두stress는실제기업지연/수요분포의추정값이아닙니다.

## 지원 범위 감사

현재모델출력과ScenarioSet은H1/H2/H3뿐입니다. nativeLP의`build_problem`은horizon_months=3만허용하며2/6을넣으면INVALID_INPUT임을합성테스트로확인합니다. 2개월에필요한가격일부는있어도A lead2+최대delay1의계획창허용성과기존pipeline 처리·새rolling window를검증한별도모델이필요합니다. 이번OAT의동일3개월정책비교에그새모델을섞지않고미지원으로기록합니다. 6개월은추가가격입력도없습니다.

2개월공표지연에서는현재t−1까지fit한모델·OOF가정보제약을위반합니다. ModelPrediction의t−1cutoff검사·Day6 OOF proof를확인하며t−2재라벨링이거부되는지테스트합니다. 새학습/OOF가필요하므로미지원입니다. 이지원감사는실제가격을새로예측하거나학습하는작업이아닙니다. Runoff변경은38개월원칙과forecastorigin가용성을바꾸므로실행하지않습니다.

## 지표·순위·비교 방향

모든성공정책은Cost7성분,수요/충족/부족/fill/stockout/평균재고,업체별발주,최종재고/pipeline,solver상태·수치·시간을보존합니다. 월별paired비용/서비스/재고/주문과Full/Active/Runoff집계를저장합니다. Fixed대비,같은모델RA−RN/FA−RN,같은정책LightGBM−SARIMAX를셀내에서비교합니다. FA와RA차이를순수CVaR효과로해석하지않습니다.

전체7정책이완주한셀만비용순위를계산합니다. 비용tie허용은1e−4USD의수치기준이고동점은공동순위입니다. 모든정책쌍의Baseline대비엄격한비용차부호역전과최저비용정책집합변경을보존합니다. RA SARIMAX−Fixed의near-tie는절대차/Fixed비용≤0.1%라는진단표시이며경제적/통계적유의성문턱이아닙니다. 비용순위와fill을함께제시하고비용·서비스모두열세인정책표시를보조로둡니다. 셀개수를시장발생확률이나독립표본수로해석하지않습니다.

Runoff감사는마지막Active말재고와확정pipeline,Runoff월별입고·충족·부족·비용,최종재고/pipeline·종료비를보존합니다. Active비용만으로절감을주장하지않으며Full−Active=Runoff를검산합니다. PlanningCVaR누계를실현CVaR로표시하지않습니다.

## 실패·압축·재현

상태는COMPLETE / FAILED_SOLVER / FAILED_PHYSICAL_VALIDATION / UNSUPPORTED_CONTRACT / FAILED_AVAILABILITY / INCOMPLETE_EVALUATION으로구분합니다. 실패원인과첫시점,부분결정로그를남기고실패한셀도삭제하지않습니다. 다른정책은독립적으로시도하고성공정책의완전원장은남기되7정책전체순위/전체paired비교는차단합니다. 실패정책의부분비용을38개월총비용으로사용하지않습니다. fallback은없습니다. 전역입력무결성실패는전체실행을중단합니다.

기존solver/엔진·모델을변경하지않습니다. 계획raw해·scenario별비용·LP원문은mtime0의결정적gzip으로보존하고공통scenario는hash로연결해중복저장을줄입니다. 실제월원장/입고/주문은CSV,공개이력은기존source와as-of hash·최신월/공표시각으로감사합니다. 시간은별도파일로보존하고반복동일성에서는제외합니다. 각run은새Day10폴더에설정사본·환경·solver binary·기존모델/원본/split/Day9·신규코드·출력해시를남깁니다.

합성손계산·누수·OAT·실패/미지원·tie/역전·압축재현테스트를먼저통과한뒤셀을실행합니다. 독립검산기는기존독립LP산술과별도수령월/재고/실제비용수식으로모든성공셀을검산하고,반복run의결정적파일과 기존 파일 보존을 확인합니다.

한역사적가격경로·가상운영조건·개발Validation선택편향·Day5 coverage미달·경험적tail확률미검증·최신수정본/가정공표시각한계를유지합니다. 새로운기본설정선정·Holdout평가·Day11은실행하지않습니다.
