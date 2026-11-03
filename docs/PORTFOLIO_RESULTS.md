# Portfolio results and evidence boundaries

MVP acceptance는 **5/5 PASS**입니다. 월별 예측, rolling-origin backtest, 동일 조건2정책 비교, 예측→발주→입고→비용 추적, 저장 결과 재현을 기존 로컬 archive에서 확인했습니다. 원천·전체 실행 Evidence는 Git에서 배포하지 않습니다.

[집계 Evidence](../evidence/portfolio_summary.json)는 고정된 Day13 summary와 Day17 검증 기록에서 선별한 비민감 집계입니다. 원본 경로·SHA로 로컬 archive와 연결할 수 있습니다. 원시 가격·개별 예측·월별 원장·미래 경로는 포함하지 않으며 집계 파일 무결성이 전체 실험 재현을 뜻하지 않습니다.

## Validation: 실제 가격과 가상 운영

2021-06~2024-05의36origin×3horizon, 모델별108개입니다. 고유 target은2021-07~2024-08의38개월입니다. MAE는 Seasonal Naive100.0296, SARIMAX41.8757, LightGBM48.6620 USD/t입니다. 성과에 맞춰 모델을 재튜닝하지 않았습니다.

공통 초기재고200t·빈 pipeline·수요100t/월·창고400t, A lead2/cap80/premium2%, B lead1/cap100/premium8%입니다. 보관3·부족1500·폐기1·말기편차9 USD/t, 종료목표200t·salvage0입니다.36결정·38원장월(Active35/Runoff3), 수령월 단회비용·최종월 단회말기를 유지했습니다.

| 지표 | Fixed | FA SARIMAX |
|---|---:|---:|
| Total Simulated Cost USD | 1,351,501.68 | 1,365,914.16 |
| 매입비 USD | 1,336,441.68 | 1,328,834.16 |
| 보관비 USD | 13,260.00 | 5,280.00 |
| 부족비 USD | 0 | 30,000.00 |
| 말기비 USD | 1,800.00 | 1,800.00 |
| Fill Rate | 100% | 99.4737% |
| Unmet Demand t | 0 | 20 |

FA−Fixed는 **+14,412.48USD(+1.0664%)**입니다. Active의−38,415.36USD가 Runoff의+52,827.84USD로 역전됩니다. 마지막 결정 시 FA 재고20+기존 pipeline80+현재 최대주문180=280t는 이후 수요300t보다 작았습니다. 이 상태부터20t 부족이라는 물리적 제약을 확인했으며 예측오차 하나의 인과효과로 단정하지 않습니다.

## Extensions and synthetic qualification

Day9의7정책·Day10의11개 운영조건은 실제 Validation 가격+가상 운영의 탐색적 평가입니다. 셀을 독립 시장 표본으로 세거나 최적 기본정책을 새로 선정하지 않았습니다.

Day12~17은 별도 합성 world의 Native backend·Legacy restore·Calibration·Joint·회계 검증입니다. Day17 기록은613tests,154결정/168원장/132LP,5632Joint경로 독립 검산,111개 결정적 파일 반복 일치입니다. 실제 Source 연결·Holdout 성능 증거가 아닙니다.

Day15에서 Horizon별 Calibration·raw 유효성 정합성을 수정했습니다. [방법론 수정](DAY15_METHOD_REMEDIATION.md)과 [Legacy 계약](DAY17_LEGACY_SEED_CONTRACT.md)에 근거를 보존합니다. 모델·정책·α/λ·운영 사양은 유지했습니다.

## 한계와 현재 잠금

수정 단일 Snapshot·가정 공표시각의 pseudo-real-time이며 과거 vintage/최초 release/live 발행은 미검증입니다. 낮은 Coverage·경험적 시나리오 확률·단일 경로/원재료·가상 운영·Validation 선택편향·계획창/Runoff·말기근사가 남습니다. 독립 OOS·시장 CVaR·기업 절감·인과효과를 주장하지 않습니다.

실제 Bridge/Holdout은 미평가·잠금이고 Day18 ACCESS_APPROVAL_REQUIRED입니다. README 개편 후 과거 Candidate가 현재 checkout 전체를 동결한다고 표시하지 않습니다.
