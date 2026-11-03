# Day17 Legacy·Native 연결 계약

기존 Day0~16 파일과 사양을 수정하지 않고 새 typed adapter를 추가했습니다. Day15 HorizonSequentialOOF를 상속해 calibration/window/rank 및 Joint/scenario 수식을 그대로 재사용합니다. 새 코드는 [Legacy 타입](../src/food_procurement_intelligence/forecasting/legacy.py), [ProvenanceSequentialOOF](../src/food_procurement_intelligence/uncertainty/provenance_sequential.py)입니다.

## 증거 유형 분리

| 타입 | 증거 등급 | 보존/금지 |
|---|---|---|
| LegacyReconstructedForecast | RECONSTRUCTED_ASOF | 원래 ID·origin/H1~3·point/quantile·논리 as-of/fit cutoff·원본 row/file/manifest SHA·모델사양·source/snapshot 보존. live 증거·native session·원래 input byte proof를 생성하지 않음 |
| NativeIssuedForecast | NATIVE_ISSUED | 기존 `publisher.IssuedForecast`의 native 타입 alias. 이번 실행의 실제 NativeForecastPublisher가 발행한 batch와 성공 fit event만 인정 |

두 타입은 서로 다른 실제 Python 타입입니다. Legacy는 proof_json/native backend 형식을 갖추기 위해 변환하지 않습니다. record의 native_session_proof/original_input_byte_proof는 null이며 당시 live 발행은 NOT_VERIFIED입니다. Native의 history hash는 이번 실행의 in-memory 입력 record hash이고 원래 World Bank 파일 byte proof와 구분합니다. 합성 Native의 논리 origin2024~2026은 당시 실제 시장에서 운영 발행했다는 뜻이 아닙니다.

공통 `planning_points`는 두 타입에서 같은 숫자/날짜/단위의 ModelPrediction view만 반환합니다. evidence 등급을 바꾸지 않습니다. Legacy의 signed residual/Joint ratio는 공개된 observation을 결합한 뒤 계산하며 원본 forecast 값은 불변입니다.

## 저장된 실제 Legacy evidence

Day16의 canonical audit를 재검증하고 허용된 Day5 저장 CSV에서192batch·576horizon을 typed Legacy로 읽었습니다. 원본 파일/manifest는 기존 pin과 일치해야 합니다. Historical60+Validation36 origin/model,558저장 residual 및18개 기존 예측과 저장된 성숙 target 연결 상태를 유지합니다. 원래 record_id·row hash·model config 연결을 검사하며2024-06~08은 보충하지 않습니다.

Archive는 새 Legacy 형식의 record와 외부 digest로 저장/재로딩할 수 있습니다. hash 변경, model/origin/horizon/ID 변경, native/live 등급 승격, 가짜 native session/input proof를 거부합니다. 이 digest는 원래 pin된 저장 내용을 이번 형식으로 나타낸 archive digest이지 과거 live 발행 서명이 아닙니다.

실제 Legacy의 공통 Planning view와 source/fit 계약은 검사했습니다. 실제 observation store·새 fit·정책 평가에 붙이지 않았습니다. 실제 source export와 허용된 actual context가 없으므로 REAL_SEED_RUNTIME_VERIFIED는 NOT_VERIFIED입니다. 실제 Legacy를 합성 source store에 혼합하려는 복원도 거부합니다.

## Lifecycle와 Native 전환

첫 origin 전에 정확한192 Legacy batch를 외부 archive hash로 검증하고 pending으로 복원합니다. 최초 tick에서 해당 source의 공개 이력으로만 실제값을 결합합니다. 복원은 원래 seed 달력·모델·source/snapshot·model spec·fit 제한을 검증한 뒤 원자적으로 수행하며 실패하면 부분 상태를 남기지 않습니다.

Calibration은 각 h의 `o+h≤t−1`, actual available_at≤d_t, valid raw interval을 만족한 뒤 공개합니다. 같은 모델/h/method의 최근60·최소24·score=max(L−y,y−U,0)·k=ceil((n+1)×.8)을 유지합니다. Joint는 모든 h가 성숙하고 공표된 뒤 최근60 vector·최소24, multiplicative actual/point ratio·128경로·기존 purpose/seed/가중치를 사용합니다. Crossing은 score에서 제외하지만 valid positive point Joint를 제거하지 않습니다. Invalid/raw不足/fit/pool/solver 실패를 구분하며 숨은 fallback이 없습니다.

신규 origin에는 실제 해당 실행의 Native publisher를 한번 bind합니다. Publisher registry에 없는 임의 record, 실패/누락 fit event, Legacy의 신규 발행, 중복 origin을 거부합니다. 새 Native는 현재 공개 이력과 완전히 성숙한 학습 label만 사용하며 목표가 성숙하기 전에는 residual이 되지 않습니다. 원래 Legacy의 값·ID·증거 등급은 바뀌지 않습니다.

## 합성 통합과 기존 결과 비교

기존 Day12와 동일한 DGP/seed·2000-01~2026-09 이력을 사용합니다. 기존 저장 native 예측 중 Historical/Validation192개를 **Legacy 형식의 합성 fixture로 투영**하며 원래 native artifact는 보존합니다. 이것은 실제 Legacy의 증거를 대체한 것이 아닙니다. 실가격은 섞지 않습니다.

첫2024-09에 Legacy를 복원한 뒤22개 origin에서 SARIMAX22fit, LightGBM point66+quantile198=264fit을 새로 실행합니다. 총286성공 fit event·44신규 Native batch·132horizon입니다. 새로운 모델/하이퍼파라미터·world를 만들지 않습니다. 실제 World Bank fit은 없습니다.

첫 origin의 Joint192vector·유효 score566은 Legacy입니다. 이후 새 Native의 H1은 o+2, H2는o+3, 완전 Joint는o+4 및 actual 공표 조건을 만족한 뒤 들어옵니다. 늦은 H3가 성숙한 H1/H2를 차단하지 않습니다. origin gap의 미발행 예측을 보충하지 않습니다.

동일 입력의 Native point/quantile, Calibration 수치/상태, Joint member/ratio/draw·가격,7정책의 발주/입고/재고/비용을 Day16과 대조합니다. provenance가 달라 pool_sha256과 그에 의존하는 planning_sha256은 달라집니다. 이 두 lineage digest만 별도로 비교하고, 숫자·표집 origin·seed·정책 성과를 해시에 맞춰 변경하지 않습니다. 가격 허용오차1e−8을 확대하지 않으며 실제 차이를 기록합니다.

평가 형태는22origin/24ledger/21Active/3Runoff·7정책·154decision·168ledger·132LP입니다. 초기I200·빈pipeline·수요100·A/B·α.90/λ0,.50·수령월 단회비용·말기 단회계상·Total Cost/Fill Rate를 유지합니다. 같은 모델 RN/RA는 같은 Planning set이며 평가 경로는 정책에 주지 않습니다.

실제 source가 승인·검증되면 이 Legacy 타입/수명주기 계약으로 연결할 수 있습니다. 현재 source store/permit와 실제 CLI는 합성/차단 상태입니다. 실제 source context 활성화·검증과 실제 최종 단회평가는 별도 범위·승인·적합한 새 동결을 요구하며, 과거 live/vintage 증거 부족을 자동 PASS로 바꾸지 않습니다.
