# Day 4 환경·의존성 기록

2026-10-27 Windows x64 / Python 3.11.5의 기존 프로젝트 `.venv`를 사용했습니다. 초기 환경에 NumPy1.26.4, SciPy1.17.1, pandas2.2.3 등이 있었지만 statsmodels/LightGBM/patsy는 없었습니다.

사용자 승인 범위에 따라 다음 **3개만 프로젝트 `.venv`에 신규 설치**했습니다.

```powershell
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: --no-deps statsmodels==0.14.6 lightgbm==4.6.0 patsy==1.0.2
```

첫 시도는 샌드박스 DNS 오류로 실패했고 승인된 네트워크 재시도에서 Windows wheel 설치를 완료했습니다. pip/기존 NumPy·SciPy·pandas·전역 Python을 업그레이드하거나 재설치하지 않았습니다. 새 3개 패키지의 실제 경로가 모두 `.venv/Lib/site-packages/`임을 확인했습니다. 기존 공유 패키지는 읽어 사용하므로 완전한 dependency isolation은 아닙니다.

`--no-deps`로 무관한 공유 패키지 변경을 막은 뒤, 설치된 세 distribution의 필수 Requires-Dist를 marker와 version specifier로 검사했습니다. 모든 필수 의존성이 충족됐고 statsmodels/LightGBM/patsy와 NumPy/SciPy/pandas의 import도 성공했습니다. sklearn wrapper 대신 LightGBM native Dataset/train API를 사용하므로 scikit-learn을 설치하지 않았습니다.

`pyproject.toml`의 `models` extra는 신규 3개 버전을 고정합니다. `requirements/day4-lock.txt`는 실제 Windows/Python3.11 환경에서 필요한 전이 의존성 closure 11개를 exact pin으로 기록합니다. 전역 환경 전체의 pip freeze가 아닙니다. clean environment 재현 시 lock을 사용하되 기존 공유 환경을 일괄 업그레이드하는 명령으로 사용하지 않습니다.

| 패키지 | 사용 버전 | Day 4 신규 설치 |
|---|---|---|
| statsmodels | 0.14.6 | 예 |
| lightgbm | 4.6.0 | 예 |
| patsy | 1.0.2 | 예 |
| numpy | 1.26.4 | 아니오 |
| scipy | 1.17.1 | 아니오 |
| pandas | 2.2.3 | 아니오 |
| packaging | 24.1 | 아니오 |
| python-dateutil | 2.9.0.post0 | 아니오 |
| pytz | 2026.1.post1 | 아니오 |
| six | 1.16.0 | 아니오 |
| tzdata | 2025.3 | 아니오 |

계산 프로세스 내 OMP/OPENBLAS/MKL/NUMEXPR thread 환경을1로 설정하고 LightGBM의 num_threads도1로 고정합니다. 부모 PowerShell/시스템의 환경변수는 변경하지 않습니다. model manifest는 사용 라이브러리·Python·thread·config·code·input hash를 기록합니다. BLAS 구현/하드웨어가 다른 환경의 비트 단위 동일성까지 보증하지 않습니다.

models extra를 설치된 프로젝트 metadata에도 반영하려고 로컬 editable 설치를 `--no-index --no-deps --no-build-isolation`로 갱신했습니다. 샌드박스 임시 metadata 파일의 접근 거부가 있어 승인된 재시도에서 완료했습니다. 외부 패키지 다운로드/업그레이드는 추가하지 않았습니다. `Requires-Dist`에 세 모델 패키지 pin이 일치하고 lock11개와 실제 버전도 일치함을 확인했습니다. 기본 Miniconda Python에서는 새 세 모델 패키지가 여전히 미설치여서 전역에 설치되지 않았음을 재확인했습니다. 갱신 후 smoke3개도 통과했습니다.
