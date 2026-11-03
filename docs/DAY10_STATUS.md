# Day 10 실행 기록

2026-10-30 Asia/Seoul. **Day 10 완료**. 실제 Validation 가격과 가상 운영조건의 OAT·Stress·순위 안정성·Runoff 진단을 수행했습니다. Day9 결과를 관측한 뒤 설계한 사후 진단이며 독립 사전등록/OOS 실험이 아닙니다. 기존 기본값·모델·분할·Holdout 잠금은 유지합니다.

## 1. 생성·수정 파일

신규 파일은 `configs/day10.toml`, [사전 프로토콜](DAY10_SENSITIVITY_PROTOCOL.md), 본 문서, `src/food_procurement_intelligence/evaluation/sensitivity.py`, `evaluation/day10.py`, `tests/test_day10_sensitivity.py`, `scripts/verify_day10_results.py`입니다. 두 평가 모듈은 기존 adapter·정책·solver·엔진을 재사용하며 운영조건만 명시적으로 replace합니다. README·ROADMAP·AGENTS에는 설명을 덧붙이고 이전 바이트를 보존했습니다.

모든 신규 실제 실행 결과는 `artifacts/day10/`, 가상 운영입력은 `data/synthetic/day10/`에 저장했습니다. 기존 Day0~9 코드·모델·설정·데이터·성과2440개 파일은 해시가 그대로입니다. 새 패키지·외부 데이터 다운로드·모델 재학습·Git commit/push는 없습니다.

## 2. 결과 계산 전 고정과 Hash

Baseline Gate 후 2026-10-30T11:43:53.944718Z에 OAT/Stress 셀별 결과 계산 전 사양을 고정했습니다.

- Day10 config: `c3e6106909c330827f6b831a6097262d3d31e0741be019893f220585d1aa48bc`
- Day10 protocol: `c86689b78b8b4456865c6046eb61d9c1d9d958e16a16f7e8f6b84ddc3b1371ca`
- Day9 config: `9310a210dd0a12ff68a4b027a96e4d9bcb8f9ccf7377a6d1ea69ccfa7f160d31`
- Day9 protocol: `4e0b3588d12cc47822dd122bd29b3f6dea73dd817e23a37ee04201336d3d9a05`

α=.90, RNλ0/RAλ.50, 7정책, 36개 결정·38개월 평가·Runoff3개월을 고정했습니다. RNG는 사용하지 않는 명시적 stress이며 기존 Planning seed/경로는 그대로입니다. 유리한 셀을 골라 기본값으로 바꾸지 않았습니다.

## 3. Day9 Baseline Gate

선행 Gate와 두 본 실행의 Baseline 모두 통과했습니다. Day9 최종run `20261030T090528446877Z`의 **주문·입고·원장21파일이 바이트 동일**, Full/Active/Runoff 지표21행이 정확히 일치했습니다. 첫 Gate는 `baseline_20261030T113653996974Z`, 기록은 `artifacts/day10/baseline_regression.json`입니다. 차이가 있으면 나머지 셀을 실행하지 않는 구조입니다.

## 4. 전체 셀과 완료 현황

Baseline1·OAT8·Stress2의 **11개 셀 모두 COMPLETE**, 총77개 정책 평가가 완주했습니다. 2/6개월 계획창·2개월 공표 지연은 감사 후 **UNSUPPORTED_CONTRACT 3개**로 목록과 이유를 보존했습니다. 실행 실패·중간 누락·fallback은0입니다. 전체14개 목록은 config와 run의 `failure_unsupported_report.json`에 있습니다.

모든 실행 셀은 실제가격38개월·36개 origin·3개월 planning·Active35/Runoff3·창고400·말기목표200·빈초기pipeline·기존예측을 공유합니다. OAT는 하나의 운영변수만 바꿉니다. Cell/world ID는 추적용 메타데이터입니다.

## 5. 초기재고100/300t

