# Day15 방법론 수정 및 회귀

2026-10-31 Asia/Seoul. 사용자 지시에 따라 Day14 MDR 권고안 A를 구현했습니다. [Day5 사전 설계](DAY5_UNCERTAINTY_DESIGN.md)의 horizon Calibration과 [Day6](DAY6_DESIGN.md)의 full-vector Joint를 유지하는 것이 근거입니다. Validation 성과를 새로 확인하거나 사양을 선택하지 않았습니다. 실제 원천·Bridge·Holdout은 계속 잠겨 있습니다.

## CR-01 독립 Lifecycle

새 [HorizonSequentialOOF](../src/food_procurement_intelligence/uncertainty/horizon_sequential.py)는 기존 Day12 SequentialOOF의 Joint 구현을 재사용하며 Calibration pending/released 집합만 분리합니다. 기존 Day12 클래스와 설정은 변경하지 않습니다. 새 adapter는 [day15 설정](../configs/day15.toml)이 지정한 수정 경로입니다. 과거 Day12 계약은 역사적 기준이며 현재 승인된 수정안과 혼동하지 않습니다.

각 과거 발행(o,h)은 발행 digest·동일 모델·정확한 target=o+h·당시 fit cutoff/publication·현재 source/session을 검사합니다. 현재 t에 `o+h≤t−1`, 해당 actual의 `available_at≤decision_at(t)`, valid raw interval을 만족하면 다른 h를 기다리지 않고 score를 공개합니다. 새로운 발행 전 tick을 수행하므로 현재 forecast의 실제값을 소급 사용할 수 없습니다. 모델·horizon·raw method를 분리하고 중복과 오염을 거부합니다.

score=max(L−y,y−U,0), 최근60개, 최소24개, k=ceil((n+1)×.8)의 1-based order statistic을 그대로 사용합니다. 보간·축소·point 변경은 없습니다. 부족한 valid raw만 명시적 raw fallback을 허용합니다. Calibration 후 양끝을 q10/q90로 재해석하지 않습니다.

Joint는 `o+3≤t−1`와 모든 actual 공표를 계속 요구합니다. 완전 벡터 최근60·최소24, raw actual/point의 세 비율을 함께 표집하는128경로, seed·가중치·Planning/Evaluation 경계를 보존합니다. Calibration interval을 Joint 입력으로 사용하지 않습니다.

## Day14 반례 회귀

기존16개 toy 반례와 입력 생성 코드를 재사용합니다. 새 adapter와 Day5 원래 calibrate의 count·선택 origin·score·rank·status·adjustment·bounds가 48개 horizon에서 일치해야 성공입니다. Day14에 달랐던4개 horizon 행은 원래 artifact에 보존하고 수정 후 Day5와 일치시킵니다. 서로 다른 API의 tuple/list는 JSON 구조로 정규화해 비교하며 수치/해시를 억지로 맞추지 않습니다.

H1 단독/H1·H2 성숙 시 공개, H3 공표 지연, d_t 정확히와+1초,23/24/59/60/61개·최근60 갱신, 미발행 origin, 모델 분리, crossing score 제외 및 유효 Joint point 보존을 검증합니다. 기존896쌍 toy 경로는 수정 후에도 가격·표집 origin·seed가 같아야 합니다.

## CR-02

[유효성 계약](DAY15_VALIDITY_CONTRACT.md)의 point/quantile/interval 검증으로 NaN q50이 보정 후 valid가 되던 결함을 수정했습니다. Day5와 기존 SequentialOOF도 공용 interval_usable을 통해 동일한 오류 차단을 받습니다. 유한 비양수 통계 경계는 flag와 함께 보존하도록 native ingress를 정합화했습니다. 실제가격과 Joint용 point·생성 가격의 양수 요구는 그대로입니다. 재정렬/clip·새 모델·튜닝은 없습니다.

## 저장 Day12 합성 결과 대비 영향

