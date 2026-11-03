# Repository instructions

## 범위와 변경 관리

- 사용자가 지정한 Day와 범위만 수행한다. Day 0 이후 단계는 별도 지시가 있을 때 진행한다.
- 기존 파일을 읽고 보존한다. 삭제·광범위한 재작성·새 프레임워크 도입은 필요성과 범위를 먼저 확인한다.
- Git commit/push, 외부 데이터/API 다운로드, 대규모 의존성 설치, 기존 전역 환경 변경은 명시적인 허가 없이 실행하지 않는다. 승인은 현재 사용자 지시의 범위에서 해석한다. Day 1에 승인된 다운로드는 World Bank 월별 Pink Sheet 원본뿐이며 NASA 수집·Git commit/push는 포함하지 않는다.
- 현재 루트를 사용한다. 중첩 프로젝트를 만들지 않는다. Windows 경로는 `pathlib.Path`와 프로젝트 상대경로로 처리한다.
- 과도한 클래스 계층, 빈 구현 모듈, 대시보드, 성급한 성능 최적화를 피한다.

## 정보 집합과 데이터 누수

- `docs/DECISION_TIMELINE.md`의 월말 의사결정, 공표 지연, 납품·정산 규칙을 따른다. 변경하면 관련 문서·설정·테스트를 함께 수정한다.
- 각 관측값에 `observation_month`, `available_at`, `availability_basis`, `vintage_id`를 보존한다. `available_at <= decision_at`만 정책/모델 입력으로 허용한다.
- 최신 수정 데이터의 조회 가능 시점과 과거 공표 시점을 혼동하지 않는다. 실제 vintage가 없으면 pseudo-real-time 한계를 명시한다.
- 미래 실제 시장가격·날씨·수요·지연·충격 경로는 평가 엔진만 읽는다. 정책은 예측과 현재까지 공개된 상태만 받는다.
- lag/rolling은 해당 origin의 사용 가능 자료에서 계산한다. 스케일링·결측 대체·특징 선택·잔차 보정·구간 보정도 fold 내부에서 학습한다.
- 월별 rolling-origin을 사용한다. random split과 전체 표본 전처리를 금지한다. 미래 타깃을 포함하는 다중 horizon 표본은 분할 경계에서 제거한다.
- 최종 holdout은 모델 선택, 정책·시뮬레이션 가정 조정에 사용하지 않는다. 사용 후 변경한 결과는 별도 탐색 실험으로 표시한다.
- Day 2 이후 날짜 기준은 `configs/splits.toml`과 `docs/SPLIT_DESIGN.md`이다. 기존 Day 0 validation 종료 규칙은 공표 지연 때문에 정정됐다. 완전 vector 학습은 `origin+3 <= evaluation_origin-1`과 모든 공표 timestamp를 검사한다.
- 모델/특징 코드는 전체 Day 1 CSV를 직접 읽지 않고 `load_development_store`의 as-of 인터페이스를 사용한다. 개발 API의 bridge/holdout 잠금을 우회하지 않는다. Holdout 가격 통계·실제 label·정답을 현재 보고서나 모델 선택에 출력하지 않는다.
- Day 3 이후 feature/model 함수에 validation 정답 reader를 전달하지 않는다. 예측 생성 후 evaluator만 validation-only reader를 사용한다. MASE scale은 각 origin의 가용 이력에서 계산하며, 향후 전처리 fit은 성숙한 label과 과거 origin 특징으로 구성된 TrainingBatch에 한정한다.

## 실제·가상 자료와 재현성

