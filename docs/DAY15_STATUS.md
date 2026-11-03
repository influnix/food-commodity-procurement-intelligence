# Day15 방법론 수정·Candidate 재동결 결과

2026-10-31 Asia/Seoul. CR-01은 Day5 horizon Calibration/Day6 full-vector Joint로 분리했고, CR-02는 공용 raw 유효성 검증을 수정했습니다. CR-03은 합성 archive interface만 검증하며 실제 출처는 NOT_VERIFIED로 유지합니다. MVP COMPLETE와 실제 Holdout 잠금을 보존합니다.

상세 구현·영향은 [방법론 수정](DAY15_METHOD_REMEDIATION.md), 상태/비양수 경계는 [유효성 계약](DAY15_VALIDITY_CONTRACT.md), 변경 사유·전후 hash 추적은 [Changelog](DAY15_CHANGELOG.md)를 따릅니다. 기존 결과를 덮어쓰지 않고 새 산출물은 `artifacts/day15/`에 저장합니다.

## 실행과 재현

```powershell
.\.venv\Scripts\python.exe scripts/day15/run_tests.py
.\.venv\Scripts\python.exe scripts/day15/run.py --output artifacts/day15/evidence_a
.\.venv\Scripts\python.exe scripts/day15/run.py --output artifacts/day15/evidence_b
.\.venv\Scripts\python.exe scripts/day15/verify.py artifacts/day15/evidence_a --repeat artifacts/day15/evidence_b --output artifacts/day15/independent_verification.json
.\.venv\Scripts\python.exe scripts/day15/freeze.py artifacts/day15/evidence_a artifacts/day15/evidence_b
```

기존 `.venv`를 사용하며 새 의존성을 설치하지 않습니다. 출력 폴더/검산 파일/테스트 결과/Candidate pointer는 덮어쓰지 않습니다. 반복에는 새 경로를 사용해야 하며 freeze는 그 실제 검산/테스트 hash와 코드에 연결합니다. 테스트 명령의 기존 회귀 안에서는 이전 합성 native fit이 실행되지만 Day15 replay 자체는 새 fit을 호출하지 않습니다. 실제 World Bank 학습·가격 조회는 없습니다.

## 검증 범위

기존451개 테스트를 유지하며 수정 목적에 맞춰 Day11 preservation 테스트와 Day14 결함 테스트의 live 기대값만 갱신했습니다. 신규64개는 NaN/Infinity/문자열/bool·point0/음수·crossing3종·interval역전·endpoint불일치·0/음수 통계 경계·23/24/59/60/61·모델/horizon·중복발행·발행/fit/공표/seed 변조·지연 성숙·실제 접근 차단·새 digest 경계를 검사합니다. 결과는 `test_results.json`에 실제 명령/exit/count/time/guard로 기록합니다. 통과를 추정하지 않습니다.

전체 명령의 확정 결과는 **451+64=515 passed, 기존 SWIG 경고3개, pytest234.52초**입니다. source open/정상 경로 차단시도는0입니다. 별도 선행 검증에서는 신규63개(마지막 Candidate pin 테스트 추가 전)와 Day11/14 관련 회귀도 통과했고, 최종 전체 실행이 신규64개를 포함합니다.

16개 반례·48개 horizon의 새 Calibration은 Day5와 의미상 같아야 합니다. 변경 전 차이4개 horizon은 기존 Day14 artifact로 보존합니다. 저장 합성348개 보정은 point불변,211개 membership·21개 adjustment/bounds·5개 rank 값 변화이며 공식은 같습니다.335 calibrated/13invalid는 실제 관측된 합성 결과이지 고정 목표가 아닙니다.

Joint116세트·228완전 vector·14,848경로·44,544가격행과 toy896쌍을 비교합니다. 7정책을 두 달력에서 재실행하고42개 flow CSV 및 모든 계획/결정/metric을 이전 Day12와 비교합니다.132+216=348개 LP·406개 정책 결정·434개 원장,Runoff 신규q0·수령월가격·최종단회말기·빈종료pipeline을 검증합니다.

