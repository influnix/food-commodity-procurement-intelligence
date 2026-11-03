# 최종 단회평가 Release Protocol — 현재 비실행 계약

현재 **Actual Execution Permission=false**, 실제 source permit/reader·실제 seed runtime adapter·실제 평가 CLI는 구현/승인되지 않았습니다. 이 문서는 후속 평가의 순서와 금지 조건입니다. Day16에서 실제 capability를 켜지 않습니다. 합성 검증용 최종 진입점은 `evaluation.final_contract.prepare_final_synthetic_stream`이며 실제 World Bank source를 거부합니다.

## 독립 Gate

| Gate | 필요한 증거 | 현재 의미 |
|---|---|---|
| A Candidate Integrity | 사용자와 외부에서 대조한 digest, 모든 contract/code/evidence SHA | 새 Day16 Handoff의 무결성. 이전 Day15 digest로 새 wiring 승인 불가 |
| B Methodology Consistency | HorizonSequentialOOF 명시 선택, Day5 calibration/Day6 Joint·raw validity 회귀 | 합성 연결 PASS |
| C Technical Readiness | 기존 전체pytest·22/24·7정책·독립 회계·반복 | PASS_SYNTHETIC; 실제 adapter readiness와 별개 |
| D Source/Seed | 실제 source/legacy seed 출처·허용된 input 검증, pseudo-real-time 한계 명시 수락 | ACCESS_APPROVAL_REQUIRED / NOT_VERIFIED 잔존 |
| E Publication Maturity | 실제 UTC clock≥2026-10-31T23:59:59Z | 가정상 마지막 target 성숙. 실제 역사 release 증거와 별개 |
| F Explicit User Authorization | **최신 적합한 실행 digest**, 입력/월/열/역할·단회 범위에 대한 명시적 승인 | false |
| G Actual Execution Permission | A~F와 검증된 실제 runtime adapter/capability, 미사용 single-run ID | 현재 무조건 false |

G는 기술 READY·clock·로컬파일 존재·승인 ID 문자열만으로 true가 되지 않습니다. Runtime capability가 없는 상태에서 승인 문자열을 넘겨도 실행하지 않습니다. 합성 clock을 E에 사용하지 않습니다. Gate 출력은 `readiness_matrix.json`과 최종 preflight metadata로 보존합니다.

## 현재 사용 가능한 정확한 명령

기존 `.venv`와 루트를 사용합니다. 첫 명령은 Handoff pointer를 읽는 metadata 동작입니다. pointer의 SHA는 최종 보고에서 받은 외부 digest와 별도로 대조해야 합니다.

```powershell
$handoffPointer = Get-Content -LiteralPath artifacts/day16/candidate_pointer.json -Raw | ConvertFrom-Json
.\.venv\Scripts\python.exe scripts/day16/runbook.py --mode preflight --candidate $handoffPointer.candidate --expected-sha $handoffPointer.sha256 --output artifacts/day16/runbook_preflight.json
```

출력이 이미 있으면 덮어쓰지 않고 새 파일명을 사용합니다. 이 명령은 source를 읽지 않고 metadata gate만 검사합니다. **실제 평가를 수행하는 명령은 현재 NOT_IMPLEMENTED입니다.** 아래 actual 모드는 비실행 계약의 거부를 확인하는 CLI이며, candidate/source/fit/ledger 접근 전에 항상 HoldoutLockedError로 중단합니다. Day16에서 실행할 필요가 없습니다.

```powershell
.\.venv\Scripts\python.exe scripts/day16/runbook.py --mode actual --candidate $handoffPointer.candidate --expected-sha $handoffPointer.sha256 --authorization-id USER_APPROVAL_REQUIRED --run-id ONE_SHOT_ID_REQUIRED
```

이 문자열을 실제 평가 명령으로 소개하지 않습니다. 향후 실제 adapter/capability 구현과 검증은 별도 승인 범위이며 코드/계약 변경 후 새 실행 Candidate·새 digest 승인이 필요합니다. 현재 Handoff SHA가 미래 미구현 실행 코드를 승인하지 않습니다.

## Input 경로·역할 계약

현재 허용 입력은 `configs/`·명시된 manifest·Day5 비Holdout seed 파일·Day9 저장 Validation evidence·기존 합성 native artifact입니다. 원천 CSV의 경로·월·열 요구는 [Source 감사](DAY16_SOURCE_SEED_AUDIT.md)에 있습니다. 실제 input export는 아직 생성/검증되지 않았으며 오늘 허용된 실제가격 경로 목록은 비어 있습니다.

후속 실제 실행을 위해 제안하는 분리 입력은 다음과 같습니다. 파일은 현재 존재한다고 주장하지 않으며 별도 승인 후 준비·hash·freeze해야 합니다.

