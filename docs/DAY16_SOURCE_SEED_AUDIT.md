# Day16 Source·Seed 감사

2026-10-31 Asia/Seoul. **저장 seed 증거 감사 PASS_WITH_LIMITATIONS, 실제 source/runtime 연결 ACCESS_APPROVAL_REQUIRED**입니다. 오늘 C·D·E 가격에 접근하지 않았습니다. 실제 source 전체 byte를 확인한 것처럼 보고하지 않습니다.

## 접근 분류

| 분류 | 허용/실행 |
|---|---|
| A Manifest·문서·설정·코드 metadata | 허용·검사. Day15 Candidate의 기존28contract/105code/233evidence pin은 수정 전에 모두 일치 |
| B 저장 비Holdout evidence | 허용. 사전 pin과 기간을 확인한 Day5 forecast/OOF/fit log, Day9의38개월 Validation 가격 증거만 수치 해석 |
| C 실제 Train/Validation 원천가격 | 미승인. data/raw·data/processed open 및 전체 rehash 없음 |
| D 실제 Bridge2024-09 | 미승인·미접근 |
| E 실제 Holdout2024-10~2026-09 | 미승인·미접근·예측/성과 계산 없음 |

Day5 파일은 `artifacts/day5/20261029T004616487272Z/`이며 `manifest.json`의 SHA는 기존 Day6 설정의 pin으로 검증합니다. `all_oof_forecasts.csv`, `historical_oof_calibration.csv`, `validation_oof_calibration.csv`, `fit_log.json`은 원래 manifest의 개별 SHA를 검사합니다. 추가 실제값은 `artifacts/day9/20261030T090528446877Z/evaluation_prices.csv`의2021-07~2024-08·38행뿐입니다. 이는 Day13 Evidence Release가 pin한 이미 검증된 B 산출물이며 C의 원천 CSV를 우회 로딩한 것이 아닙니다. 읽은 범위와 역할을 별도로 기록합니다.

## 실제 저장 Seed 검사

Historical2016-04~2021-03의60origin과 Validation2021-06~2024-05의36origin을 모델별로 확인했습니다. 합계192개 model-origin·576개 raw horizon입니다. 각 모델·origin에 H1/H2/H3가 정확히 있고 중복/누락/2024-06~08 발행은 없습니다. 타깃은2016-05~2024-08 안에 있습니다. Raw forecast 파일에는 actual_price 열이 없으며 당시 미래 target과 분리돼 있습니다.

키·phase·달력 범위를 모두 검사한 뒤 숫자를 해석합니다. t−1 cutoff·t+h target·2/3/4 model step·forecast_asof·fit end/publication을 확인합니다.1248개 fit event는96origin×(SAR1+LGB point3+quantile9)입니다. SAR의 train_end/convergence, LGB의15특징·성숙 feature origin end≤o−4·label end≤o−1·max publication≤d_o·objective/quantile 구성을 논리적으로 대조합니다. 원래 Day4 사양·Day5 설정·source snapshot identity를 연결하며 오늘 fit하지 않습니다.

저장 잔차558개(Train360·Validation198)의 actual−point와 calibration score를 별도 대조했습니다. 원래 예측이 이미 존재하지만 Day5 마지막 clock에는 잔차가 미성숙했던18개는 허용된 Day9 저장 Validation actual과 연결했습니다. 새 forecast, 미발행 origin, 새 모델, 구매 성과를 생성한 것이 아닙니다.576개 예측-타깃 연결의 감사 hash와192개 vector proof를 새 read-only evidence index에 저장합니다. 실제 가격은 보고서에 출력하지 않습니다.

Horizon별 가장 이른 공개 가능 origin은 target+1 및 recorded available_at 조건으로 계산합니다. Joint는 세 target·공표가 모두 성숙한 o+4를 사용합니다. 마지막 seed origin2024-05의 Joint 공개 가능월은 가정상2024-09이며,192vector 모두 첫 최종 origin에서 가정상 성숙합니다. 원래 Day5가 실제 방문한 clock의 release와 “가장 이른 가용월”은 다릅니다. 미발행6~8월에 forecast를 보충하지 않으며 공표/잔차 갱신만 가능하다는 계약입니다.

## 발행 증거의 세 종류

