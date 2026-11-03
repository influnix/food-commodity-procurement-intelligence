# Day15 변경 추적

변경 전 Candidate/Evidence 무결성을 먼저 확인하고 `artifacts/day15/preservation_before.json`에 기존6275개 비Data SHA와 Data89개 size/mtime를 저장했습니다. 원천 데이터는 열거나 재해시하지 않았습니다. 모든 기존 Day0~14 artifact는 보존합니다.

## 의도적으로 수정한 기존 파일

| 파일 | 이유·영향 |
|---|---|
| `src/food_procurement_intelligence/uncertainty/contracts.py` | CR-02 공용 finite/point/quantile/bounds/base 검증과 metadata 정합성. Invalid가 보정 후 valid로 변하는 경로 차단 |
| `src/food_procurement_intelligence/forecasting/publisher.py` | 공용 native raw 검사 적용. 비유한 입력 거부 유지, 유한 비양수 통계 경계는 보존·flag. 모델 fit 사양은 불변 |
| `tests/test_day11_release_gate.py` | 과거 live source SHA 고정 검사를 현재 승인된 CR-02 코드 변경과 구분. 변경 전 SHA가 일치한 명명된 코드만 제외하고 나머지 artifact/metadata 검증 유지 |
| `tests/test_day14_methodology.py` | 기존 NaN 결함 반례 artifact를 확인하면서 수정 후 live 동작은 invalid를 요구. 테스트 수/원래 증거 보존 |

변경 전·후 실제 SHA와 사유는 `artifacts/day15/change_ledger.json` 및 새 Candidate에 포함합니다. 허용 목록은 `configs/day15.toml`의 정확한4개 경로이며 다른 변경을 포괄 허용하지 않습니다. 과거 freeze를 현재 코드와 동일하다고 주장하지 않습니다. 이전 Day14 manifest 파일은 그대로지만 수정된 live source 참조에 대해 이전 검산을 그대로 재사용할 수는 없습니다.

## 신규 파일

`configs/day15.toml`; `uncertainty/validity.py`, `uncertainty/horizon_sequential.py`; `scripts/day15/common.py`, `run.py`, `verify.py`, `run_tests.py`, `freeze.py`; `tests/test_day15_remediation.py`; 문서 DAY15_METHOD_REMEDIATION, DAY15_VALIDITY_CONTRACT, DAY15_CHANGELOG, DAY15_STATUS입니다.

기존 SequentialOOF/calibration/joint/model/LP/engine 코드와 Day5/6/11/12 설정은 수정하지 않았습니다. README/AGENTS/ROADMAP도 수정하지 않았으며, Day15의 사용자 승인 범위가 과거 Day12에 한정했던 full-vector Calibration 계약을 새 경로에서 대체합니다. 그 근거는 Day14 권고안 A와 이번 지시입니다.

`artifacts/day15/probe`는 초기 tuple/list 비교 실패, `probe2`는 중간 검산용이며 정본이 아닙니다. 실패를 가격/정책 불일치로 숨기지 않았습니다. 실제 원인은 직렬화 구조 차이였고 같은 수치·member·seed를 확인한 뒤 의미 비교를 적용했습니다. 초기 실행 중 변경 전 기대값이 이미 로딩돼 있던 Day14 결함 테스트2개도 실패했으며, 원래 증거와 수정 후 invalid 동작을 함께 검사하도록 명시적으로 갱신했습니다. 확정 결과는 정본·반복·전체 pytest만 사용합니다.

모든 새 실행·검산은 Python의 `open/io.open/os.open`에 대한 deny-all-data guard 아래 수행합니다. 정상 source open0·차단시도0이어야 합니다. Negative tests는 별도의 내부 guard에서 실행 전에 차단을 검증합니다. guard는 OS 격리나 이미 열린 fd/C-extension 전체의 보안 모니터가 아닙니다. Git commit/push·다운로드·설치·실제 가격 fit/평가는 없습니다.
