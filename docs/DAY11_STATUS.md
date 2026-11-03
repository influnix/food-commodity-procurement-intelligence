# Day 11 실행 결과 — Pre-Holdout Audit & Freeze

2026-10-30 Asia/Seoul. **Day11 감사·동결·합성 검증을 완료했습니다. 실제 Holdout 실행 준비 상태는 NOT_READY이며 잠금을 유지합니다.** 실제 Holdout/Bridge 가격값 조회·평가·unlock, 새 실험의 모델 학습·튜닝, 외부 다운로드, 설치, Git commit/push는 없습니다.

## 1. 생성·수정 파일

- `configs/day11.toml` — 최종 달력·정책·정보·OOF·시나리오·운영·지표·실패 계약.
- `evaluation/day11.py`, `pre_holdout_audit.py`, `synthetic_preflight.py`, `release_gate.py` — 모두 `src/food_procurement_intelligence/` 하위의 신규 모듈입니다.
- `tests/test_day11_release_gate.py`, `scripts/run_day11_tests.py`, `scripts/verify_day11_results.py`.
- [최종 계약](DAY11_PRE_HOLDOUT_PROTOCOL.md), [Release Gate](DAY11_RELEASE_GATE.md), [18개 한계](DAY11_LIMITATIONS.md), 현재 상태 문서.
- README, ROADMAP, AGENTS는 이전 내용을 보존하고 Day11 기록만 덧붙였습니다.
- 모든 신규 실험 결과는 `artifacts/day11/`, 합성 입력은 `data/synthetic/day11/`에 분리했습니다. 전체 파일 목록은 `artifacts/day11/file_inventory.json`을 따릅니다.

## 2. 전체 파이프라인 감사

Raw/원본 provenance는 기존 검증 metadata/hash를 재사용했습니다. Availability → Features → Training의 t−1·공표timestamp·성숙한 vector 조건을 확인했습니다. Forecast → OOF → Joint Scenario는 과거에 발행한 예측과 현재 공개된 target만 사용하는 계약입니다. Planning LP에는 Planning만 전달하고, 정책은 공개 context와 현재 주문만 실행합니다. 원장 엔진은 입고·수요·재고·비용을 정산하고 evaluator와 정책의 정보 경계를 유지합니다.

실제 source 위치와 line 증거는 정본 run의 `pipeline_audit.json`에 있습니다. 개발 store의 최종 origin/Bridge 차단, 저장 예측 adapter의 Validation 한정, OOF phase/partition 제한, 공동 generator의 Validation 달력 제한을 발견했습니다. Day9 CLI는 Validation 기간과 fixed36 집계에, Day10 보고는 `ledger[34]` 등 35 Active/38개월 구조에 의존합니다. 공통 실행 core는 합성 22/24 달력을 지원했지만 기존 CLI를 Holdout에 연결할 수 있다는 뜻은 아닙니다.

## 3. Final Evaluation Protocol

Day4 모델·Day3 특징·기존 seed/OOF/보정/시나리오/LP/위험 설정과 Day9 운영기준을 유지합니다. Day4의 MAE는 SARIMAX41.8757, LightGBM48.6620USD/t였습니다. Day9~10의 운영비용 순서와 다르다는 사실, Validation에서 이미 선택·비교했다는 편향, Day10의 사후 진단 성격을 기록했습니다. 이를 이용한 새 기본모델·정책 선택은 없습니다.

## 4. Holdout 달력

| 구분 | 기간 | 수 |
|---|---|---:|
| Decision origins | 2024-09~2026-06 | 22 |
| Full ledger | 2024-10~2026-09 | 24 |
| Active ledger | 2024-10~2026-06 | 21 |
| Runoff | 2026-07~2026-09 | 3 |
| 마지막 origin targets | 2026-07/08/09 | 3 |

가격값 없이 날짜 계산만으로 기존 split과 일치함을 검증했습니다. 이전 Validation의 38개월 총액과 최종 24개월 총액을 직접 같은 기간의 성과처럼 비교하지 않습니다.

