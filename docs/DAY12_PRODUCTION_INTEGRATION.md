# Day12 Production Integration 계약

실제 World Bank 원천·Bridge·Holdout 값을 읽지 않습니다. 기존 개발용 store/reader, 모델·feature·OOF·scenario·LP·engine 코드를 변경하지 않고 세션과 순차 연결 모듈을 추가합니다. 실제 가격 loader와 unlock capability는 연결하지 않습니다. 날짜가 같아도 모든 새 가격은 `synthetic_day12_not_world_bank`입니다.

## 기준선과 변경 범위

Day11 정본 SHA는 `163a74d3387743b882651e98fa434d1cc4113d3e5eac98e3fde08e53e24b78be`입니다. 최초 작업 전에 실제 contract/code/metadata/output hash를 확인했고 NOT_READY의5개 미검증 상태를 기록했습니다. `artifacts/day12/day11_baseline_integrity.json`이 증거입니다. 원천 raw/CSV hash는 이전 metadata를 재사용하고 재해시하지 않습니다.

신규 모듈은 `data/sequential.py`, `forecasting/publisher.py`, `uncertainty/sequential.py`, `evaluation/sequential_runner.py`, `evaluation/day12.py`, `evaluation/readiness.py`입니다. 기존 API의 잠금·호출·결과는 유지합니다. README/ROADMAP/AGENTS는 추가 기록만 허용합니다. 기존 실가격 결과는 저장 artifact와 합성 회귀로 확인하며 재생성하지 않습니다.

## 5개 연결 문제

| 항목 | 기존 제한 | 새 연결과 증거 |
|---|---|---|
| 순차 store/Bridge | `data/availability.py`의 selection freeze/Bridge 차단 | permit·공개 clock·Observation hash·가용 이력·미래/중복/역순 차단 |
| 신규 forecast | `optimization/forecast_adapter.py`의 Validation 저장키 제한 | native publisher가 현재 origin에서 raw point/interval/quantile를 배치로 발행·exclusive 저장 |
| OOF/scenario | 기존 calibration phase와 joint generator의 Validation 제한 | 새 lifecycle의 고정 archive 복원·현시점 발행·완전성숙 release·보정·128 joint draw |
| 최종 runner | Day9의 fixed36과 Day10 ledger[34] 등 | 같은 core로22/24와36/38의 두 합성 달력 실행 |
| native backend | Day11의 injected fake만 확인 | 설치된 statsmodels/LightGBM의 실제 fit과 native output·독립 proof·반복 검산 |

## 세션·공표·Bridge

`SessionPermit`는 Day12가 허용한 명시적 합성 세션만 발급합니다. 실제 source permit은 기본 비활성이고 오늘은 발급 API가 없습니다. `SequentialObservationStore`는 공개된 record만 소유하며 파일 loader를 받지 않습니다. 각 record는 관측월·가격·실제 사용한 공표timestamp·가정 근거·vintage·source·단위를 보존하고 SHA를 기록합니다.

Clock은 순방향으로 한 번씩 전진합니다. 공개는 `observation_month≤t−1`와 `actual_available_at≤decision_at(t)`를 모두 만족해야 합니다. 공개 순서는 `(available_at, observation_month)`이며 날짜가 오래된 관측의 지연 공표를 허용하되 공표 순서 역행과 같은 관측의 재공개/수정을 금지합니다. 과거 as-of query는 이미 공개된 record에 다시 그 시점의 조건을 적용하며 공개 clock을 되돌리지 않습니다.

Bridge2024-09는 첫 origin에서 금지하고 실제 공표 가정을 만족한 뒤 과거 특징으로 허용합니다. 공표가 늦으면2024-10에서도 거부합니다. Bridge는 원장 성과에 포함하지 않습니다. 한 record의 공개로 다른 미래 target의 권한을 얻지 않습니다. Runoff에는 정책·예측 발행을 중단합니다.

## 합성 fixture와 native 추정

Day11의321개월 fixture는 길이는 충분하지만 잡음 없는12개월 반복이라 고정 SARIMAX가2016-04/2024-09/2026-06에서 nonconverged였습니다. 이를 Native 성공으로 기록하지 않았습니다. 모델 사양을 바꾸지 않고 통합용 fixture를 별도로 정의했습니다.

2000-01부터321개월, 초기 level200, 초기 미존재 increment0, `d_i=.1+.35*d_(i−1)+.25*d_(i−12)−.0875*d_(i−13)+ε_i`, `ε~Normal(0,1.5)`, `level+=d`, Python Random seed20261030입니다. 단위는 USD/t이고 실제 관측이 아닙니다. 가격이 비양수면 clip 대신 실패합니다. DGP는 테스트 입력 정의이며 모델 탐색이나 실제 시장의 추정 결과가 아닙니다.

