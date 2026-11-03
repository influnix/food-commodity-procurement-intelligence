# 프로젝트 최종 인수인계

**Portfolio MVP: COMPLETE**

**Final Holdout Research Evaluation: PENDING AUTHORIZATION / SOURCE GATE**

Food Commodity Procurement Intelligence는 가격예측을 구매 의사결정·재고·비용·서비스에 연결하는 포트폴리오 MVP입니다. 월별 예측·rolling backtest·동일 조건 대표2정책·증거 추적·저장 결과 재현의5조건을 충족했습니다. 실제 기업의 조달 데이터를 관측한 시스템이나 절감 실적 보고서는 아닙니다.

## 검증한 성과와 불리한 결과

World Bank Wheat US HRW의 기존 수정 snapshot과 명목 USD/t를 사용했습니다. 월말t의 가용 가격은t−1까지, target은납품t+1/2/3입니다. Validation36origin·108예측/model·38고유 target, expanding fit과 label/publication 성숙 규칙을 검증했습니다. 기존 Validation MAE는 SeasonalNaive100.0296, SARIMAX41.8757, LightGBM48.6620입니다. SARIMAX의 baseline 대비 MAE 개선58.1367%는 같은 Validation에서 관측한 결과입니다.

| 대표 가상 운영 비교 | Fixed | FA SARIMAX |
|---|---:|---:|
| 총 가상비용USD |1,351,501.68|1,365,914.16|
| Fill Rate |100%|99.4737%|
| 부족 |0t|20t|
| 평균 월말재고 |116.3158t|46.3158t|

FA 비용이14,412.48USD(+1.0664%) 높았습니다. 낮은 재고·매입/보관비보다 부족 패널티가 컸고 Runoff/마지막 상태의 공급 제약이 영향을 줬습니다. 예측 MAE 개선이 구매비용 개선을 보장하지 않는다는 것을 원장·제약·계정으로 설명했습니다. 이는 실제 Validation 가격+가상 업체·수요·비용 환경의 한 역사 경로이며 기업 절감·인과효과가 아닙니다.

SARIMAX RN/RA와 LightGBM FA/RN/RA의 추가5정책·OOF·quantile·joint bootstrap·CVaR는 확장 증거입니다. Day10 민감도는 사후 운영 리스크 진단이며 새로운 기본값을 선택하지 않았습니다. CVaR는 제시한 경험적 시나리오의 계획비용 tail이지 실제 시장의 실현 위험 보장이 아닙니다.

## 구현·검증 인수인계

`src/`는 source/as-of·features·forecasting·uncertainty·policy·LP·engine·evaluation을 구분합니다. Day15에서 horizon Calibration과 full-vector Joint를 분리하고 raw point/quantile/interval 검증을 통합했습니다. Day16은 공통 준비 함수에 optional factory 두 개를 추가해 기존 API 기본값을 보존하고, **최종 합성 진입점이 HorizonSequentialOOF를 명시적으로 선택**하도록 연결했습니다. 실제 capability는 추가하지 않았습니다.

동일 초기 상태·동일 외생경로·정책별 독립 재고/pipeline·현재q만 실행·Runoff·수령월 비용·최종 단회 말기를 유지합니다. 실제값은 evaluator만 소유하고 정책에는 현재 공개 context만 전달합니다. 설정·환경·source/seed·코드 SHA, 회귀·독립 검산·반복 바이트 일치를 새 Handoff에 연결합니다. 과거 결과·Candidate 파일은 보존하며 README는 원래 prefix를 유지해 최신 안내만 추가했습니다.

## 연구평가의 남은 조건

저장된 실제 seed576행·192vector의 달력·원래 모델사양·논리 cutoff/fit·잔차558개와 잔여18개 target 연결을 확인했습니다. 그 기록은 사후 재구성입니다. 실제 과거 운영 발행이나 원시 vintage·최초 release timestamp는 검증되지 않았습니다. 새 audit hash를 당시 native 발행 증거로 꾸미지 않았습니다.

실제 source byte와 최초 origin의 학습 이력을 독립 검증하려면 [Source 감사](DAY16_SOURCE_SEED_AUDIT.md)의 제한된 Train/Validation export·출처 증거·허용 범위가 필요합니다. 현재 runtime은 실제 source knowledge/legacy archive를 받지 않으므로 관련 adapter 구현·검증도 남습니다. 과거 vintage 부재를 인정한 pseudo-real-time 연구는 가능하지만 source gate를 PASS로 위조하거나 현재 승인 없이 실행할 수 없습니다.

실제 OOS Holdout은 **미평가·잠금**입니다. 현재 최종 실제 평가 명령은 미구현입니다. [Release Protocol](DAY16_FINAL_RELEASE_PROTOCOL.md)은 비실행 계약과 후속 새 freeze·digest 승인·단회 식별자·실패/공개/재실행 순서를 정합니다. 이 Handoff를 실제 평가 승인으로 사용하지 않습니다.

추가 모델·튜닝·새 horizon·스트레스 world·대시보드가 없어도 MVP는 완료입니다. 최종 연구평가를 보류한 이유와 불리한 성과, 데이터의 한계까지 재현 가능한 증거로 남긴 상태로 인수인계합니다.
