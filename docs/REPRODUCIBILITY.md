# 재현성 및 안전한 실행 안내

## 환경과 설치

Python 3.11과 활성화한 가상환경을 사용합니다. 기존 버전은 [runtime-lock.txt](../requirements/runtime-lock.txt)에 보존하며 예측 의존성만 담은 [forecasting lock](../requirements/forecasting-lock.txt)도 유지합니다. Python patch·OS에 따라 실행시간은 달라질 수 있지만 모델·solver·패키지 pin은 동일합니다.

```sh
python -m venv .venv
# 사용하는 셸의 표준 명령으로 생성한 가상환경을 활성화합니다.
python -m pip install -r requirements/runtime-lock.txt
python -m pip install pytest==8.3.5
python -m pip install --no-deps -e .
python scripts/ci/run_contract_tests.py
python scripts/validation/run_synthetic_checks.py
python scripts/release/audit.py
```

CI는 깨끗한 Ubuntu22.04/Python3.11 checkout에서 설치를 확인합니다. 로컬 clean export 검증은 기존 환경과 내보낸 소스를 사용하고, 제외된 시장가격·Evidence를 읽지 않습니다. 설치는 의존성만 받으며 World Bank/NASA 입력을 내려받지 않습니다. 코드 라이선스는 소유자가 아직 선택하지 않았고 설치 명령이 데이터 이용·접근 권한을 주지는 않습니다.

## 재현 가능한 범위

| 범위 | 저장소만으로 실행 | 의미 |
|---|---|---|
| A: 오프라인 계약 테스트 |가능| 매개변수화 항목을 포함한 기존 CI 330개 전체 |
| B: 합성 통합 |가능| 7개 정책 Toy 엔진·LP, RN/RA 동일 시나리오, 미래 가격·수요·지연 변경, λ0/1·비예견성 등 기존 6개 항목; A의 부분집합 |
| C: 실제 가격 분석 |자동 실행 불가| 승인된 원천 전용 Export·생성/출처 Manifest·hash·명시적 접근/학습 범위 필요 |
| D: 전체 과거 archive 검증 |불가| 원천·대규모 artifacts는 제외됨. 613 passed는 과거 실행 기록이며 현재 clean checkout 전체 통과가 아님 |

전체 622개 테스트의 수집과 실행은 다릅니다. archive에 의존하는 항목을 실행하려면 해당 자료와 코드 버전이 필요합니다. 제외된 입력을 갖추지 않은 상태에서 전체 pytest 성공을 주장하지 않습니다.

합성 진입점은 기존 회귀 테스트·엔진·solver를 호출합니다. 예측기·가격 생성 규칙·실험 정책을 추가하지 않으며 과거 22/24 Native 학습 검증을 다시 수행한 것으로 표시하지 않습니다. 완전 벡터 보정 호환 계약과 Horizon별 보정은 구분합니다.

Runner는 `configs/evaluation/ci.toml`의 항목만 선택하고 무관한 plugin 자동 로드를 막습니다. checkout의 `data/`·`artifacts/` Python open과 socket 연결을 차단하되 임시 Toy fixture는 허용합니다. 일부 음성 테스트는 내부 guard에서 금지 요청을 먼저 가로챕니다. 이는 Python/API 경계이며 OS/FD/C extension 격리가 아닙니다. CI를 맞추려고 Skip·XFail을 추가하지 않습니다.

Workflow는 `contents:read`, 고정된 공식 Actions Commit, checkout credentials 미보존을 사용합니다. 프로젝트 Secret·원천 다운로드·artifact 업로드는 없습니다. 6개 합성 항목을 별도 명령으로 재실행해 진입점을 확인하지만 고유 테스트 수를 336개로 늘려 보고하지 않습니다.

## 기능별 설정과 실행 계약

`configuration.load_spec(name, root)`는 source/quality/restricted_export, features/models, calibration/joint_and_operations/lifecycle, deterministic/risk, splits/validation/sensitivity/final/native_synthetic/handoff를 찾습니다. 하이퍼파라미터·Horizon·seed·업체/비용·달력은 유지합니다. Joint와 운영조건은 기존 호출자가 같은 스키마를 사용하므로 `joint_and_operations`에 함께 있습니다.

`configs/compatibility/initial_proposal.toml`은 사용하지 않는 초기 제안입니다. 과거 확률·위험 가정이 최종 운영·위험 계약을 덮어쓰지 않습니다. 호환 도구의 과거 식별자는 내부 매핑으로 처리하므로 사용자는 개발 단계 번호를 알 필요가 없습니다.

## 저장 Evidence와 역사적 검증

[portfolio_summary.json](../evidence/portfolio_summary.json)은 원시·월별 가격을 포함하지 않는 선별 집계이며 원래 summary 경로·hash를 보존합니다. hash는 원본 기록과의 연결이지 그 원천을 현재 재검증했다는 뜻이 아닙니다.

원래 문서·설정·코드와 과거 경로 기반 Candidate는 Git History·로컬 기록으로 보존합니다. 정확한 과거 pin 검증에는 해당 코드·경로·archive가 필요하며 현재 파일을 과거 bytes로 간주하지 않습니다. `scripts/compatibility/`는 서로 다른 과거 감사·Freeze·재현 계약을 유지합니다. 현재 트리에서 오래된 pin이 맞지 않으면 실패하는 것이며 이를 통과시키려고 assertion을 약화하지 않습니다.

[evidence/product_release_manifest.json](../evidence/product_release_manifest.json)은 현재 제품 파일의 무결성 목록입니다. 실제 Holdout 승인이 아니며, 원천·과거 예측 발행·사용자 권한을 새로 입증하지 않습니다. 내부 개발·마이그레이션 감사 기록은 제품 안내 파일과 구분해 로컬·Git History에 보존합니다.

## 실제 원천 사용 조건

공식 출처와 제한된 776개월 Export 요건은 [데이터 및 As-Of 계약](DATA_AND_ASOF_CONTRACT.md)에 있습니다. 승인된 Export가 없으며 801개월 혼합파일을 읽어 자체 생성하면 안 됩니다. 실제 Source/Seed Runtime은 NOT_VERIFIED / ACCESS_APPROVAL_REQUIRED이고, 실제 세션 발급·평가 실행 capability는 비활성입니다.

향후 실제 실행에는 원천·adapter 검증, 전체 회귀, 새로 검증된 실행 Candidate와 digest에 연결한 단회 평가 승인이 필요합니다. 실제 UTC 성숙도도 새로 확인해야 하며 달력 Threshold가 지났다고 과거 Vintage·최초 공표시각이 검증되는 것은 아닙니다. [연구 및 운영상 한계](LIMITATIONS_AND_FUTURE_WORK.md)를 함께 확인하세요.
