# World Bank 월별 원본: 출처·버전·Wheat 선택 기록

확인일: 2026-10-24 (Asia/Seoul). 아래는 실제 다운로드 파일과 공식 안내에서 확인한 사실입니다. 가격의 분포·추세·모델 적합성 분석은 수행하지 않았습니다.

## 수집 provenance

| 항목 | 값 |
|---|---|
| 데이터 | World Bank Commodity Price Data (The Pink Sheet), Monthly Historical Commodity Prices |
| 공식 진입점 | https://www.worldbank.org/en/research/commodity-markets |
| 실제 요청/최종 URL | https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx |
| 파일명 | `CMO-Historical-Data-Monthly.xlsx` |
| snapshot ID | `20261024T012917500704Z_ea1c35082787` |
| 다운로드 완료 UTC | `2026-10-24T01:29:17.500704+00:00` |
| HTTP 결과 / 크기 | 200 / **586,099 bytes** |
| Content-Type | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| SHA-256 | `ea1c350827878ea3bbe30e3cda16a13fd3bd5b409b8458940dc94a36b5a33154` |
| 원본 위치 | `data/raw/world_bank/20261024T012917500704Z_ea1c35082787/CMO-Historical-Data-Monthly.xlsx` |
| 수집 기록 | 같은 디렉터리의 `manifest.json` |
| HTTP Last-Modified | `Fri, 02 Oct 2026 18:57:55 GMT` |
| 워크북 표시 갱신일 | `Monthly Prices!A4`: `Updated on October 02, 2026` |
| Excel 내부 modified | `docProps/core.xml`: `2026-10-02T15:26:16Z` |

샌드박스에서 첫 요청은 DNS 해석 실패로 끝났습니다. 승인된 네트워크 접근 재시도로 동일 공식 URL의 파일을 받았고, 다른 기관이나 비공식 데이터로 대체하지 않았습니다. 다운로드한 response body 그대로 이진 저장했으며 추출·독립 검증 전후의 SHA-256이 같습니다.

공식 [문서 묶음 페이지](https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/world-bank-commodities-price-data-the-pink-sheet)의 Document/Web Publish Date는 2026-02-03으로 표시되지만 관련 파일에는 10월 자료가 있습니다. 따라서 그 페이지의 최초 날짜를 현재 XLSX의 정확한 공표시각으로 사용하지 않습니다. Last-Modified, 내부 modified, 표시 갱신일, 수집 시각도 서로 다른 정보입니다.

## 실제 Excel 구조

| 시트 | 상태 | Day 1 취급 |
|---|---|---|
| `Mismatch Details` | hidden | 존재를 기록. 진단용 비교 내용이며 완전한 공표/수정 이력으로 간주하지 않음 |
| `Monthly Prices` | visible | 가격 원천. 헤더 5행, 단위 6행, 데이터 7~807행 |
| `Monthly Indices` | visible | 가격표와 별개. 다운로드 파일에 포함되지만 모델 입력으로 추출하지 않음 |
| `Description` | visible | 계열 정의·공급 출처·일부 수정 주석 확인 |
| `Index Weights` | visible | 원본 보존만 수행 |

`Monthly Prices`의 월 문자열은 A열의 `1960M01` 같은 **텍스트**입니다. 달력 행은 1960-01~2026-09의 801개이며, 월 중복 0·누락 월 0·원본 오름차순을 확인했습니다. B~BT에는 **71개 계열 열**이 있습니다. 이 중 `Natural gas index`는 지수 단위이므로 모든 열이 USD 가격이라고 일괄 해석하면 안 됩니다. 실제 헤더·열 좌표·단위 전체 목록은 `configs/world_bank_monthly.schema.json`과 실행 inventory에 기록했습니다.

금액은 A2/A3에서 **nominal US dollars**임을 확인했습니다. Wheat 두 계열의 단위는 각각 `($/mt)`입니다. 인플레이션 조정·환율 변환·원재료 혼합은 수행하지 않았고 USD/metric tonne로 이름만 정규화했습니다.

실제 가격표에는 U+2026 한 글자 `…`와 세 점 `...`이 결측 token으로 나타납니다. `Description!B130`은 미제공 기간을 두 점 `..`으로 표시한다고 설명합니다. 표기 불일치를 숨기지 않고 세 token을 구분해 허용하며, 빈 셀도 null로 보존합니다. 이번 Wheat의 결측 셀은 모두 U+2026입니다. 알 수 없는 문자열이나 Excel 오류를 결측으로 조용히 변환하지 않습니다.

## Wheat 관련 항목 전체 비교

| 항목 | US HRW | US SRW | Canada CWRS |
|---|---|---|---|
| 실제 가격 헤더 | `Wheat, US HRW` | `Wheat, US SRW` | **가격 열 없음** |
| 가격 열 / 정의 위치 | AL5:AL807 / Description!B48 | AK5:AK807 / Description!B49 | Description!B47만 존재 |
| 품질·종류 | 미국 hard red winter | 미국 no.2 soft red winter | 캐나다 no.1 Western Red Spring |
| 기준 시장 | 미국 Gulf 수출 기준 | 미국 Gulf 항만 인도, prompt/30일 shipment | St. Lawrence in-store 수출 기준 설명 |
| 원단위 | `($/mt)` | `($/mt)` | 이 파일에 가격 열/단위 없음; 추정하지 않음 |
| 달력 행 | 1960-01~2026-09, 801행 | 동일 801행 | 해당 없음 |
| 유효값 기간·수 | 1960-01~2026-09, **801개** | 1979-01~2026-09, **573개** | 해당 없음 |
| 결측 | **0** | **228개**, 1960-01~1978-12; 이후 결측 0 | 전부 결측인 시계열을 인위 생성하지 않음 |
| 공급 출처 표기 | Bloomberg Finance L.P.; USDA; World Bank | 동일 | Canadian Grain Commission; Thomson Reuters Datastream; World Bank라는 설명만 있음 |
| 주요 해석 한계 | 2020년 6월까지 no.1, 이후 no.2 기준으로 정의가 바뀜 | 2026년 3월판에서 2023/2024 가격 수정 명시 | 이 파일로 추출 불가 |

