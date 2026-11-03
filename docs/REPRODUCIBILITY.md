# 저장 Evidence 재현 방법

기존 프로젝트 루트와 `.venv`를 사용합니다. 기록 환경은 Python3.11.5·pytest8.3.5·statsmodels0.14.6·LightGBM4.6.0·OR-Tools9.14.6206입니다. Day13은 설치·다운로드·실험을 하지 않았습니다.

## 현재 범위의 명령

```powershell
.\.venv\Scripts\python.exe scripts/run_day13_tests.py
.\.venv\Scripts\python.exe scripts/build_day13_evidence.py --output artifacts/day13/evidence_a
.\.venv\Scripts\python.exe scripts/build_day13_evidence.py --output artifacts/day13/evidence_b
.\.venv\Scripts\python.exe scripts/verify_day13_evidence.py artifacts/day13/evidence_a --repeat artifacts/day13/evidence_b --output artifacts/day13/verification.json
```

출력 폴더가 있으면 덮어쓰지 않고 실패합니다. 재실행에는 새 이름을 사용하세요. 새 모델/solver 실험을 호출하지 않으며 첫 명령의 기존403개 회귀 테스트 안에서만 합성 toy fit을 재실행합니다. Artifact가 빠지거나 hash/값이 다르면 성공으로 보고하지 않습니다.

표 계산·검산은 표준 라이브러리만 사용합니다. 그림은 현재 설치돼 있던 Matplotlib3.10.1을 사용하고 `plot_environment.json`에 버전을 남깁니다. 새 설치 없이 표만 재현하려면 두 build 명령에 `--no-plot`을 추가하세요. 같은 옵션/환경으로 만든 두 bundle을 비교해야 합니다. 선택 옵션이 다르면 Release hash도 달라집니다.

## 필요한 자료와 공개 범위

| 자료 | 취급 |
|---|---|
| 공식 World Bank Pink Sheet | 공개 출처이며 기존 기록상 CC BY4.0/World Bank 추가조건과 제3자 예외를 확인해야 합니다. [출처/조건](WORLD_BANK_SOURCE.md) 참조 |
| `data/raw`, `data/processed` | 따로 확보하는 원본/가공 데이터입니다. 원본 URL·SHA는 기록하지만 Day13은 열지 않습니다. 공개 파일이어도 프로젝트 Holdout 잠금을 우회하지 않습니다. 새 다운로드는 별도 명시 승인 대상입니다 |
| Day3/4/9 저장 Validation 결과 | 이 패키지가 참조하는 기존 예측·fit provenance·발주·입고·원장·metric/manifest입니다. 전체 참조 경로와 SHA를 bundle index에 기록합니다 |
| Day10/12 결과 | 사후 민감도/합성 통합·한계의 참조입니다. 원래 실험을 다시 실행하지 않습니다 |
| Day13 bundle | 원본을 복사한 폴더가 아니라 재계산 요약·재고 그림·검산·출처 index입니다. 원본 artifact 없이 검산을 재현했다고 주장하지 않습니다 |

깨끗한 환경에 설치가 별도 승인된 경우에만 실제 존재하는 lock/프로젝트 설정을 사용합니다. 아래는 이번에 실행한 명령이 아닙니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements/day7-lock.txt
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip install pytest==8.3.5
```

위 lock에는 선택적 그림 패키지가 없으므로 새 환경에서는 `--no-plot`을 사용할 수 있습니다. 기존 bootstrap은 system-site-packages를 사용했던 환경이며 새 컴퓨터의 완전한 의존성 격리 재현을 이번에 검증한 것은 아닙니다.

## 실행·승인 경계

예전 Day4/9 verifier와 모델·구매 runner에는 실제 `data` 파일을 읽거나 새 fit/평가를 하는 경로가 있습니다. 이번 재현에는 사용하지 않습니다. 새 verifier는 저장 결과만 읽습니다. Raw source hash는 이전 검증 기록을 재사용하며 이번에 다시 계산하지 않습니다. MASE denominator도 핀한 fold scale을 사용합니다.

Evidence Release Manifest는 출력과 인용 파일의 SHA index입니다. 향후 Holdout 승인용 Freeze가 아닙니다. Day12 Candidate `ae093042b0cfbe3b8af5a75d01e235f12faa5adb82fd0438527286a0006b6a4f`는 수정하지 않았지만 새 Day13 코드/문서를 포함한 승인으로 사용할 수 없습니다. 7정책 계약·실제 승인·공표성숙·방법론 일관성 검토는 별도이며 실제 Holdout은 계속 잠겨 있습니다.