## 5. Bridge·공표 규칙

Origin t에서 `observation_month≤t−1`과 `available_at≤decision_at(t)`를 모두 검사합니다. 첫2024-09 결정의 cutoff는2024-08입니다. Bridge2024-09는 성과에서 제외하며 첫 결정에서는 금지, 2024-10 이후 공개 조건 충족 시 과거 이력이 됩니다. 합성 지연 timestamp를 넣어 달력상 과거라도 미공표면 차단됨을 테스트했습니다. 실제 Bridge 값은 읽지 않았습니다.

현재 공표 timestamp는 실제 역사적 release가 아닌 다음 달 말 가정입니다. 마지막2026-09 target도 이 가정에서는2026-10-31 말에 가용해집니다. 오늘 모든 실제 target이 평가용으로 공표됐다고 판정하지 않았습니다. 후속 실제 평가의 assessed_at과 모든 target 공표 조건도 별도 확인해야 합니다.

## 6. Rolling Refit

매 origin의 공개 이력으로 기존 SARIMAX를 expanding refit하고, LightGBM은 기존15특징·3direct·100rounds·seed·thread1을 유지합니다. 과거 학습 origin o의 완전 vector는 `o+3≤t−1`와 모든 공표timestamp≤현재결정시각 조건을 충족해야 합니다. SARIMAX의4개 model step 중2/3/4를 납품 H1/2/3으로 사용합니다. 사전 전체 Holdout fit은 금지하며 순차적으로 공개된 이전 target의 사용만 별도 승인된 평가 절차에서 허용합니다.

오늘 native 함수에는 학습하지 않는 fake backend만 주입했습니다. SARIMAX22회, LightGBM의3direct 출력66개를 통해 입력 cutoff·maturity·출력 정합성을 검증했습니다. 새 실험의 실제 모델 학습은0회이며 기존 회귀 테스트의 오래된 toy fit은 재실행했습니다. 신규 origin의 실제 backend 연결은 NOT_VERIFIED입니다.

## 7. OOF·보정·공동 시나리오

실제 실행의 초기 seed pool은 기존 Day5 Historical60+Validation36 origin/model이며 당시 fit proof와 현재 공표 여부로 필터링합니다. 미발행2024-06~08 예측을 임의로 보충하지 않습니다. 새 예측을 먼저 발행하고 target이 공개된 뒤 잔차를 편입합니다. Horizon별 보정은 최근60·최소24, 공동 vector는 같은 과거 origin의 H1/2/3 전체 성숙 후 최근60·최소24입니다. 기존 finite-sample80% 보정 규칙과 raw fallback 기록을 유지합니다.

128개 multiplicative joint ratio draw, 가중치1/128, Planning seed2026102901/Evaluation seed2026102902와 origin/model/purpose별 파생 규칙을 고정했습니다. RN/RA의 Planning 세트는 같습니다. Evaluation은 정책에 전달하지 않습니다. 별도 seed의 같은 pool 재표집은 독립/OOS가 아닙니다.

오늘의 합성 pool은 명시적 fixture 전용 harness입니다. 합성 raw interval `.9×point~1.1×point`는 테스트 입력이며 실제 Day5 구간을 대체하는 사양이 아닙니다. Production OOF/generator의 phase 제한은 유지했고 연결 지원을 검증했다고 보고하지 않습니다.

## 8. 7정책·지표

Fixed와 SARIMAX/LightGBM 각각 FA·RNλ0·RAλ.5의7정책을 모두 유지합니다. α=.90입니다. Primary는24개월 총 가상 조달비용과 수량 Fill Rate입니다. Secondary는 비용 성분, 부족·stockout·평균재고·업체배분·Active/Runoff·종료재고/pipeline·실패/fallback·월별 paired입니다. 각정책−Fixed, 같은모델RA−RN/FA−RN, 같은정책의모델차를 비교하며 비용/서비스 Pareto와 제약을 함께 보고합니다. 확정적 우승자를 고르지 않습니다.

## 9. 초기조건·말기