| 자료 | 증명하는 것 | 증명하지 못하는 것 |
|---|---|---|
| 실제 Day5 Historical/Validation 출력 | 2026-10의 저장 실행이 논리적 과거 cutoff/fit 조건에 맞춰 재구성한 예측·OOF | 2016~2024 당시 실제 운영 발행·최초 vintage |
| 과거 contemporaneous live issuance | 이번 자료에는 NOT_VERIFIED | record_id/forecast_asof 문자열만으로 live 증거가 생기지 않음 |
| Day12~15 Synthetic native batch | 합성 source에서 실제 native backend로 계산한 immutable236batch와 논리 clock | 실제 World Bank 당시 발행 예측 |

원본 CSV 파일 SHA는 현재 저장 byte의 무결성입니다. 새 row/batch hash는 **오늘 pin된 원래 저장 row로부터 유도한 감사 hash**이며 당시 개별 발행 hash라고 표시하지 않습니다. 원래 record_id와 파일/manifest hash를 함께 보존합니다.

Read-only archive evidence 재구성은 가능했습니다. **실제 runtime restore는 차단**됩니다. SessionPermit는 합성 knowledge만 허용하고, Day5 legacy row에는 Native IssuedForecast의 per-origin history/model/feature/session envelope가 없습니다. 해당 필드를 새로 만들어 native 과거 발행처럼 보이게 하지 않았습니다. 첫 차단 이유와 proof 차이를 `seed_audit_canonical.json`에 기록했습니다. 실제 adapter 지원·과거 fit input의 독립 byte 검증은 미해결입니다.

## Source evidence levels

| 항목 | 오늘의 등급 |
|---|---|
| 허용된 B 파일·Manifest의 현재 byte | VERIFIED_CURRENT_BYTES — 저장 evidence에 한정 |
| 실제 World Bank XLSX/전체 가격 CSV의 SHA | DOCUMENTED_PREVIOUS_HASH — 오늘 재열람/재해시 안 함 |
| 저장 forecast/fit log·잔차의 논리적 as-of 일관성 | VERIFIED_RECONSTRUCTED_ASOF — 원래 학습 원천가격 byte까지 재검증한 등급 아님 |
| 과거 원시 vintage | NOT_VERIFIED — VERIFIED_HISTORICAL_VINTAGE 미달 |
| Observation별 available_at | ASSUMED_PUBLICATION_TIME — 다음 달 말 UTC |
| 실제 과거 최초 release timestamp·live issuance | NOT_VERIFIED |

**“이 평가는 공식 World Bank 가격의 수정된 단일 Snapshot과 사전 정의된 공표 지연 가정을 사용하는 pseudo-real-time historical simulation이다. 실제 당시 발표 Vintage와 최초 공표 Timestamp를 완전히 복원한 평가가 아니다.”**

이 한계를 연구 가정으로 명시하고 source/adapter·권한 gate를 충족하면 제한된 역사적 시뮬레이션 연구는 가능합니다. 실제 실시간/OOS 독립성·시장 CVaR·기업 인과효과의 증거로 바뀌지는 않습니다. Vintage 부재는 코드를 수정해 해결할 오류가 아닙니다.2020-07 HRW no.1→no.2 경계도 보존하며 구조단절을 단정하지 않습니다.

## 필요한 추가 권한·자료

독립 source/fit-history 확인에 필요한 원천은 다음입니다. 오늘은 읽지 않았습니다.

- 원래 혼합 파일: `data/processed/world_bank/20261024T012917500704Z_ea1c35082787__20261024T013704254799Z/wheat_us_hrw.csv`
- 필요한 범위: **1960-01~2024-08·776행만 분리한 검증 가능한 export**. 원래 혼합 파일에는 Bridge와 Holdout25개월도 있어 전체 로딩/전체 SHA 재계산은 현재 미승인입니다.
- 필요한 열: observation_month, price, unit, source_series, available_at, availability_basis, vintage_id.
- 목적: 원래 학습 이력·snapshot identity·첫 최종 origin의 공개 입력을 독립 확인. 실제 과거 vintage/최초 release를 복원한다는 목적은 아닙니다.
- 별도 자료: 분리본의 원본 연결 증거·SHA·생성 범위/방법, 실제 과거 vintage/release archive 또는 그 부재를 인정하는 명시적 연구 프로토콜, legacy seed proof를 보존하는 실제 adapter 검증.

**ACCESS_APPROVAL_REQUIRED**입니다. 이 감사의 추가 source 확인에 Bridge/Holdout 가격 접근을 요청하지 않습니다. 향후 실제 평가에는 별도로 Bridge/성숙 Holdout의 순차 접근 및 evaluator의24개월 정산값 접근 범위가 명시돼야 합니다.