- `data/raw`는 다운로드한 원본을 불변으로 보관한다. URL, retrieval UTC, SHA-256, 단위, license, vintage, 공표 지연 근거를 manifest에 남긴다.
- 실제 가격을 임의 생성하거나 synthetic 가격을 실제 자료로 표시하지 않는다. 합성 단위 테스트 fixture는 명시적인 toy 데이터로 한정한다.
- 공급업체 조건·수요·비용 등은 `data/synthetic`에서 분리하고 생성 규칙, 단위, seed, 설정 버전을 기록한다.
- RNG는 전역 상태 대신 명시적으로 전달한다. 동일 seed만으로 정책별 RNG 소비 순서를 맞추지 말고 외생 경로를 먼저 생성·고정해 공유한다.
- 실험마다 설정 사본, Python/패키지 버전, 코드 버전(저장소가 없으면 소스 해시), 원본 해시, split 경계, seed와 시나리오 ID를 기록한다.
- 가상 결과를 실제 기업의 절감 실적 또는 인과효과로 표현하지 않는다. 통계적 불확실성과 시뮬레이션 가정 민감도를 별도로 보고한다.

## 코드와 검증

- Python 3.11+, `src/` layout, `pyproject.toml`, 타입 힌트, 짧은 함수와 명시적인 설정을 사용한다.
- 관련 pytest 검증을 실행하고 실제 명령과 결과를 보고한다. 실행하지 못한 테스트나 모델 결과를 성공으로 표현하지 않는다.
- 미래 기능 구현 시 중요한 불변식을 검증한다: 미래 자료 차단, 분할 경계, 재고 보존, 리드타임, 비용 합산, 수량/단위, solver 상태, 동일 외생 경로.
- 실제 데이터는 테스트에 내장하거나 네트워크에 의존하지 않는다. 낮은 영향의 문서 수정에 구현을 복제한 테스트를 늘리지 않는다.
- 실패·불가능한 최적화·누락 예측을 숨기지 않는다. fallback 정책과 실패율을 사전에 정하고 비용 평가에 포함한다.
- Day 4 초기 모형은 `configs/day4.toml`의 고정 사양이다. 오늘의 비교에는 탐색·early stopping·fallback이 없으며 일부 성공 키 성과를 전체108개 성과처럼 보고하지 않는다. 후속 모델 변경은 사전 사양과 근거를 기록하고 기존 결과를 덮어쓰지 않는다.
- 무거운 모델·solver 의존성은 해당 구현 단계에서만 추가한다. 설치는 프로젝트 환경에 한정한다.
- Day 5 불확실성 사양은 `configs/day5.toml`이다. Historical Train OOF와 실제 공표된 Validation OOF만 모델·horizon별로 보정에 사용한다. 원본 구간과 rolling conformal 구간을 분리하며 보정 양끝을 근거 없이 q10/q90으로 취급하지 않는다. Quantile crossing·음수 경계를 숨기거나 clip하지 않는다. 세 분위수만으로 사건 확률이나 공동 가격 시나리오를 만들지 않는다.
- Day 6 공동 시나리오는 `configs/day6.toml`의 완전 성숙 OOF 비율 vector bootstrap이다. Planning/evaluation은 seed·ID·소비 경계를 분리하되 같은pool 재표집을 독립/OOS라고 부르지 않는다. Fixed Toy 엔진의 미래 실현 경로는 정책에 전달하지 않으며 수령월 비용을 한 번만 계상한다. Toy 전용 초기pipeline A80/B20을 향후 실제 정책 비교의 기본 입력으로 조용히 채택하지 않는다. Day 6는 실제 Validation 구매평가·최적화를 포함하지 않는다.
- Day 7은 `configs/day7.toml`의Deterministic GLOP이다. 현재q만확정하고미래계획은재최적화한다. 기존pipeline은상수로유지하며납품월가격을쓴다. 계획폐기0의보수적제한·수치/greedy회계검사를명시하고검증된OPTIMAL만실행한다. FEASIBLE/실패는최적으로취급하지않으며기본fallback은없다. 동일초기재고200·빈pipeline Toy 비교와실제Forecast의계획smoke만허용했고실제Validation구매성과·Risk-Aware는아직없다.


## Day 8 추가 계약

