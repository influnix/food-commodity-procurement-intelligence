# Day17 상태와 종료 범위

2026-11-01 Asia/Seoul. Source/Seed 계약을 구현하고 합성으로 검증합니다. **실제 source 접근 승인은 없으며 REAL_SOURCE_NOT_VERIFIED / REAL_SEED_RUNTIME_NOT_VERIFIED, Holdout 실행 false를 유지합니다.** Portfolio MVP5/5 COMPLETE는 그대로입니다.

상세는 [Source Scope](DAY17_SOURCE_SCOPE.md)와 [Legacy 계약](DAY17_LEGACY_SEED_CONTRACT.md)를 따릅니다. 새 설정은 `configs/day17.toml`, 새 구현은 restricted_source·forecasting/legacy·uncertainty/provenance_sequential입니다. 실행·독립 검산·freeze 도구와 신규 pytest를 추가했습니다. **기존 파일은 수정하지 않았습니다.**

## 시작 무결성과 접근

Day16 Candidate SHA `20ee930ef7c6ae2d662145ca15015fff0ae27afa9404b85390771170c627bfe7`와 contract27/code114/evidence132개 pin을 먼저 검사했습니다. 새 파일이 추가돼도 그 기존 pin/원본 artifact는 보존합니다. 이전 digest가 새 Day17 코드까지 승인하지는 않으므로 새 Candidate를 발급합니다.

실제 접근은 허용된 저장 A evidence뿐입니다. Day5 forecast/OOF/fit log, Day9 비Holdout Validation evidence, Day16 audit·manifest를 읽고 실제 Legacy192batch·576예측을 구성했습니다.558residual/18target 연결은 기존 확인 범위를 유지합니다. 원천 CSV·제안 export·Bridge·Holdout은 열거나 재해시/생성하지 않았습니다.

Source validator는 허용 path·776개월·7열·HRW·명목 USD/t·공표 가정·vintage/snapshot·원본 metadata link·export/manifest hash·생성 근거를 합성 fixture로 검증합니다. 실제 Source 검증 함수는 IO 이전에 ACCESS_APPROVAL_REQUIRED입니다. Export hash가 아직 없으면 null이며 가짜 승인/hash를 넣지 않습니다.

## 전환과 회귀

Legacy는 RECONSTRUCTED_ASOF·historical live NOT_VERIFIED·native session/input byte proof null입니다. NativeIssuedForecast는 이번 합성 실행에서 실제 native fit·publisher registry·성공 event를 확인한 경우에만 NATIVE_ISSUED로 기록합니다. 두 타입은 공통 point Planning view를 제공하면서 증거 등급을 유지합니다.

기존 Synthetic Legacy192개 복원 후 새 Native44batch·286fit을 수행하며 Day15 horizon release와 완전 Joint 규칙을 상속합니다. 원래 Legacy hash/값 불변, sparse calendar·최근60·최소24·rank·지연공표·raw validity를 검증합니다.22/24·7정책·154/168·132LP 회귀와 독립 회계·반복 실행을 수행합니다. 새 실제 가격 fit/구매 성과는 없습니다.

예비 `probe`는 구현 중 추가한 serializer/lineage 코드 변경을 code-at-start 검사가 감지해 마지막에 실패했습니다. 실패 파일을 보존하고 정본으로 채택하지 않았습니다. 해당 예비 실행의 수치/flow 비교는 통과했지만 정본은 코드 확정 후 새 두 폴더에서 실행합니다. 일부 성공만으로 완료를 판정하지 않습니다.

## 실제 실행 명령

```powershell
.\.venv\Scripts\python.exe scripts/day17/run_tests.py
.\.venv\Scripts\python.exe scripts/day17/integration.py --output artifacts/day17/evidence_a
.\.venv\Scripts\python.exe scripts/day17/integration.py --output artifacts/day17/evidence_b
.\.venv\Scripts\python.exe scripts/day17/verify.py artifacts/day17/evidence_a --repeat artifacts/day17/evidence_b --output artifacts/day17/independent_verification.json
.\.venv\Scripts\python.exe scripts/day17/freeze.py artifacts/day17/evidence_a artifacts/day17/evidence_b
```

