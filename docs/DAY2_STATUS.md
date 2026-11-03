# Day 2 실행 결과

실행일: 2026-10-24 Asia/Seoul. **Day 2 완료**, Day 3은 시작하지 않았습니다. 원본·Day 1 CSV와 기존 실행 기록을 보존했고, 새 다운로드·의존성 설치·모델·예측구간·시뮬레이션·최적화·holdout 성능 평가·Git commit/push는 수행하지 않았습니다.

## 1. 생성·수정한 파일

생성:

- `configs/day2.toml`: Day 1 manifest 해시, split 파일, 고정 감사 threshold, holdout 통계 비활성
- `configs/splits.toml`: 두 날짜 후보·선택안·정의 경계·이력 조건·holdout 잠금
- `src/food_procurement_intelligence/data/audit.py`: 원본/CSV 전체 대조, 개발 구간 감사, 날짜 분할 보고서 CLI
- `src/food_procurement_intelligence/data/availability.py`: 과거값 as-of 접근과 미래 Feature/학습 label/holdout 차단
- `src/food_procurement_intelligence/evaluation/__init__.py`, `evaluation/splits.py`: 월 산술·origin/target·성숙도·overlap·분할 요약
- `tests/test_splits_and_availability.py`: 날짜·toy 값·보고서 경계 테스트
- `docs/DATA_AUDIT.md`, `docs/SPLIT_DESIGN.md`, 본 문서

수정: README, AGENTS의 정보 경계 규칙, PROJECT_CHARTER, DECISION_TIMELINE, EVALUATION_PROTOCOL, DATA_DICTIONARY, ROADMAP. 날짜 조정은 [분할 설계](SPLIT_DESIGN.md)에 이유를 기록했습니다. Day 0/1 설정·실행 기록·수집/추출 코드·기존 테스트·실제 데이터 파일은 변경하지 않았습니다.

최종 실행 산출물:

```text
artifacts/day2/20261024T015928132214Z/split_freeze.json
artifacts/day2/20261024T015928132214Z/data_audit.json
artifacts/day2/20261024T015928132214Z/sample_calendar.csv
artifacts/day2/20261024T015928132214Z/run_manifest.json
```

시도 과정의 `20261024T015648998247Z`, `20261024T015809272974Z`도 덮어쓰지 않고 보존했습니다. 최종 run은 120개월 평가 warmup과 개별 과거 sample 조건의 구분, 보고서 코드 경로의 독립성까지 반영한 버전입니다. 사용자에게 제시하는 수치는 위 최종 run 기준입니다. 가격을 담은 train/validation/holdout CSV를 따로 복제하지 않고 날짜 config와 마스크로 분할합니다.

## 2. 실제 데이터 감사 결과

- 1960-01~2026-09의 801개월, 유효 가격 801, 결측/중복/달력 누락/0·음수/비유한 가격 모두 0입니다.
- 원본과 대표 CSV의 801개 행·14개 필드를 모두 다시 대조해 일치했습니다. 원본·CSV·Day 1 manifest 해시도 고정값과 일치했습니다.
- 원단위 `($/mt)`와 nominal US dollars 설명, 계열 정의·수정 주석을 원본에서 재확인했습니다.
- 날짜 선택 후 개발 구간 1960-01~2024-08에서만 고정 ±20% 월 변화 기준을 적용했습니다. 7개월이 표시됐고 수정/삭제는 0건입니다. 1973-08 +67.98%, 2022-03 +24.53% 등을 그대로 보존했습니다.
- holdout/bridge의 가격 수준·변동률·급변동 개수는 계산/출력하지 않았습니다. 전체 가격의 구조적 무결성 검사 결과만 공개합니다.
- 관측 기간별 coverage와 7개 표시 월은 [감사 문서](DATA_AUDIT.md)에 있습니다. 이는 본격 EDA나 원천 오류 판정이 아닙니다.

## 3. 2020-07 정의 변경 처리