| 제안 경로 | 범위/역할 |
|---|---|
| `data/approved_exports/final/wheat_history_through_202408.csv` |1960-01~2024-08·776개월. 첫 origin fit 이력과 실제 seed/source 확인 |
| `data/approved_exports/final/wheat_sequential_releases_202409_202609.csv` | Bridge 및 후속 관측. source controller/evaluator만 소유하고 origin별 조건 충족 후 공개 |
| `artifacts/approved_seed/<verified_archive_id>/` | 실제 Day5 Historical60+Validation36의 legacy proof 보존 adapter 결과. 가짜 native/session/history 증거 추가 금지 |

평가 엔진은 승인된24개월 실제 정산가격을 소유할 수 있지만 정책/예측기는 현재까지 공개된 history·예측·운영 context만 받습니다. 전체 원천가격을 정책에 넘기지 않습니다. 모든 실제 입력의 snapshot·vintage·assumed/actual timestamp 근거를 고정합니다.

## 동결할 평가 조건

Fixed, FA/RN/RA SARIMAX, FA/RN/RA LightGBM의7정책입니다. Decision2024-09~2026-06·22개, Ledger2024-10~2026-09·24개월, Active21·Runoff3입니다. I200·빈pipeline, 수요100, 기존 A/B lead/cap/premium, α.90/λ0,.50, Joint128, 고정seed·cost·lost sales·말기목표/비용·Total Cost/Fill Rate를 유지합니다.

첫2024-09 origin에서는 Bridge2024-09를 볼 수 없습니다. 이후 관측월≤t−1와 available_at≤d_t를 동시에 충족하면 과거 feature로만 허용합니다. Bridge는 ledger target이 아닙니다. 이미 정산한 Holdout 관측도 실제 공표 조건을 만족한 이후에만 학습·보정에 사용합니다.

## 향후 단 한 번의 실행 순서

1. 추가 source 확인의 허용 경로/월/열과 실제평가 controller/evaluator 접근을 명시 승인받고, source/seed 및 adapter를 검증합니다. Pseudo-real-time 한계 수락을 기록합니다. 과거 vintage 부재를 PASS로 바꾸지 않습니다.
2. 실제 연결 코드가 바뀌면 전체회귀·동일 합성 dress·독립 검산·새 Candidate 동결을 수행합니다. 승인받을 digest는 그 **새 실행 Candidate**입니다. 실제 실행 명령도 구현·검증한 정확한 경로와 인자로 runbook을 갱신합니다.
3. 사용자에게 최신 적합한 digest·고정 입력·22/24 달력·실패/공개/재실행 규칙을 제시하고 별도의 단회 평가 승인을 받습니다. 승인 시점과 범위를 저장합니다.
4. 실제 UTC로 E를 다시 확인하고 A~G를 평가합니다. 마지막으로 승인 digest와 모든 pin을 재검증합니다. 불일치·부족 증거·미승인은 즉시 중단합니다.
5. 새 단회 ID를 exclusive-create로 예약하고 승인 ID·Candidate·환경·입력 hash를 연결합니다. 이미 소비/실패한 ID와 기존 결과 경로를 재사용하지 않습니다. 제안 결과 루트는 `artifacts/final_holdout/<single_run_id>/`이며 현재 생성하지 않습니다.
6. 기존 seed를 공개 조건으로 필터링합니다. 미발행2024-06~08을 채우지 않습니다. origin마다 공개→과거자료만 native fit→immutable 발행→horizon Calibration/완전 Joint 갱신→동일모델 RN/RA Planning 공유→독립7정책 현재q 확정 순서를 지킵니다. 기존 source와 미래 target을 forecast 함수에 주지 않습니다.
7. 동일 실제 외생 경로를 evaluator에 한 번 고정합니다. 정책은 독립 I200/빈pipeline에서 시작합니다. 납품월 가격×premium 비용을 수령월 한 번 계상하고 Runoff에는 provider/정책을 호출하거나 새 q를 만들지 않습니다. Terminal은2026-09 한 번만 계상하고 종료 pipeline이 비어야 합니다.
8. Fit·유효성·pool·출처·solver·재고·회계 실패가 하나라도 있으면 즉시 중단하고 시점/원인/prefix 로그를 남깁니다. 성공 정책·부분기간만 전체 성과처럼 비교하거나 fallback/자동재실행하지 않습니다.
9. Manifest·환경·source 접근·공표 로그·예측·OOF·scenario·154decision·168ledger·132계획과 실패 상태를 저장합니다. 저장 결과로 독립 비용/재고/시점/목적 검산을 수행합니다. 검산이 실패하면 결과를 공개하지 않습니다.
10. 공개 전 Manifest와 승인 digest를 확인하고 성공/실패·가상운영·단일 snapshot/한경로 한계를 함께 보고합니다. 재실행은 원인·새 코드/계약·이미 본 Holdout의 영향을 명시한 **별도 승인**이 필요하며, 결과를 본 뒤 바꾼 것은 탐색 분석으로 표시합니다.

현재 위 절차의 실제 runtime·승인은 준비되지 않았습니다. 문서·합성 검증 완료와 실제 최종 연구평가 가능성을 구분합니다.
