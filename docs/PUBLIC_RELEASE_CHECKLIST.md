# Public release — owner checklist

이번에는 PRIVATE만 허용합니다. 소유자가 아래 확인 뒤 직접 결정하며 Public 변경을 자동화하지 않습니다. 코드 라이선스도 임의로 선택하지 않습니다.

- [ ] 모든 branch/tag/commit 이력의 Secret·원천·파생가격·개인 경로/식별정보 검사. Public 전환 시 과거 이력도 노출됨.
- [ ] 발견된 Secret 폐기/재발급과 필요한 이력 조치의 별도 승인. 임의 삭제·force push 금지.
- [ ] World Bank/제3자 조건과 원천·파생자료·그림·집계 재배포 권리/출처 표기 검토.
- [ ] 과거 Actions 로그·캐시·artifact·실패 run, Release·Issue/PR 첨부물 확인.
- [ ] 개인 이메일·절대경로·인증정보·비공개 설정 제거, Git author noreply 확인.
- [ ] **소유자가 코드 License 선택**, 데이터 이용조건과 구분.
- [ ] README·모든 Markdown 링크/이미지/Evidence가 Git tree에 존재하는지 확인.
- [ ] bare clone CI 실행. 원천 없는 테스트/합성/원천 필요/archive 필요를 구분.
- [ ] 수동 원천 준비의 공식 출처·snapshot/hash·수정 위험·접근 승인·잠금 확인.
- [ ] 실제 Validation+가상 운영과 합성 통합 구분. 기업 절감·인과효과·Holdout 성능으로 표현하지 않음.
- [ ] MVP COMPLETE와 Source/Seed NOT_VERIFIED·Holdout 잠금을 함께 명시.
- [ ] 최신 CI SHA/default main 동기화, 최소 권한·Secret 출력·원천 다운로드 부재 확인.
- [ ] 이후 기능은 별도 branch/PR·사전 검증·원본 결과 보존. 실제 평가/Public 전환은 별도 승인.
- [ ] Release tag는 소유자 승인 후 검증 SHA에만 생성. 기존 이력/tag 덮어쓰기 금지.