두 셀에서도 최저비용은 FA/RN LightGBM 공동입니다. 초기100t에서 Fixed는100t 부족·Fill97.3684%, FA SARIMAX는20t 부족이고 나머지는 수치허용 내 부족0입니다. 초기300t에서 Fixed는부족0, FA SARIMAX의Runoff20t는남았습니다.

셀 내부 RA SARIMAX−Fixed 비용차는 I100에서−107,121.12USD, I300에서−43,693.92USD입니다. Fixed의고정주문과최종부족/잔여재고 차이가 큽니다. 초기재고 취득비는 기존처럼 sunk cost이므로 서로 다른 초기재고 셀의 총비용 감소를 무료 자산 증가의 경제적 절감으로 해석하지 않습니다.

## 6. 부족비·보관비

부족비750/1500/3000에서 현재 발주량 차이는 최대2.56e−13t로 수치오차 범위였고 FA SARIMAX의Runoff부족20t는 유지됐습니다. 그 비용만15,000/30,000/60,000USD로 달라졌습니다. 부족비750에서는 FA SARIMAX가Fixed보다587.52USD 저렴하지만 서비스는낮습니다. 비용순위가 바뀌어도 발주행동이 바뀐 것은 아닙니다.

보관비6에서는 FA SARIMAX 평균재고46.32→38.42t, FA LightGBM52.63→48.95t, RN SARIMAX111.05→90t로줄었습니다. RA SARIMAX는115.79→115.46t로거의유지했습니다. 이때 RA SARIMAX−RN은기존−1,591.92에서 **+4,914.04USD**로역전됐고서비스차이는0입니다. FA LightGBM만단독최저비용이며RN LightGBM과의동점이풀렸습니다.

## 7. 말기계수0/30

0/9/30 범위에서 모든 정책의 현재 발주·입고·재고·부족은동일했습니다. 최종재고0/목표200이므로 실제 종료비는0/1800/6000USD로변했고 전체비용은Baseline대비−1800/+4200USD씩평행이동했습니다. 순위·서비스·FA SARIMAX Runoff20t는변하지않았습니다. 계획근사와실제종료비 양쪽에 같은계수를적용했으며 실제종료비는한번만계상했습니다.

## 8. B capacity60

Fixed20t 배분은유지했고solver와engine에모두B cap60을전달했습니다. 이범위에서서비스악화는없었고FA SARIMAX의기존20t부족만남았습니다. FA/RN LightGBM 평균재고52.63→74.74t, 총비용+6,684.48USD였습니다. RA LightGBM−RN의추가비용은14,271.96→6,594.68USD로축소됐습니다. RA SARIMAX 결과는Baseline과같았습니다. 이capacity가모든수요충격에서충분하다고일반화하지않습니다.

## 9. 공통 수요·납기 Stress

수요120은2022-01~03에만실현하며계획수요100을유지했습니다. 전체수요3860t입니다. Fixed는60t부족이최종Runoff에발생했고, FA SARIMAX는기존Runoff20t, 나머지는수치허용내부족0입니다. 미래수요를미리주거나수요예측을갱신하지않았습니다.

A의2022-01~03 **발주cohort**에추가delay1을동일하게적용한셀에서는순위가역전됐습니다.

| 정책 | 총비용 USD | 부족t | Fill Rate |
|---|---:|---:|---:|
| Fixed | 1,348,602.96 | 0 | 100% |
| FA SARIMAX | 1,465,295.28 | 120 | 96.8421% |
| RN SARIMAX | 1,349,597.04 | 0 | 100% |
| RA SARIMAX | **1,348,005.12** | 0 | 100% |
| FA LightGBM | 1,433,343.36 | 100 | 97.3684% |
| RN LightGBM | 1,433,343.36 | 100 | 97.3684% |
| RA LightGBM | 1,381,982.20 | 40 | 98.9474% |

실제도착월/미래delay는정책에전달하지않고공개promised/overdue만사용했습니다. Fixed의Baseline대비낮은비용은수령월지수와보관시점이바뀐이경로의회계결과이며지연이유리하다는일반주장이아닙니다.