전체 기간을 유지하고 정의 변경 경계 및 feature/target crossing flag를 날짜 메타데이터로 관리합니다. 가격 조정이나 경계 전후 임의 삭제는 하지 않았습니다. 전후 구분 평가, rolling/expanding 비교, 경계를 가로지르는 vector/pair 제외는 후속 validation 민감도입니다.

경계 전 726개월, 이후 75개월입니다. 경계 월 변화 +11.95%만으로 구조적 단절이나 품질 변경의 인과효과를 단정할 수 없습니다. 이후 75개월만 사용하면 초기 학습 120개월 조건을 충족하지 못합니다. 경계 flag의 역사적 공지 시점도 확인하지 못했으므로 바로 모델 predictor로 쓰지 않습니다.

## 4~5. 최종 날짜와 표본 수

| 구간 | Target/원시 관측 날짜 | 월수 | 완전 vector origin | origin 수 | target-pair 수 |
|---|---|---:|---|---:|---:|
| Train 정적 후보 | 1960-01~2021-06 | 738 | 1960-02~2021-03 | 734 | 2,202 |
| Validation | 2021-07~2024-08 | 38 | 2021-06~2024-05 | 36 | 108 |
| Bridge | 2024-09 | 1 | 주 평가 없음 | — | — |
| Holdout | 2024-10~2026-09 | 24 | 2024-09~2026-06 | 22 | 66 |

Train origin은 실제 학습량이 아닌 구조적 후보 수입니다. 첫 validation fit 2021-06에는 **2021-05까지 737개월**만 관측됐고, 정적 Train vector 중 **733개/2,199쌍**, 마지막 origin **2021-02**만 target이 성숙했습니다. 각 모델의 실제 lag 요건은 Day 3 이후 별도로 적용합니다. 120개월 평가 warmup을 모든 과거 후보에 강요하지 않아 불필요한 학습 이력 손실을 피했습니다.

Holdout tail의 부분 horizon을 포함한 날짜 후보는 24 origins, h별 **24/23/22쌍**, 합계 69쌍입니다. 주 비교 66쌍과 tail 3쌍을 섞지 않습니다. 실제 holdout 가격·예측·점수는 전혀 조회/평가하지 않았습니다.

대안 B는 holdout 2023-10~2026-09, validation origin 2020-06~2023-05입니다. 가격/성능을 비교하지 않고 기존 24개월 설계의 일관성을 근거로 A를 선택했습니다. 설정 사본과 두 후보의 날짜·개수는 split_freeze에 있습니다.

## 6. 다중 horizon 누수 방지

- origin `t`의 feature는 관측월 `<=t-1` 및 `available_at<=d_t`여야 합니다.
- 학습 sample `o`의 모든 target은 `o+h<=t-1` 및 공표 timestamp 조건을 만족해야 합니다. 완전 3-horizon vector는 `o<=t-4`입니다.
- 고정 구간은 target 합집합 overlap을 금지합니다. 월별 재학습에서는 과거 validation 정답이 성숙하면 사용할 수 있지만 현재 fold의 미래 target과는 겹치면 안 됩니다.
- 기존 Day 0 마지막 validation origin `a-4`는 첫 holdout 결정 때 미공표 label을 포함했습니다. **`a-5`로 정정**하고 36 origins를 한 달 앞당겼습니다. 이는 값/성능 기반 조정이 아닙니다.
- 2024-09 bridge는 한 달의 정보 지연 때문에 선택에서 제외한 target이며 원본에서 삭제하지 않았습니다. 추가적인 전후 고정 폭 embargo는 적용하지 않습니다.

수식·예시·적용 범위·부분 horizon 규칙은 [분할 설계](SPLIT_DESIGN.md)를 따릅니다.

## 7. 구현·재현 명령

기존 Python 3.11.5 `.venv`를 유지하고 표준 라이브러리만 사용했습니다.

```powershell
.\.venv\Scripts\python.exe -m food_procurement_intelligence.data.audit --config configs/day2.toml
.\.venv\Scripts\python.exe -m pytest -q
```

