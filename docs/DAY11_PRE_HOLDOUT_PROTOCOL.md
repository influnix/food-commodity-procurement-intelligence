# Day 11 최종 평가 계약 — 실제 실행 잠금 유지

2026-10-30 Asia/Seoul. 오늘은 감사·계약 동결·Synthetic Preflight만 수행합니다. 실제 Holdout 조회·모델 fit·평가·unlock은 없습니다. 기술적 READY도 접근 승인이 아닙니다. 기존 파일을 수정하지 않고 새 계약과 감사 결과를 Day11에 보존합니다.

## 선택과 사후 진단의 구분

Day0의 월말 결정·t−1 정보·납품월 지수 연동·가상 운영조건을 유지합니다. Day2의 날짜 정정은 공표 지연과 target 성숙도를 반영한 결정이며 가격 패턴을 보고 Holdout을 선택한 것이 아닙니다. Day4의 두 모델 사양은 당시 신규 비교 전에 고정됐지만 SARIMAX 선호는 같은 Validation의 성능 비교 후 결정됐습니다. MAE는 SARIMAX41.8757, LightGBM48.6620USD/t였으나 Day9~10의 비용 결과는 다른 순서를 보였습니다. 이를 근거로 새 기본모델을 고르지 않습니다.

Day5 OOF/보정은 이미 선택한 사양으로 수행했고 coverage80%를 달성하지 못했습니다. Day9의 Runoff/calendar 추가 제약은 당시 운영결과 전 고정했습니다. Day10은 Day9 결과를 본 뒤의 사후 OAT/Stress 진단입니다. 동결 시점이 있다고 독립 사전등록이나 OOS로 바뀌지 않습니다.

## 달력과 7정책

기존 split 그대로 첫 origin2024-09, 마지막2026-06의22개 결정입니다. 원장은2024-10~2026-09의24개월이며 Active21개월·Runoff2026-07~09의3개월입니다. 마지막 origin의 H1/2/3은7/8/9월입니다. 첫 결정 전 I200·빈pipeline이고 첫 결정월 수요/보관비를 원장에 더하지 않습니다.

Fixed, SARIMAX/LightGBM 각각 FA·RNλ0·RAλ.50의7정책을 모두 평가합니다. α.90, 기존 모델·특징·seed·LP 제약을 유지하고 좋은 정책만 남기지 않습니다. 마지막 결정 후 현재 주문과 미래 계획 q를 모두 금지합니다. 확정 pipeline만 입고/정산하며 최종 미착이 있으면 실패입니다. 38개월 Validation 총액과24개월 Holdout 총액을 같은 기간의 성과처럼 직접 비교하지 않습니다.

## 정보·Bridge·순차 학습

월말 t에 observation_month≤t−1와 available_at≤d_t를 함께 검사합니다. 납품 target t+1/2/3은 SARIMAX 기준 최신관측부터2/3/4-step입니다. 중간 미관측 P_t의 실제값을 쓰지 않습니다. 실제 과거 vintage가 없으므로 최신수정본의 pseudo-real-time 평가라는 한계를 명시합니다.

Bridge2024-09는 평가 target이 아닙니다. 첫 origin2024-09에서는 미공표이며 금지합니다. origin2024-10 이후에는 실제 available_at 조건을 만족하면 과거 feature로 사용합니다. 나중에 공개된 이전 Holdout 관측도 별도 승인된 순차 실행의 당시 이력에만 자동 편입할 수 있습니다. 전체 Holdout을 사전 학습하거나 미공표 label을 쓰는 것은 금지합니다.

## Rolling Refit·OOF·보정·시나리오

매 origin마다 Day4 SARIMAX 고정사양을 t−1까지 expanding refit합니다. LightGBM은 Day3의15개특징과 Day4의3direct/100rounds/seed20261027/thread1을 유지하며 과거 sample o의 전체 target이 `o+3≤t−1` 및 모든 공표timestamp≤d_t일 때만 학습합니다. Hyperparameter search·early stopping·전체표본 전처리는 없습니다.

초기 OOF seed는 기존 Day5의Historical60+Validation36 origin/model입니다. 실제 최종 실행 시 각 row의 fit proof와 현재 공표 여부를 확인해 편입하며, 미발행2024-06~08 origin 예측을 임의로 채우지 않습니다. 이후 새 origin의 raw 예측을 당시 정보로 먼저 발행하고, 실제 target이 공개된 뒤에만 OOF 오류를 release합니다. 이미 평가한 가격도 공개 전에는 학습/보정에 쓸 수 없습니다.