## 10. 전체 Cost/Fill 비교

전체77개정책의비용7성분·Fill·재고·업체별수량은 run의 `policy_matrix.csv`, 기간별231행은 `policy_metrics.json`에있습니다. 모든최저비용정책은이번셀에서Fill100%였으나비용만으로우수성을분류하지않았습니다. 아래는셀전체의최소Fill과평균재고범위입니다.

| 정책 | 최소Fill % | 평균재고 범위t |
|---|---:|---:|
| Fixed | 97.3684 | 18.95~216.32 |
| FA SARIMAX | 96.8421 | 38.42~67.37 |
| RN SARIMAX | 100 | 90.00~114.74 |
| RA SARIMAX | 100 | 109.47~117.89 |
| FA LightGBM | 97.3684 | 48.95~74.74 |
| RN LightGBM | 97.3684 | 51.05~74.74 |
| RA LightGBM | 98.9474 | 93.27~98.36 |

수량표는반올림한값입니다. 원장에는2.84e−14t수준의부족도그대로보존했고가격/수량을clip하거나생성하지않았습니다. Stockout 판정은기존1e−7t허용범위를따릅니다.

## 11. 순위와 Near-Tie

FA LightGBM은11셀중10셀에서최저비용집합에포함됐고, RN LightGBM은9셀에서공동최저였습니다. A지연셀은RA SARIMAX가최저입니다. 따라서한정된grid에서도보편적인최저비용정책은없습니다.

Baseline대비엄격한정책쌍순서역전은셀별21건, 동점해소를포함한관계변화22건입니다. 해당셀은초기100/300, 부족750, 보관6, 수요/납기Stress입니다. 모든쌍과순위변화는 `stability.json`에보존했습니다. 동일셀/정책의반복등장을독립표본으로세지않습니다.

RA SARIMAX−Fixed는이번11셀에서모두음수였지만8셀은차이/Fixed비용이0.1%이하였습니다. Baseline−597.84USD가작다는사실은그대로입니다. 재고100/300·수요stress에서는Fixed의종료/주문제약이비교차이를확대했습니다. 이는경제적으로확정된우위나발생확률을뜻하지않습니다.

## 12. 같은 Scenario의 RA−RN 추가 효과

SARIMAX는보관6에서+4,914.04USD로불리해졌고나머지10셀에서는음수였습니다. 범위는초기100의−5,132.16부터보관6의+4,914.04USD입니다. 서비스차이는모든셀에서수치허용내0입니다.

LightGBM은10셀에서추가비용이양수(6,594.68~16,527.66USD)였지만A지연에서는 **−51,361.16USD**, 부족60t감소·Fill+1.5789%p였습니다. 위험목적이재고·업체배분·납기충격완충에간접영향을주었지만수요/납기분포를학습한것이아닙니다. 셀별비용/재고/A·B수량/Fill/Active/Runoff차이는 `risk_increment.csv`에있습니다.

Point와scenario mean을구분한RN−FA비교도각셀의paired파일에있습니다. LightGBM의RN과FA는보관6을제외하면이번총비용이같았고,보관6에서는RN이474.96USD높았습니다. 이차이를CVaR효과로부르지않습니다.

## 13. SARIMAX와LightGBM

FA의LightGBM비용은이grid에서항상SARIMAX보다낮았습니다. RN/RA의모델비용순서는A지연에서반대로바뀌었습니다. A지연의LightGBM−SARIMAX는RN +83,746.32USD, RA +33,977.08USD입니다. 기존모델·모델별scenario분포가함께다르므로알고리즘하나의인과효과가아닙니다. 이결과로기본모델을교체하지않았습니다.

## 14. Active / Runoff / Terminal

FA SARIMAX의Runoff부족20t는초기100/300·부족750/3000·말기0/30·보관6·Bcap60·두Stress **어느셀에서도사라지지않았습니다**. A지연에서는Active100t가추가돼Full120t입니다. Fixed의초기100부족100t와수요Stress부족60t도Runoff에집중됐습니다.