초기200t·빈pipeline·수요100·창고400·A2%/lead2/cap80·B8%/lead1/cap100·추가지연0/최대1·보관3·부족1500·폐기1·말기편차9/목표200·잔존가치0·lost sales·납품월지수연동을 유지합니다. 초기재고 취득비는 공통 매몰비입니다. 구매비는 입고월 한 번, 계획말기비는 목적 근사, 실제말기비는 전체 최종월 한 번입니다. 마지막 결정 후 신규 q와 미래 계획 q도0이며 미착pipeline이 남으면 실패합니다. 종료편차비는 실제 재고 경제가치를 추정한 것이 아닙니다.

## 10. Synthetic Preflight

실제 가격과 독립인 `100+2*(2000-01부터 월index mod12)`의321개월 fixture를 생성했습니다. 공표정보와 synthetic provenance를 보존하며 운영수요는100입니다. 정본·반복 각 실행에서7정책 모두22결정/24원장을 완료했습니다. 각132개 LP가 OPTIMAL이고, 독립 검산은154결정·168원장행·44 fit proof·44 pool proof를 확인했습니다.

23개 필수 검증 항목은 run 결과와 테스트·독립 검산으로 점검했습니다. 달력/Bridge/공표, feature·label maturity, 완전 joint vector, purpose·확률합, 동일RN/RA경로, 현재q·납기·capacity·재고/pipeline·입고월가격·비용합·Runoff·말기를 확인했습니다. INFEASIBLE 주입 시 중단·빈비용원장·비교거부, 미공개 합성 미래값 변경 시 FA/RN/RA의 과거 주문 불변성도 테스트했습니다.

원천접근 guard 안에서 테스트·runner·검산을 실행했습니다. 실제 원천 open0건이며 runner/검산의 차단 시도도0건입니다. 별도 음성 테스트의 builtin/path/io/os 접근 시도는 reader 이전에 거부됐습니다. 이 Python API 감시는 OS 보안 경계나 이미 열린 fd/C extension의 모든 접근을 감시하는 보안 도구는 아닙니다.

## 11~12. Gate와 미해결 사항

최종 상태는 **NOT_READY**입니다.14개 계약·감사·검증 조건은 PASS, 다음5개는 NOT_VERIFIED입니다. 실제 Holdout 접근이나 성능으로 이 항목을 추측하지 않았습니다.

| Gate 항목 | 별도 보완 범위 |
|---|---|
| production_sequential_store_bridge | 기존 개발 잠금을 보존한 허가 기반 순차 store/Bridge capability |
| production_new_origin_forecast_adapter | 신규 origin별 모델 발행·저장·입력 adapter |
| production_oof_scenario_phase_support | 공개된 이전 target의 OOF release/구간/공동pool 순차 연결 |
| production_final_runner_metrics_22_24 | Validation 상수에 의존하지 않는22/24 실행·집계·실패 경로 |
| production_new_origin_backend_integration | 새 origin 실제 backend·구간·OOF 연결의 합성 검증 증거 |

누락 증거는 NOT_READY, hash/접근 무결성 위반은 BLOCKED, 전부PASS여도 READY는 기술적 상태일 뿐입니다. 모든 상태에서 `holdout_locked=true`, `actual_holdout_execution_allowed=false`입니다.

## 13. Freeze

- 정본: `artifacts/day11/run_20261030T141429269521Z/final_freeze_manifest.json`
- SHA-256: `163a74d3387743b882651e98fa434d1cc4113d3e5eac98e3fde08e53e24b78be`
- 반복: `artifacts/day11/run_20261030T141529837060Z`
- 27개 계약파일·70개 code/test/script·6개 metadata 파일을 실제 SHA-256으로 핀했습니다. 원천스키마 JSON과 두 package lock도 포함합니다.
- Raw SHA `ea1c350827878ea3bbe30e3cda16a13fd3bd5b409b8458940dc94a36b5a33154`와 CSV hash는 이전 검증 기록을 재사용했습니다. 오늘 원천 byte를 열어 재해시하지 않았습니다. 공식 URL·UTC·크기·단위는 기존 출처 기록을 재사용하고 license는 핀한 WORLD_BANK_SOURCE에 보존했습니다.
- 변경된 계약/Manifest는 이전 digest로 승인할 수 없습니다. 임시 이전 Freeze가 실제로 BLOCKED되는 것도 확인했습니다. 현재 정본과 반복본은 각각 자신이 핀한 계약에 대해 검증됐습니다.