236batch·708raw·crossing14·완전 vector228은 기존 기록을 그대로 사용합니다. 기존 raw 발행 파일의 외부 SHA와 immutable batch digest를 확인한 뒤 **새 fit 없이 replay**합니다. Synthetic 관측도 동일한 Day12 DGP/seed로 재구성하고, 독립 검산에서 당시 history hash와 맞춥니다. 실제 archive의 가격/잔차는 읽지 않습니다.

수정 전후348개 보정 row에서 point는 모두 동일합니다.211행의 pool membership이 달라졌고,21행은 adjustment/구간 양끝,5행은 rank 값이 달라졌습니다. rank의 **공식**은 바뀌지 않았으며 n/구성원 차이에 따른 값의 변화입니다. 상태는335 calibrated/13 invalid로 같았지만 같아지도록 강제하지 않았습니다. 원래 저장 raw validity에는 변화가 없었습니다. 상세 차이는 새 실행의 `methodology_impact.json`에 원인별로 분리했습니다.

116개 origin/model Joint 세트·228개 full vector·14,848개 경로·44,544개 horizon 가격행은 기존과 동일해야 합니다. Crossing14개를 정상 quantile로 재분류하지 않습니다. Joint는 raw point와 ratio에만 의존하므로 보정 변경이 직접 정책 입력을 바꾸지 않는다는 구조를 실제 합성 E2E로 확인합니다.

## 7정책·운영 계약

새 합성 실행은 최종형22결정/24원장/21Active/3Runoff와 Validation형36/38/35/3을 각각7정책으로 재실행합니다.132+216=348개 LP 계획,406개 정책 결정,434개 월별 원장을 확인합니다. 기존 Day12와42개 발주·입고·원장 CSV를 바이트 비교하고 계획·결정·지표도 의미상 동일성을 확인합니다. 같은 모델 RN/RA Planning 세트도 같습니다. 실패/변화가 있으면 전체 비교를 중단하고 원인을 격리합니다.

Split·모델·15특징·h1/2/3·128경로·α.90/λ0,.50·seed·I200/빈pipeline·업체lead/cap·수요100·비용·수령월가격·Runoff·말기 단회계상·Full Cost/Fill Rate는 변경하지 않았습니다. Day9/10 실제 Validation 저장 Baseline과 Day13 대표2정책/MVP5조건은 보존합니다. 오늘 새 실제 Validation 성과나 실제 Holdout 성과는 계산하지 않습니다.

## CR-03 합성 Archive

복원은 externally pinned archive digest, 모델명, 모델별60 historical+36 validation 원래 달력, source/knowledge/native backend, 원래 session, immutable batch digest, original issuance/history/model/feature proof와 fit cutoff/publication을 확인합니다. 복원된 session은 원래 값을 보존하되 현재 발행은 현재 session이어야 합니다. 새 adapter는 모든 batch를 검증한 뒤 복원하여 변조가 중간 상태를 남기지 않게 합니다.

합성192batch 복원과 성숙 후192Joint vector·566유효 horizon score(10개 seed crossing 제외)를 확인합니다. hash·누락 batch·source·knowledge·model·session·history/model proof·horizon·fit·publication·발행 증거 변조를 거부합니다. 지연된 H3가 H1/H2 Calibration을 막지 않지만 Joint는 지연되는 것도 확인합니다. 2024-06~08 미발행 forecast를 보충하지 않습니다.

**Synthetic Interface PASS와 Real Provenance NOT_VERIFIED는 별개입니다.** 실제 과거 운영 발행·vintage·release timestamp·실가격 seed adapter 연결/실제 신규 fit은 이번에 입증하지 않았습니다.

## 새 Candidate

CR-01/02 수정과 전체 회귀·두 실행·독립 검산을 새 Candidate에 연결합니다. Day12 Candidate와 Day13 Evidence Release 파일을 덮어쓰지 않습니다. 이전 digest로 새 코드를 승인하는 동작은 BLOCKED입니다. Candidate READY는 합성 기술/방법론 계약의 준비 상태일 뿐 사용자 승인이나 실제 Holdout 실행 허용이 아닙니다.
