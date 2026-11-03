# Private release status

2026-11-03 Asia/Seoul. 최초 업로드 버전은 **PORTFOLIO_PRIVATE_RELEASE_COMPLETE**입니다. PRIVATE 저장소의 실제 원격 CI 성공을 확인했습니다. 이 문서를 갱신한 후속 Commit에도 같은 CI를 적용하며 최종 main 상태는 저장소의 최신 Workflow 결과를 기준으로 확인합니다.

MVP5/5 PASS·기존 Validation·방법론/합성 결과는 유지합니다. Source Export·Seed Runtime은 미검증, Day18 ACCESS_APPROVAL_REQUIRED, 실제 Bridge/Holdout 접근·fit·평가·Unlock은 비활성입니다.

[집계 Evidence](../evidence/portfolio_summary.json) · [재현 범위](RELEASE_REPRODUCIBILITY.md) · [Backlog](../ROADMAP.md) · [Public 체크리스트](PUBLIC_RELEASE_CHECKLIST.md).

README 원문과 이전 gitignore는 로컬 archive에 보존했습니다. 기존 Candidate bytes는 변경하지 않으며 새 문서가 과거 Candidate 승인 범위를 확장하지 않습니다.

## 업로드 전 확인

- 계정 influnix(89777831), 신규 Git 저장소 main, 기존 commit/tag/remote 없음.
- [대상 GitHub 저장소](https://github.com/influnix/food-commodity-procurement-intelligence)는 생성 후 PRIVATE·empty 상태를 확인했습니다.
- `configs/release_allowlist.toml`의210파일만 포함. 원천/가공/approved export·전체 artifacts·캐시·개인 절대경로가 있는 과거 문서는 제외합니다. 모든 후보의 크기/내용/Secret 패턴/상대링크를 검사했습니다. 검사는 모든 가능한 Secret이나 재배포 권리를 보증하는 도구가 아닙니다.
- Stage 파일만 내보낸 clean export에 data/artifacts가 없는 상태로 `scripts/ci/run_contract_tests.py`: **330passed,3기존SWIG경고,37.60초**, source/evidence open·network 시도0입니다.
- 구성은 기존 toy/contract321개+Release 경계9개입니다. 최초 새 경로검사1건 실패를 플랫폼 독립 경로 판정으로 수정한 뒤 재검증했습니다. 과거613개 전체는 이번 Release에서 재실행하지 않았습니다.
- Git author는 계정의 GitHub noreply 주소를 로컬 설정으로 사용합니다. 개인 메일·토큰을 파일에 넣지 않았습니다.

## 실제 Private Release 검증

| 항목 | 결과 |
|---|---|
| Repository | [influnix/food-commodity-procurement-intelligence](https://github.com/influnix/food-commodity-procurement-intelligence) |
| 계정 / Visibility / 기본 branch | influnix / **PRIVATE** / main |
| 최초 Commit·Push | `ebbcbb09d52210154cec50aa95957d267e9661e5`, 성공 |
| Workflow | Offline portfolio contracts |
| 검증 Run | [41559513966 — SUCCESS](https://github.com/influnix/food-commodity-procurement-intelligence/actions/runs/41559513966) |
| 원격 환경 | Ubuntu22.04 / CPython3.11.17, 기존 lock 설치 성공 |
| 실제 원격 테스트 | **330passed / 0failed / 0skipped**, 기존 SWIG경고3,36.93초 |
| 원격 접근 감사 | checkout source/evidence open0, 차단시도0, network시도0 |
| 로그 검사 | credential/private-key/개인 Windows경로/개인 메일 패턴 검출0. GitHub hosted runner 경로는 정상 플랫폼 metadata |
| 최초 동기화 | Local/Remote main SHA 일치, working tree clean |
| 보안 |210파일의 내용·크기·링크 검사, 최초 전체 Git 이력1commit/210unique blob 검사 PASS |
| 제외 | data 전체(raw/processed/approved_exports/synthetic), artifacts 전체, 환경/캐시/Secret·개인 경로 문서. Git에는 가격 행 없는 집계 JSON만 포함 |

GitHub 연결 앱은 새 저장소 Actions 로그를 조회하지 못해 정상 인증된 CLI로 검증했습니다. 로컬 첫 로그 수신은 Windows 기본 decoding 오류로 실패했고 UTF-8 bytes decoding으로 정정했습니다. 원격 CI 자체는 첫 실행부터 성공했으며 모델·의존성 사양 변경은 없습니다.

MVP5/5 PASS는 유지하지만 이번 CI는 과거 전체613개가 아닌321개 기존 계약+9개 Release 검사입니다. 실제 source·Holdout의 독립 재검증은 없습니다. README를 제외한 기존 Day17 pin380개와 원래 Candidate bytes는 그대로이며, README 원문도 archive pin과 일치합니다. 새 Release 코드/문서가 과거 실행 Candidate에 포함된다고 주장하지 않습니다.

Public 변경·License 임의선택·force push·이력 삭제·실제 학습/평가·Unlock은 수행하지 않았습니다. 현재 버전 이후 고도화는 [독립 Backlog](../ROADMAP.md)로 분리합니다. 최종 SHA/최신 CI·작업트리/보존·로그 검산은 로컬 Day19 종료 보고에도 기록하며, 이 문서에 자기 자신의 Commit SHA를 미리 만들지 않습니다.