마지막Active말재고/확정pipeline, Runoff월별입고·충족·부족·비용·미착, 최종재고/종료비를각셀의 `runoff_audit.json`에보존했고Full−Active=Runoff를검산했습니다. Runoff길이·새origin·예측horizon을늘려부족을제거하지않았습니다. 단기Active비용만보고정책우월성을주장하지않습니다.

## 15. Horizon / Publication Lag 감사

2개월은H1/H2가격은있지만nativeLP가3개월만허용하며A lead2+maxdelay1의새허용규칙·기존pipeline처리를검증한planner가없습니다. 6개월은H4~H6입력부터없습니다. 두native실행은합성문제에서INVALID_INPUT을확인했습니다.

공표지연2개월은기존t−1 fit/OOF를그대로쓸수없고t−2재라벨링도ModelPrediction이거부했습니다. 새학습·백테스트·OOF재생성이필요하므로미지원으로남겼습니다. 계산결과와제약은 `artifacts/day10/support_audit.json`에있습니다. 불가능한가격을임의생성하지않았습니다.

## 16. 실패·Solver·계약·정보

실행11셀의solver/정보가용성/계약/물리실패0, fallback0, **2,376 OPTIMAL**입니다. 미지원3개는실행성공에포함하지않았습니다. 어떤정책이실패해도같은셀의다른정책은독립시도하고,성공원장은남기되7정책전체순위와paired비교를차단하도록구현했습니다. 불완전비용을38개월총비용으로제시하지않습니다.

기존GLOP9.14.6206·수치허용·폐기0·greedy검사를그대로유지했고모든raw진단·scenario비용·LP원문을압축보존했습니다. 정책은현재q만확정하며Runoff주문과종료미착은모두0입니다. 실제가격경로는모든정책/셀에서동일합니다.

## 17. pytest

신규 **29 passed, 3 warnings in1.42s**, 최종전체 **324 passed, 3 warnings in114.85s**, exit0입니다. 기존295개를모두포함합니다. 경고는기존OR-Tools SWIG의 `__module__` deprecation이며solver실패가아닙니다.

OAT단일변경·ID/값·capacity와비용의solver/engine동시반영·초기재고/말기/부족손계산·공통stress·미래정보차단·cohort일관성·재고보존·수령월단가·Runoff·미지원guard·순위동점/역전·불완전순위차단·압축재현·Baseline변조검출·전체실행셀의합성Holdout변조불변성을검증했습니다. 실제World Bank가격은pytest fixture에없습니다.

## 18. 독립 검산·재현·보존

최종run은 `artifacts/day10/run_20261030T114444326360Z/`, 반복run은 `artifacts/day10/run_20261030T114642620170Z/`입니다. 가상입력은같은run ID의 `data/synthetic/day10/`에있습니다. 두run모두독립검산이통과했고 **481개 결정적 파일이 바이트동일**합니다.

독립검산기는solver/정책을호출하지않고셀별실제수요·cohort지연·수령월가격·capacity·재고·출고·부족·종료·모든비용을재구성했습니다. 기존독립LP수식으로2,376개해를검산하고Baseline21파일·기간별지표·RN/RA동일시나리오·rank/paired/Runoff도확인했습니다. 기존2440파일과안내문서3개원문prefix를보존했습니다.

