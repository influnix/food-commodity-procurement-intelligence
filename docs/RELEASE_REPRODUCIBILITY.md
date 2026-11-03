# Release reproduction contract

## A/B — 원천 없는 테스트와 합성 fixture

Python3.11·pytest8.3.5·기존 `requirements/day7-lock.txt`를 사용합니다. GitHub Actions는 Ubuntu22.04에서 아래 설치/실행 계약을 사용합니다. Day19 로컬에는 패키지를 새로 설치하지 않습니다.

```sh
python -m pip install -r requirements/day7-lock.txt
python -m pip install pytest==8.3.5
python -m pip install --no-deps -e .
python scripts/ci/run_contract_tests.py
python scripts/release/audit.py
```

`configs/ci.toml`에 명시한 parser·분할/as-of·특징·모형 계약·잔차/Joint·LP/CVaR·재고/수령월 회계·Runoff·미래변경 불변성만 검사합니다. 테스트 내부 toy fit/solver는 실제 시장 신규 학습·평가가 아닙니다. Runner는 checkout data/artifacts의 Python open과 socket 연결을 차단합니다. 임시 디렉터리의 toy fixture는 허용합니다. Python guard는 OS/FD/C extension 보안 경계가 아닙니다.

Workflow 권한은 contents:read, checkout credentials 미보존, Secret/원천 다운로드·artifact 업로드 없음입니다. 기존 lock은 Windows/Python3.11.5 기록이며 Linux 호환성은 실제 CI 성공 여부로 별도 확인합니다. 모델 결과에 맞춘 pin 변경은 하지 않습니다. CI 통과를 과거613개 전체 또는 원래 Evidence의 완전 재현으로 확대하지 않습니다.

## C — 별도 실제 원천 필요

[World Bank Commodity Markets](https://www.worldbank.org/en/research/commodity-markets)의 Monthly Historical Commodity Prices가 출처입니다. [Snapshot·이용조건](WORLD_BANK_SOURCE.md)을 확인하세요. 최신 파일이 과거 Snapshot과 같다고 가정하지 않습니다. Release는 원천을 새로 조회하거나 다운로드하지 않습니다.

자료 소유자가 별도 승인된1960-01~2024-08·776개월 비Holdout CSV와 생성 Manifest·외부 SHA를 준비해야 합니다. 제안 경로는 `data/approved_exports/final/wheat_history_through_202408.csv`이며 열은 observation_month, price, unit, source_series, available_at, availability_basis, vintage_id입니다. 목적·정확한 경로·기간·열·역할을 지정한 승인 전에는 읽거나 자체 생성하지 않습니다. 혼합801개월 원천을 읽어 분리하는 것은 현재 승인 범위가 아닙니다.

실제 store/permit·Runtime·Holdout 실행 capability는 비활성입니다. 자료를 구했다고 잠금이 해제되지 않습니다. 실제 fit/평가·순차 Bridge/Holdout 접근에는 별도 승인·새 검증·새 실행 Candidate가 필요합니다. 이번에 실제 실행 명령을 제시하지 않습니다.

## D — 로컬 archive 필요

Day0~18 artifacts와 실제 source는 로컬에 보존하고 업로드하지 않습니다. 과거613개 테스트에는 archive의 hash/존재 검사도 포함되므로 bare clone에서 전체 pytest를 보장하지 않습니다.613passed는 Day17 저장 결과, CI는 별도 선택 범위입니다.

README와 gitignore는 승인된 Release 변경이며 원문은 로컬 `artifacts/day19/before/`에 보존합니다. Day17 Candidate bytes는 보존하지만 README pin 불일치를 숨기지 않습니다. 과거 preservation assertion을 약화하지 않으며 향후 실제 평가는 새 검증·digest가 필요합니다.

`evidence/portfolio_summary.json`은 원시/월별 가격을 포함하지 않는 집계 인용입니다. source SHA는 archive 연결이지 파일 배포나 실제 원천 재검증을 뜻하지 않습니다. 코드 라이선스는 미선택, 데이터 재배포 허가는 미확정입니다.