Day5 raw native/quantile 사양을 그대로 사용합니다. 보정은 모델·horizon별 최근60개 성숙 raw OOF, 최소24개, 비음수 초과 score와 ceil((n+1)*.8) order statistic을 유지합니다. 부족은 기존 명시적 raw-interval fallback으로 기록하며 fit 실패는 대체하지 않습니다. 보정 interval을 q10/q90로 재해석하거나 Holdout coverage에 맞춰 재조정하지 않습니다.

Joint pool은 같은 모델·과거origin의 h1/2/3이 모두성숙한vector만 최근60개, 최소24개를 사용합니다. 128개 multiplicative joint OOF ratio draw·가중치1/128, 기존 planning/evaluation base seed와 origin/model/purpose별 파생 규칙을 유지합니다. RN/RA는 동일 Planning세트이며 evaluation경로는 정책에 주지 않습니다. 별도seed는 독립/OOS를 의미하지 않고 origin별3개월경로를 장기실현가격으로 이어 붙이지 않습니다.

## 운영·경제적 회계

Day9 Baseline의 수요100·창고400·A premium2%/lead2/cap80·B8%/lead1/cap100·실현추가지연0/최대1을 유지합니다. 보관3·부족1500·폐기1·말기편차9USD/t, 말기목표200, lost sales, 납품월지수연동입니다. 초기재고취득비는공통 sunk cost, 실제매입비는입고월 한 번, 계획말기비는근사, 실제종료비는전체최종월 한 번입니다. 회수수익은0이며 미착 비용을 숨기지 않습니다.

종료재고 편차 패널티는 실제 재고 경제가치의 추정치가 아닙니다. 잔존가치0·매몰비·짧은계획창·Runoff가정에 민감할 수 있고 Validation에 맞춰 새 잔존가치를 도입하지 않습니다. W=0 보수적LP와 실제엔진의overflow disposal을 구분하며 greedy/물리 검산 실패도 실행하지 않습니다.

## 지표·비교·실패

Primary는 Full-Horizon Total Simulated Procurement Cost(USD)와 Quantity Fill Rate입니다. 비용7성분·부족량/stockout·평균재고·업체배분·Active/Runoff·종료재고/pipeline·실패/fallback·월별paired를Secondary로 함께 보고합니다. 각정책−Fixed, 같은모델RA−RN/FA−RN, 같은정책LightGBM−SARIMAX를 고정합니다. 비용이낮고서비스가낮으면무조건우수라판정하지않고 Pareto와제약을함께보며 우승자하나를선택할의무는없습니다.

월별24개를독립표본으로취급하거나 한경로로시장실현CVaR를추정하지않습니다. PlanningCVaR누적은실현CVaR가아닙니다. 실패월·정책을제외해개선율을만들지않고,첫실패시점·부분로그·불완전범위를남기며전체비교를중단합니다. 기본fallback은없습니다.

## Synthetic Preflight와 실제 준비도의 구분

2000-01부터의 독립 합성가격 규칙 `100+2*(월index mod12)`를 사용합니다. 원천파일·기존가격loader는호출하지않습니다. 실제 모델 fit 대신 명시적 fake backend를 기존SARIMAX/LightGBM 함수에 주입해cutoff·feature/label·출력schema를 검사합니다. 순차OOF·보정/공동bootstrap은Synthetic 전용계약 harness이며 기존의 Validation-only OOF phase guard를 해제한것이아닙니다.

기존 native generator가 Holdout을받는다고 가정하지 않습니다. 실제 store/Bridge capability, 신규origin model/OOF adapter,22/24개월 productionrunner와 실제backend 연결이 검증되지 않았다면 Gate는NOT_READY입니다. 날짜/합성harness 통과만으로 실제 실행을 열지 않습니다.

## 동결·변경·승인

Freeze Manifest는실제config/code/metadata파일의SHA-256을핀합니다. 원천가격파일은열지않고이전검증hash·메타데이터만재사용하며,현재원천byte재검증여부를구분합니다. Manifest 자체의digest는별도파일과최종보고에기록합니다. hash가달라지면이전freeze를무효로보고Gate는BLOCKED입니다.

READY는기술적준비도일뿐입니다. 실제접근은동결digest에연결한사용자명시승인과별도작업이필요합니다. 오늘은어떤상태에서도실제unlock API를제공하지않습니다. 미해결production확장은새freeze와Synthetic재검증을필요로하며실제Holdout가격/성능은NOT_VERIFIED로남깁니다.