Manifest는설정/프로토콜사본, Day9·원본·모델·scenario·split·캐시·코드·환경·solver binary·모든출력해시를연결합니다. 생성시각·manifest·solver시간은동일성대상에서제외합니다. 재실행은새run폴더에만저장합니다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_day10_sensitivity.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m food_procurement_intelligence.evaluation.day10 --config configs/day10.toml
.\.venv\Scripts\python.exe scripts/verify_day10_results.py --run artifacts/day10/run_20261030T114444326360Z --repeat artifacts/day10/run_20261030T114642620170Z
```

## 19. 경제적·통계적 한계와 답

이grid안에서는 **SARIMAX RN/RA의서비스가상대적으로안정적**이었고, **LightGBM FA/RN의비용우위는저재고·A지연충격에민감**했습니다. SARIMAX RA−Fixed의작은차이는대부분near-tie이며RA−RN의추가효과도보관비에따라역전됩니다. Fixed는초기재고/수요충격과Runoff에의존했고,FA SARIMAX의종료부족은시험한운영계수범위에서지속됐습니다. 어느정책도전셀의최저비용은아닙니다.

이것은한역사적가격경로·가상운영조건·개발Validation의사후진단입니다. 셀은독립시장표본이아니며순위빈도를발생확률로해석하지않습니다. Day5 coverage미달·OOF tail확률미검증·사후수정snapshot·가정공표시각·2020정의변경·가격만의불확실성·폐기0/3개월계획/Runoff한계를유지합니다. 기업절감액·장기시장CVaR·일반화보장을주장하지않고유리한셀을새기본설정으로선정하지않았습니다.

## 20. Day 11 후속 과제 — 미실행

별도지시후현재모델·정책·운영가정·Runoff·실패규칙·seed/평가경로·지표·Holdout진입조건의최종잠금여부를검토해야합니다. 지원범위내조건의강건성진단과추가horizon/lag재학습이필요한작업을구분하고,필요한추가예측/OOF는별도범위로승인받아야합니다. 단일역사경로로시장CVaR를검증하지않고종료상태의경제적가치·실제업무타당성도검토해야합니다. **Day11과Holdout실행은시작하지않았습니다.**


## 부록 — 전체 셀 비용 및 위험 목적 차이

단위 USD. 가격·시장표본이 서로 다른 독립실험이 아니며 각 행 안에서 정책을 비교합니다.

| Cell | Fixed | FA S | RN S | RA S | FA L | RN L | RA L |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1,351,501.68 | 1,365,914.16 | 1,352,495.76 | 1,350,903.84 | 1,333,962.24 | 1,333,962.24 | 1,348,234.20 |
| inventory_100 | 1,490,401.68 | 1,401,831.12 | 1,388,412.72 | 1,383,280.56 | 1,366,338.96 | 1,366,338.96 | 1,381,240.44 |
| inventory_300 | 1,362,001.68 | 1,331,836.08 | 1,318,775.04 | 1,318,307.76 | 1,301,366.16 | 1,301,366.16 | 1,316,449.80 |
| unmet_750 | 1,351,501.68 | 1,350,914.16 | 1,352,495.76 | 1,350,903.84 | 1,333,962.24 | 1,333,962.24 | 1,348,234.20 |
| unmet_3000 | 1,351,501.68 | 1,395,914.16 | 1,352,495.76 | 1,350,903.84 | 1,333,962.24 | 1,333,962.24 | 1,348,234.20 |
| terminal_0 | 1,349,701.68 | 1,364,114.16 | 1,350,695.76 | 1,349,103.84 | 1,332,162.24 | 1,332,162.24 | 1,346,434.20 |
| terminal_30 | 1,355,701.68 | 1,370,114.16 | 1,356,695.76 | 1,355,103.84 | 1,338,162.24 | 1,338,162.24 | 1,352,434.20 |
| holding_6 | 1,364,761.68 | 1,369,018.32 | 1,359,098.64 | 1,364,012.68 | 1,339,487.28 | 1,339,962.24 | 1,353,786.52 |
| capacity_b_60 | 1,351,501.68 | 1,368,834.72 | 1,352,971.44 | 1,350,903.84 | 1,340,646.72 | 1,340,646.72 | 1,347,241.40 |
| stress_demand_120 | 1,436,101.68 | 1,395,371.52 | 1,381,953.12 | 1,380,361.20 | 1,363,419.60 | 1,363,419.60 | 1,379,947.26 |
| stress_delay_a_1 | 1,348,602.96 | 1,465,295.28 | 1,349,597.04 | 1,348,005.12 | 1,433,343.36 | 1,433,343.36 | 1,381,982.20 |

S=SARIMAX, L=LightGBM.