- Day 8은 `configs/day8.toml`의 α=.90/λ=.50 Scenario GLOP이다. 현재와 미래 모든 신규 q·재고/입고/부족/폐기는 시나리오가 공유하며 perfect-foresight recourse를 허용하지 않는다. 현재 q만 실행하고 미래 계획은 재최적화한다.
- 수령월 가격×premium과 기존 pipeline의 시나리오별 상수 비용을 포함한다. W=0 보수적 제한과 greedy 검사를 유지한다. OPTIMAL이어도 시나리오 비용·E·CVaR·목적·VerifySolution·공유 변수 검산이 실패하면 실행하지 않는다. 기본 fallback은 없다.
- λ0의 η/ξ는 식별되지 않으므로 raw epigraph와 독립 CVaR를 구분한다. 이산 CVaR는 경계 원자의 일부 질량을 포함한 상위1−α 비용이며 128경로의13개 단순평균이 아니다.
- 실제 Day6 scenario adapter는 같은 origin/model의 Planning만 허용하고, 원본 hash·공표/fit proof를 확인한다. Evaluation·Holdout을 거부하며 미요청 pool 가격을 숫자로 해석하지 않는다.
- Day8 비교는 동일 초기200·빈pipeline Toy만이며 RA synthetic generator는 world/Validation과 별개다. 실제 저장 시나리오는4개 가상상태 계획smoke만 수행했다. 실제 Validation 구매평가·Day9는 별도 지시 후 진행한다. α/λ/시나리오 가정을 결과에 맞춰 변경하지 않는다.


## Day 9 추가 계약

- Day9의기준은 `configs/day9.toml`과 `docs/DAY9_EVALUATION_PROTOCOL.md`이다. 실제Validation가격+가상운영의탐색적평가이며기업실적/독립OOS가아니다. Holdout과Bridge는계속평가입력에서차단한다.
- 최초2021-06월말I200·빈pipeline에서결정하고2021-07~2024-08의38개월을정산한다.2021-06~2024-05의36개origin만발주하며Runoff6~8월에는provider/정책호출을중단한다. Day9 solver adapter는Runoff미래계획q의상한도0으로추가한다. 기존Day7/8LP·모델·위험설정은수정하지않는다.
- 초기6월결정주문을7월시작엔진의opening으로전달하더라도외생초기pipeline으로취급하지않는다. `engine_opening_from_first_decision`과첫결정전빈pipeline을구분한다. 실제가격world를synthetic-onlyToy로위장하지않는다.
- 실제가격reader는evaluator만소유하며38개고유월을한번씩취득한다. 정책에는as-ofhistory와공개context만전달하고현재정산단가/미래실현수요/delay를주지않는다.
- 같은모델RNλ0/RAλ.5는동일Planning세트를사용한다. FA와RN의차이를순수CVaR효과로부르지않고모델변경과위험목적을분리한다. Active35원장월/Runoff3월/Full38월을구분하고월별차이를독립표본으로취급하지않는다.
- 실패시부분성공기간을전체성과로비교하거나fallback하지않는다. 실패원인·시점·완료결정로그·확인가능prefix를기록한다. 실패정책의부분비용원장이반환되지않으면가공해만들지않는다. 최종실제종료비는한번이며모든계획말기비를누적하지않는다. Day10은별도지시후진행한다.


## Day 10 추가 계약

- Day10은 `configs/day10.toml`과 `docs/DAY10_SENSITIVITY_PROTOCOL.md`의사후진단이다. Day9Baseline21개flow파일·기간지표를정확히재현한뒤OAT8/Stress2를실행한다. 새기본값·모델·α/λ를선정하지않는다.
- 운영override는동일settings/supplier객체로LP와engine에함께전달한다. 초기재고취득비는sunk cost이며다른초기재고셀의총비용차를정책절감으로해석하지않는다.
- 계획수요100/명목delay0은유지하고수요120(2022-01~03)/A cohort delay1(같은발주월)을evaluator에만적용한다. 미래실현수요/도착월을정책에주지않는다.
- 같은모델RN/RA는같은불변Planning경로를사용한다. 기존검증입력은hash로고정한압축캐시를재사용하고새예측/OOF를생성하지않는다. 실패셀도보존하고일부정책실패셀의7정책전체순위를차단한다.
- horizon2/6·publication lag2는감사후미지원이다. 기존t−1 forecast를t−2로재라벨링하거나H4~H6를생성하지않는다. 원래36결정/38개월/Runoff3개월을유지한다.
- 실제가격한경로와가상운영의셀을독립시장표본으로취급하지않는다. 작은차이·순위역전·Coverage/tail미검증을명시한다. Day11과Holdout은별도지시후진행한다.


