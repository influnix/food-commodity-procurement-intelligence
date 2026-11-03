# Day12 Release Readiness

Day11의 READY/NOT_READY/BLOCKED 의미를 유지합니다. 모든19개 기술 조건이 PASS일 때 READY, 누락/실패 증거가 있으면 NOT_READY, hash/권한/접근 경계 위반은 BLOCKED입니다. READY는 실제 실행 승인이 아닙니다.

5개 production 항목은 함수 존재 대신 native 합성 22/24 전체 실행,36/38 합성 회귀, immutable 발행·OOF·pool proof, 독립 물리/비용/E/CVaR 검산, 반복 결정성 및 기존359개 회귀를 증거로 사용합니다. 기존14개 조건과 frozen split·모델·특징·seed·scenario·운영·회계를 유지합니다. 전체 vector 편입 조건의 차이는 [연결 계약](DAY12_PRODUCTION_INTEGRATION.md)에 명시했습니다.

다음 네 상태를 별도 기록합니다.

1. **Technical Readiness**: 합성 source와 실제 backend에서의 계약 통합 상태.
2. **Target Publication Maturity**: 실제 UTC clock이2026-10-31T23:59:59+00:00에 도달했는지 여부. Fixture clock으로 대체하지 않습니다.
3. **Explicit User Authorization**: 실제 Bridge/이전 target의 순차 접근·원천 reader 연결·최종 단회평가에 대한 명시적 승인. 오늘은 false입니다.
4. **Actual Holdout Execution Allowed**: Day12에서는 항상 false이며 실제 capability 발급/원천 reader 연결이 없습니다.

실제 파일에 값이 있어도2·3을 우회할 수 없습니다. 실제 source/vintage 및 기존 Day5 seed archive 연결은 승인된 다음 범위에서 확인해야 합니다. 합성 native 지원이 실제 데이터 연결까지 실행됐다는 뜻은 아닙니다.

Candidate freeze는 Day11 기준 digest를 보존하고 새 code/config/test/contract와 독립·회귀·반복 증거를 핀합니다. Day11 원본 Manifest를 덮어쓰지 않습니다. 원천 raw/CSV hash는 기존 기록을 재사용하며 실제 source byte를 열지 않습니다. 신규 합성 입력은 별도 hash로 검증합니다. 초기 문서3개는 추가 전 prefix hash와 변경 후 hash를 기록합니다.

후보 검증기는 외부 expected digest와 핀 파일/합성 입력을 검사합니다. 이전 Day11 digest로 새 후보를 승인하려는 검증은 BLOCKED여야 합니다. Candidate 자체도 사용자 승인이 아닙니다. 코드가 바뀌면 이전 승인을 이월하지 않고 새 검사·후보·digest별 승인이 필요합니다. 마지막 보고의 상태와 `candidate_pointer.json`을 사용합니다.

불확실성 raw quantile crossing은 유지·flag·보정 제외 처리하며 기술적 native fit 성공과 구간의 통계적 타당성을 구분합니다. Coverage80%나 실제 시장 tail 보장을 READY 조건 충족으로 추정하지 않습니다.