감사 CLI exit code 0. 새 run 디렉터리를 만들며 기존 결과를 덮어쓰지 않습니다. split freeze는 가격 감사 전에 날짜 규칙·설정 해시를 기록하고, run manifest는 입력/코드/출력 해시와 holdout_locked를 기록합니다.

실제 guarded store도 연결해 첫 validation history가 737개월·마지막 월 2021-05인지 확인했고, 첫 holdout origin 2024-09의 history 요청이 HoldoutLockedError로 차단됨을 확인했습니다. repr은 가격을 포함하지 않습니다. 개발 API에는 unlock이나 무필터 전체 가격 export가 없습니다.

## 8. 전체 테스트 결과

**74 passed in 0.40s**, exit code 0. Day 0~1의 53개를 모두 재실행했고 Day 2의 21개 검증을 추가했습니다. 네트워크 연결이나 실제 World Bank 가격 fixture를 사용하지 않았습니다.

확인 범위: 시간 순서·구간 경계, 연말/윤년, t-1 cutoff, horizon별 target/step, 최소 평가 이력과 샘플 조건의 구분, 미성숙/지연 label, 정적 및 현재 fold overlap, tail·누락 월, 설정 복제, holdout 값/원점을 향한 접근 차단, 미래/holdout toy 값 변경 시 개발 view/감사 불변, 극단값 보존, 실제 CLI 보고서 형식입니다.

integration test에서 입력 프로젝트와 설치 코드 위치가 다를 때 provenance 경로 계산이 실패하는 문제를 발견해 코드 모듈 기준 경로로 수정한 뒤 전체 테스트를 통과했습니다. 테스트 중 실패를 성공으로 집계하지 않았습니다. 가격 예측·성능 지표·solver는 구현하지 않았으므로 검증하지 않았습니다.

마지막 무결성 확인: 문서 내부 링크 35개 정상, 최종 report manifest의 출력 해시 3개와 코드 해시 3개 일치, Day 1 manifest에 기록된 기존 수집/추출 코드 해시 3개도 현재와 일치했습니다. TOML 설정 4개 파싱 성공, synthetic 폴더에 marker 외 데이터 0개입니다.

## 9. 남은 위험

현재 snapshot의 재현성은 확보했지만 역사적 발표 당시 vintage를 복원한 것은 아닙니다. `available_at`도 가정입니다. 장기 nominal 가격·품질 정의 변화·공급업체 계약 가정의 적합성은 별도 문제입니다. 오늘 날짜 freeze는 최종 모델·정책·seed 잠금과 다릅니다.

Holdout 잠금은 프로그래밍 API 경계입니다. 기존 로컬 원본/CSV를 OS 수준에서 암호화하거나 접근권한으로 봉인한 것은 아닙니다. 후속 모델이 직접 전체 CSV를 읽으면 경계를 우회할 수 있으므로 AGENTS에 guarded store 사용을 기록했습니다.

## 10. Day 3 구체 작업 — 아직 시작하지 않음

1. guarded history를 입력으로 쓰는 lag/rolling 특징과 원천월 provenance를 구현합니다. centered rolling·P_t 참조·전체 표본 전처리를 차단합니다.
2. source/target별 가용성 검사를 유지하며 Seasonal Naive를 `target_month-12`에서 생성합니다. 최신 관측 기준 step 2/3/4를 구분합니다.
3. 고정 validation 36 origins/108 pairs에서만 expanding rolling-origin 실행기를 연결합니다. 매월 성숙한 label만 fit하며 holdout은 계속 잠급니다.
4. MAE와 origin별 학습 이력으로만 계산한 MASE 분모를 구현하고 0 분모/결측·실패 규칙을 검증합니다. 스케일러·lag에 필요한 추가 마스크를 달력 purge와 구분합니다.
5. 미래 관측값을 바꿔도 과거 특징·예측이 바뀌지 않는 테스트와 모델별 공통 평가 마스크를 확인합니다. SARIMAX/LightGBM/예측구간/최적화는 아직 추가하지 않습니다.

Day 3은 별도 지시를 받은 뒤 진행합니다.