## Day 11 추가 계약

- Day11은 `configs/day11.toml`과 `docs/DAY11_PRE_HOLDOUT_PROTOCOL.md`의 감사·동결·Synthetic Preflight만 포함한다. 실제 원천가격은 읽거나 재해시하지 않고 이전 검증 metadata/hash를 재사용한다. Python 수준 source guard의 범위와 OS 보안 경계의 차이를 명시한다.
- 최종 달력은 origin2024-09~2026-06의22개, ledger2024-10~2026-09의24개월, Active21/Runoff3이다. Bridge는 성과에서 제외하고 당시 공표된 뒤에만 과거 특징이 될 수 있다. 오늘 실제 Bridge/후속 Holdout 값의 접근은 없다.
- 7정책·기존 모델/특징/OOF60·최소24·128경로·seed·α.9/λ0,.5·Day9 운영기준과 말기회계를 유지한다. Validation 결과로 새 기본모델이나 정책을 선택하지 않는다.
- Synthetic 전용 store/pool과 주입 fake backend는 production guard를 해제하지 않는다. 새로운 실험의 모델 재학습은 없고 기존 회귀 테스트의 toy fit만 재실행한다. 미검증 production 연결은 NOT_VERIFIED로 둔다.
- Release Gate의 READY도 unlock 승인이 아니다. Freeze SHA 변경은 이전 동결을 무효화하며 실제 실행은 새 검증과 digest에 연결한 별도 사용자 승인이 필요하다. Day11에는 실제 실행 capability가 없다.


## Day12 추가 계약

- Day12는 `configs/day12.toml`과 `docs/DAY12_PRODUCTION_INTEGRATION.md`의 합성 source/native backend 통합이다. 기존 source reader·개발 잠금·모델·LP와 Day0~11 결과를 보존한다. 실제 원천·Bridge·Holdout 조회/fit/평가/Unlock은 없다.
- 새 SessionPermit는 합성 평가만 발급한다. observation≤t−1와 actual_available_at≤decision_at를 함께 검사하고 중복/역순/미래 공개를 차단한다. source hash·vintage·가정 근거와 immutable 발행 hash를 보존한다.
- 실제 seed의 기본은 Day11 Historical60+Validation36이며 오늘은 같은 달력의 native 합성 발행으로 검증한다. 미발행2024-06~08을 보충하지 않는다. archive 복원은 외부 hash와 출처/당시 fit proof를 요구한다.
- Day12 신규 OOF는 Calibration과 Joint 모두 완전3target 성숙을 요구한다. 기존 Day5 horizon별 release와의 차이를 문서화하고 옛 코드를 수정하지 않는다. raw crossing을 숨기거나 재배열/clip하지 않으며 invalid 구간은 score에서 제외한다.
- 같은 core로22/24와36/38을 처리하고7정책·공통외생경로·독립상태·현재q·Runoff·최종단회말기를 유지한다. 실패 시 전체 비교를 차단하며 fallback은 없다.
- Candidate READY도 실제 공표성숙/승인/실행과 별개다. 실제 UTC2026-10-31말 이전에는 마지막 target 성숙을 주장하지 않는다. 어떤 합성 clock도 실제 승인/공표 gate를 통과시키지 않는다. 실제 실행은 계속 false이며 이전 Day11 digest를 새 승인으로 재사용하지 않는다.