## 14. pytest

명령: `.\.venv\Scripts\python.exe scripts/run_day11_tests.py` — 내부 `pytest.main(['-q'])`를 source guard 안에서 실행했습니다. **기존324+신규35=359 passed, 경고3, wrapper 실행 104.06초**입니다. SWIG deprecation 경고3개이며 실패/skip은 없습니다. 실제 명령·exit0·개수·접근 감사는 `artifacts/day11/test_results.json`에 있습니다.

## 15. 독립 검산·반복 재현

두 최종 run 각각 `python scripts/verify_day11_results.py <run> --output <Day11 검산 JSON>`으로 저장된 주문·납기·입고가격·물리흐름·비용·말기, LP의 공유변수/목적/E/CVaR, seed와 bootstrap draw를 다시 계산했습니다. 검산은 solver/정책을 호출하지 않습니다. 53개 결정적 run 파일+2개 합성 입력=55개가 바이트 일치합니다. UTC/run 경로를 포함한 Manifest·digest와 solve timing은 비교에서 제외했습니다. 계약/code/metadata 해시 목록은 서로 같습니다.

초기 병렬 반복 시 UTC ID 충돌로 두 번째 프로세스가 mkdir에서 거부됐습니다. 덮어쓰기는 없었으며 원인 기록을 남기고 순차 재실행했습니다. 검증 전 임시 run과 무효화된 중간 Freeze도 이력으로 보존하며 최종 정본과 혼동하지 않습니다.

## 16. Day0~10 보존

기존3411개 비Data 파일 SHA가 모두 일치합니다. 기존 Data58개는 size/mtime와 이전 기록 hash만 유지 확인했으며 오늘 byte hash 재검증을 했다고 표현하지 않습니다. README/ROADMAP/AGENTS의 기존 prefix3개도 일치합니다. 패키지16pin·Python3.11.5·OR-Tools9.14.6206/GLOP와 solver binary hash를 기록했으며 설치는0입니다.

## 17. 해석 한계

[18개 한계](DAY11_LIMITATIONS.md)를 모두 기록했습니다. 수정 snapshot/역사적 vintage 부재·가정 공표시각·2020-07 HRW 정의 변경, 단일 품목과 가상운영,80%미달 coverage·의존 OOF·미검증 시나리오 확률·가격만 확률화,3개월/공유주문/W0/말기근사, Validation 선택편향·사후 Day10·단일 Holdout 경로가 남습니다. 이 통계적 한계를 기술적 Gate 통과로 해소했다고 표현하지 않으며 실제 기업 절감이나 시장 CVaR 보장을 주장하지 않습니다.

## 18~19. 승인과 다음 범위

먼저 실제 가격 없이 위5개 production gap을 별도 승인 범위에서 구현·검증해야 합니다. 그 결과는 새 freeze와 전체 회귀·독립검산을 거쳐야 합니다. 실제 최종 실행은 **해당 새 digest에 연결한 사용자의 명시적 Holdout 접근·단회 평가 승인**이 추가로 필요하며, 그 전에는 열지 않습니다. 본 문서는 승인을 요청하거나 자동 부여하지 않습니다. 후속 구현과 실제 평가를 오늘 시작하지 않았습니다.

**현재 최종 Holdout을 평가할 준비가 됐는가? NOT_READY입니다.** 합성 계약 검증은 완료됐지만5개 production 연결과 최종 공표/평가시계 검증이 남아 있습니다. 통계적·경제적 한계도 그대로입니다. Day11 범위에서 종료하고 잠금을 유지합니다.