원본에서 `wheat`를 포함한 모든 가격 헤더와 설명 항목을 대조했습니다. Canada는 설명에 있다는 이유만으로 확보한 가격 계열 수에 포함하지 않습니다. 두 미국 계열을 평균내거나 서로의 결측을 채우지 않았습니다.

### MVP 선택: Wheat, US HRW

선택 근거는 구조와 운영 해석입니다. (1) 확보한 전체 801개월에 결측이 없어 초기 전체 흐름에서 보간·기간 절단을 강요하지 않고, (2) USD/t와 미국 Gulf 수출 기준이 가상 구매계약의 단위 연결을 설명하기 쉽고, (3) 밀가루·제빵용 원료를 가정하는 MVP와 hard winter wheat의 품질 맥락을 연결할 수 있습니다. 실제 기업의 구매 규격을 관측한 것은 아니며 Gulf 기준가격을 모든 지역의 실제 납품가격으로 일반화하지 않습니다.

SRW도 같은 단위·기준 시장의 별도 유효 후보이며 1979년 이후 자료만으로도 확장 가능합니다. HRW 선택은 예측 오차·변동성·비용 절감 성과를 비교해 고른 것이 아닙니다. Day 1에는 그러한 분석을 하지 않았습니다.

HRW의 장기 기록이 품질상 완전히 동질적이라는 뜻은 아닙니다. 원본 설명상 2020-06까지 no.1, 이후 no.2가 연결돼 있으므로 **2020-07 정의 경계**를 Day 2 감사 대상으로 남깁니다. 원본 계열을 임의 보정하거나 이전/이후 가격을 합성하지 않습니다. 개발기간 범위·해석 변경이 필요하면 holdout 성과를 보기 전에 근거와 사양 변경을 기록합니다.

## 공표·수정·vintage 위험

- 최신 안내 페이지는 2026-10-02의 갱신과 다음 2026-11-03 갱신 예정을 표시했고, 파일의 마지막 관측은 2026-09입니다. 이는 이번 snapshot의 관측 사례이며 모든 역사적 월에 동일한 발표일·지연을 보장하지 않습니다.
- `Description!B126`에 **2026년 3월 Wheat US SRW와 phosphate rock의 2023/2024 가격 수정**이 명시돼 있습니다. 과거 관측값이 사후 변경될 수 있음을 직접 확인한 증거입니다.
- `Description!B130`은 2026년 8월판 grain 가격의 일부 불일치가 formatting 문제였고 9월에 수정됐음을 설명합니다. 영향받은 모든 값과 원래 값은 이 주석만으로 복원할 수 없습니다.
- hidden `Mismatch Details`에는 비교표가 있지만 원본/비교본의 전체 timestamp와 모든 역사적 배포본이 제공되는 것은 아닙니다. 이를 revision database나 최초 발표값으로 해석하지 않습니다.
- 현재 확보물은 **2026-10-24 수집 snapshot 하나**입니다. `vintage_id`는 수집 버전 ID이며 과거 월의 최초 발표 vintage가 아닙니다. 최신 파일의 최신 수정값을 사용하므로 향후 평가는 `latest-vintage / pseudo-real-time`입니다.
- `available_at`은 관측월 다음 달 말이라는 **가정**을 적용했습니다. `retrieved_at`이나 HTTP Last-Modified를 과거 각 관측의 availability로 대체하지 않습니다. 월말 t에 t-1 가격만 사용하는 기존 설계는 유지합니다.
- 미래 다운로드의 바이트 동일성을 보장하지 않습니다. 동일 파일명/URL이 바뀔 수 있으므로 새로운 snapshot을 만들고 해시를 확인한 뒤 명시적으로 채택해야 합니다. 현재 config의 원본 해시 불일치는 실패합니다.

## 이용조건과 재배포 시 출처 표시

[World Bank Summary Terms of Use](https://data.worldbank.org/summary-terms-of-use)와 [Data Access and Licensing](https://datacatalog.worldbank.org/public-licenses)을 확인했습니다. 기본 조건은 CC BY 4.0과 World Bank 추가 조건이며, 데이터/지표 metadata의 별도 조건과 제3자 권리 예외가 우선할 수 있습니다. 원본 셀의 copyright/license/terms 관련 별도 문구는 발견하지 못했으나, 이것이 모든 제3자 권리가 해소됐음을 입증하지는 않습니다.

실제 사용 출처 표기: “The World Bank: Commodity Price Data (The Pink Sheet), Monthly Historical Commodity Prices; Wheat, US HRW / US SRW. Providers as identified in the workbook: Bloomberg Finance L.P.; US Department of Agriculture; World Bank. Retrieved 2026-10-24 UTC.” 원본은 변경하지 않았고 파생 CSV는 월 라벨·nullable 숫자·단위 이름·provenance를 정규화한 추출물임을 표시합니다. World Bank의 프로젝트 승인/보증을 암시하지 않습니다. 현재 raw/processed 파일은 기존 `.gitignore` 대상이며 commit/push하지 않았습니다.