SARIMAX는 Day4 고정사양과 fitting 설정, `get_forecast(4)`/native80% interval, model step2/3/4를 사용합니다. LightGBM은15특징·3 direct point·9 quantile·100rounds·기존 alpha/seed/thread와 완전 label maturity를 사용합니다. 각 origin의 전체 vector 학습은 `o+3≤t−1` 및 모든 label timestamp 조건을 만족해야 합니다. 실제 validation reader나 미래 truth는 publisher의 인자가 아닙니다.

Publisher는 immutable raw triple과 cutoff·history hash·학습 origin/target/publication cutoff·model/feature hash·native event 증거를 저장합니다. 저장은 exclusive-create이며 같은 origin 재발행이나 소급 발행을 거부합니다. Reload는 외부에 핀한 issuance digest를 검사하며 target 결합이 원래 예측을 바꾸지 않습니다. 시간 측정은 별도 파일로 분리합니다.

## 초기 pool·순차 OOF·기존 규칙과의 차이

실제 평가 기본 seed는 Day11이 지정한 기존 Day5 Historical60+Validation36 origin/model이며 변경하지 않습니다. 오늘 실가격 OOF를 합성 pool에 섞지 않습니다. 같은60+36 달력에서 합성 native 예측을 시간순으로 실제 발행해 seed의 합성 대응물을 검증합니다.2021-04~05와2024-06~08에 미발행 예측을 보충하지 않습니다.192개 seed batch(모델별96개) archive 복원 API는 외부 SHA와 원래 달력/출처/fit proof를 요구하고 새 모델 fit으로 빈 archive를 채우지 않습니다. 실제 Day5 데이터 archive의 원천별 연결 검증은 실제 평가 승인 단계의 별도 확인 대상입니다.

**명시적 계약 차이:** 기존 Day5는 horizon별 성숙한 잔차를 먼저 release합니다. Day12 지시는 Calibration에도 `o+3≤t−1`와 전체 target 공표를 요구합니다. 새 adapter는 vector 전체 성숙까지 H1/H2도 대기합니다. finite-sample 식·score·최근60·최소24는 유지합니다. 최초 합성 Validation에서는 전체 vector59개가 성숙합니다. 기존 Day5의60/60/59 결과와 코드는 변경하지 않습니다. 이는 성능에 맞춘 보정 변경이 아니라 오늘 지시의 더 강한 편입 조건입니다.

새 origin의 raw 예측은 현재 시점에서 발행하고 이후 공개 이력으로만 잔차를 만듭니다. 모델/방법/horizon을 분리하고 보정 window60·최소24·기존 rank/score/fallback을 유지합니다. 현재 예측 batch는 knowledge type·native backend·source ID·현재 session ID를 함께 검사합니다. 고정 archive 복원은 원래 session 기록을 보존하면서 외부 digest와 동일 source를 확인합니다. Raw point는 수정하지 않습니다. quantile crossing·음수 경계를 숨기거나 재배열/clip하지 않습니다. Crossing raw 구간은 invalid로 기록하고 점수에서 제외하며 현재 구간의 conformal output은 `raw_invalid_uncalibrated`입니다. Point가 유효하면 공동 point-error vector에는 사용할 수 있습니다.

Joint pool은 같은 모델·과거 origin의 세 target과 공표가 모두 성숙한 최근60개·최소24개입니다. 기존 파생 seed·multiplicative ratio·128경로·균등가중치·Planning/Evaluation 목적을 유지합니다. 같은 모델 RN/RA는 같은 Planning 세트를 사용합니다. 같은 pool의 별도 seed 재표집을 독립/OOS라고 부르지 않습니다.

## 실행·회계·실패

시장 예측은 정책 상태와 독립이므로 공통 순차 as-of pass에서 한 번 발행하고, 각 정책은 자기 origin에 봉인된 입력과 공개 context로 별도 원장 pass를 실행합니다. 정책은 source·전체 forecast cache·평가 truth를 받지 않습니다. 같은 immutable 외생가격/수요/납기 경로와 독립 I200/빈pipeline 상태를 씁니다. 7정책·기존 GLOP/α/λ·운영·수령월가격·Runoff·최종 단회말기·빈종료pipeline 규칙을 유지합니다.

같은 core는22 origins/24 ledger/21 Active/3 Runoff 및36/38/35/3을 처리합니다. 실패 시 부분 정책을 Fixed로 대체하지 않고 전체 비교/지표를 비웁니다. Native fit, provenance, mature history, pool, scenario, solver, 보존, 불완전 원장 오류는 명시적으로 실패합니다. 기존 code/result를 덮어쓰지 않습니다.

## 보안·해석 범위

Python open/io/os.open guard는 `data` 접근을 차단하고 Day11/12 합성 디렉터리만 허용합니다. 실제 source/Bridge/target 접근 시도는 실행 전에 거부합니다. OS 격리나 이미 열린 fd/C extension 전체를 감시하는 장치는 아닙니다.

Native 합성 통합은 실제 예측 정확도·coverage·시장CVaR·기업 절감의 증거가 아닙니다. Day11의18개 한계와 최신 수정 snapshot/가정 공표시각을 유지합니다. READY·실제 공표성숙·사용자 승인·실제 실행허용을 별도로 판정합니다.