현재 `.venv`를 사용합니다. 실제 source reader나 평가 CLI를 활성화하지 않습니다. 새 폴더와 파일명을 사용하며 과거 artifact를 덮어쓰지 않습니다. native_timing.json은 runtime 계측으로 결정적 비교에서 제외하고 모델 output·경고/event·발행 proof·정책/evidence는 비교합니다. package 설치·다운로드·Git commit/push는 없습니다.

신규 tests는776개월 fixture의 경계/가격/열/manifest·type/evidence 변조·archive·source/model/snapshot·no-backfill·성숙도·23/24/59/60/61 rank·새 native·7정책·미래변경·source guard·새 digest·반복을 검사합니다. 기존549개 case를 유지합니다. 정확한 테스트 수·경고·시간, independent/repeat 수·새 Candidate SHA는 `test_results.json`, `independent_verification.json`, `candidate_pointer.json`, `final_qa.json`에 확정 실행 후 기록합니다.

확정 결과는 **기존549+신규64=613 passed, 기존 SWIG 경고3개, pytest579.82초**입니다. Candidate 검증 case 추가 전 신규63개도 선행 통과했습니다. 정본 A/B는 각각 새 Native44batch·SAR22fit/LGB264fit을 성공했고, 과거 동일 입력 대비 point/quantile 최대 가격 차이는 **0**입니다. 실제 World Bank 신규 fit은0입니다.

Legacy192개·576예측, 기존558residual/18target 연결의 계약을 보존했습니다. Calibration132행의 수치/상태, Joint44세트·5632경로,7정책154결정·168원장·132LP는 Day16과 같았고21개 flow CSV는 바이트 일치했습니다. 달라진 pool/planning digest는 명시한 Legacy/Native lineage 변경이며 숫자·표집·정책을 바꾸지 않았습니다.

독립 검산 PASS이며 두 실행의 **111개 결정적 파일이 바이트 일치**합니다. Native timing은 제외했습니다. Run Manifest SHA는 `60e90d09e6389d6ed8519c341e96138ac95368f9ca4072912ae07525a29d890f`입니다. 기존6843개 파일 SHA·Data89개 metadata가 보존됐고 기존 파일 수정은0입니다. 정상 source open/차단시도0, 실제 source/Bridge/Holdout 접근0입니다.

## Readiness

MVP COMPLETE, 방법론·합성 기술·Legacy adapter 계약은 검증 결과에 따라 분리 판정합니다. 합성 통합 성공으로 REAL_SOURCE_EXPORT_VERIFIED나 REAL_SEED_RUNTIME_VERIFIED를 올리지 않습니다. 실제 source는 미승인·미검증입니다. 공표성숙은 실제 UTC와2026-10-31T23:59:59Z를 비교하고 실제 historical release 증거와 구분합니다. USER_AUTHORIZED/HOLDOUT_EXECUTION_ALLOWED는 false입니다.

남은 요청은 정확한776행 export와 생성 근거/외부 hash, 실제 source context의 제한 검증·활성화 승인, pseudo-real-time 한계의 명시적 수용, 그 뒤 최신 실행 Candidate에 연결한 별도 단회평가 승인입니다. 기존801행 전체 로딩/해시와 Bridge/Holdout 권한은 포함되지 않습니다. 과거 vintage/최초 release/live 증거는 계속 NOT_VERIFIED입니다. Python guard는 OS 격리가 아니라는 한계도 유지합니다.

**Legacy를 정직한 RECONSTRUCTED_ASOF로 유지한 연결은 가능하며 합성으로 확인합니다. 실제 source가 없는 상태에서는 실제 runtime 검증을 주장하지 않습니다. Day17 범위에서 종료하며 실제 Holdout은 열거나 평가하지 않습니다.**
