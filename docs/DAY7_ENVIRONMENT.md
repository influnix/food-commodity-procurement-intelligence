# Day 7 Solver 환경

2026-10-29 Asia/Seoul. 기존 Windows x64 /프로젝트 `.venv` Python3.11.5를 사용했습니다. OR-Tools가 미설치인 것을 확인하고 PyPI의9.14.6206 메타데이터와cp311-win_amd64 wheel을 확인했습니다. 이 버전은 기존 NumPy1.26.4·pandas2.2.3과 호환되는 requirement를 선언합니다.

신규 설치는4개뿐입니다: ortools9.14.6206, absl-py2.3.1, protobuf6.31.1, immutabledict4.2.2. 기존 typing_extensions4.15.0을 재사용했습니다. 모델 패키지·NumPy·pandas·SciPy 등 기존 버전 변경은0개입니다. 기본 Miniconda의ortools는 여전히 미설치이며 설치 경로는 프로젝트`.venv/Lib/site-packages/`입니다.

```powershell
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: --no-deps ortools==9.14.6206 absl-py==2.3.1 protobuf==6.31.1 immutabledict==4.2.2
```

처음 메타데이터 조회는 샌드박스DNS getaddrinfo 오류로 실패했고 승인된 재시도에서 성공했습니다. 패키지 설치는 승인된 실행으로 성공했으며 설치 충돌은 없었습니다. OR-Tools의 Requires-Dist 전체가 설치 버전을 충족하는지 확인하고 statsmodels0.14.6/LightGBM4.6.0 import와 전체 회귀 테스트를 통과했습니다. 사용자 승인 범위의 solver 설치 외에 데이터 다운로드·전역 환경 변경은 없습니다.

Backend는 `Glop solver v9.14.6206`입니다. MIP/CVaR/stochastic 기능은 사용하지 않았습니다. 설치된pywraplp에서 상태코드0..6과VerifySolution 의미를 직접 확인했습니다. OPTIMAL=0, FEASIBLE=1(실행한계로 중단된 feasible 포함), INFEASIBLE=2, UNBOUNDED=3, ABNORMAL=4, MODEL_INVALID=5, NOT_SOLVED=6입니다. FEASIBLE을 최적으로 취급하지 않습니다.

GLOP의SetNumThreads(1)은False를 반환했습니다. 지원된 thread 설정이라고 기록하지 않으며 기본 직렬 GLOP에 고정random_seed·dual simplex를 사용합니다. pytest의SWIG import deprecation 경고3개는 버전호환 경고로 남겼고 solver 실패로 세지 않았습니다. 이를 제거하려고 무관한 환경을 업그레이드하지 않았습니다.

`requirements/day7-lock.txt`는 기존 모델 closure를 유지한16개 exact pin입니다. 기존pyproject·day4 lock은 수정하지 않았습니다. 재구축은 기존 환경 설명을 따른 뒤 이 lock을 프로젝트 환경에 설치합니다. 현재 환경은 기존system-site-packages를 읽으므로 완전 격리 환경이라는 주장은 하지 않습니다.

`artifacts/day7/environment_before.json`, `environment.json`에 버전 전후와설치 경로·Requires-Dist를 기록했습니다. 실행 manifest에는backend/version,solver extension SHA-256,Python/패키지 버전과새 코드 해시를 남겼습니다. API 근거는 [Google GLOP LP 예제](https://developers.google.com/optimization/lp/lp_example)와 [PyPI9.14.6206](https://pypi.org/project/ortools/9.14.6206/)입니다.