독립 verifier는 새 adapter/calibrate/publisher/policy/solver를 호출하지 않습니다. 고정 합성 관측의 history hash, 원본236batch digest와708raw, horizon별 적격 score·window·rank·구간348개, 표집 seed/ratio/가격44,544행, 물리흐름·입고비용·E/CVaR·현재q·말기348계획을 별도 산술로 확인합니다. 두 정본 실행의 파일을 byte 비교하며 허용오차를 확대하지 않습니다. 확정 숫자·manifest/Candidate SHA는 `independent_verification.json`, `candidate_pointer.json`, `final_qa.json`에 기록합니다.

정본 `evidence_a`와 반복 `evidence_b`는 **111개 파일 바이트 일치**입니다. 독립 검산 PASS이며 Run Manifest SHA는 `a21c2178f2477ed918584dbeea5f4fd2926e4e3828f8b58c4ce9e0ea23d712b4`입니다. 기존6275개 중 승인된4개 수정 외6271개 SHA·Data89개 metadata가 일치했습니다.6110개 과거 artifact 파일을 보존했고 Day13 MVP5/5 및 기존 Candidate/Release 자체 SHA도 유지했습니다.

## Readiness 및 승인 경계

| 상태 | 판정 원칙 |
|---|---|
| MVP_COMPLETE | 기존5/5 PASS 유지 |
| TECHNICAL_READY | 새 Candidate의 전체 회귀·합성 E2E·독립/반복 검산이 통과해야 PASS_SYNTHETIC |
| METHODOLOGY_CONSISTENT | CR-01/02 구현 및 사전 계약 회귀 통과 시 PASS_CR01_CR02 |
| CR03_SYNTHETIC_INTERFACE | 합성192batch·변조·공표/성숙·복원 회귀 통과 시 PASS |
| SOURCE_PROVENANCE_VERIFIED | NOT_VERIFIED — 실제 seed/vintage/release/당시 live발행·실가격 신규 연결 미확인 |
| PUBLICATION_MATURE | 실제 UTC now와2026-10-31T23:59:59Z 가정 규칙을 별도 비교; actual release 증거는 NOT_VERIFIED |
| USER_AUTHORIZED | false — 이번 승인은 수정/합성 검증/Candidate 생성까지 |
| HOLDOUT_EXECUTION_ALLOWED | false — 어떤 기술적 PASS도 실제 실행을 열지 않음 |

공표 threshold는2026-11-01 08:59:59 KST입니다. 합성 clock·파일 값 존재·이전 Candidate/Day13 Evidence를 승인으로 사용하지 않습니다. 기존 Day12 Candidate 자체는 보존하되 수정된 코드에 대한 적합성/승인은 이월하지 않습니다. 새 freeze verifier는 Day15 kind·외부 digest·모든 pin을 요구하며 코드 변경/이전 digest는 BLOCKED입니다. 새 Candidate도 사용자 승인이나 real capability를 발급하지 않습니다.

실제 단회평가 승인 요청 전에는 실제 source/vintage/공표 근거와 seed archive 연결의 검증 범위·허용 접근을 먼저 구체화해야 합니다. Historical OOF는 사후 as-of 예측 기록이지 당시 운영 발행의 완전 증명이 아닙니다. 미발행2024-06~08 보충은 금지합니다. 출처 확인 과정에서 코드를 바꾸면 새 회귀·동결이 필요합니다. 실제 clock 성숙 확인 뒤 최신 적합한 digest와 별도 명시 승인이 있어야만 후속 범위를 논의할 수 있습니다.

최신 수정 snapshot·실제 vintage/release 부재·2020-07 정의 경계·시계열 의존성/겹치는 OOF·미달 coverage·경험적 bootstrap 확률·가상 운영·W0·짧은 계획창·Runoff/말기·단일 역사 경로/Validation 선택편향은 남습니다. 이번 수정이 coverage·시장CVaR·기업절감을 보장하지 않습니다. **Day15에서 종료하며 실제 Holdout은 접근·fit·평가·unlock하지 않습니다.**
