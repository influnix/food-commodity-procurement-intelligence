# Day 11 Release Gate

READY는 기술적 준비 상태이며 실제 Holdout 실행 승인이 아닙니다. 이 단계에는 실제 데이터 unlock capability가 없습니다. 최종 실제 상태는 생성된 Day11 run의 `release_gate.json`과 `DAY11_STATUS.md`를 따릅니다.

## 상태 판정

- **BLOCKED**: Freeze digest·계약/코드/증거 hash 불일치, 원천파일 접근 시도 등 무결성/권한 위반입니다. 이전 freeze로 실행하지 않습니다.
- **NOT_READY**: 필수 증거가 FAIL 또는 NOT_VERIFIED입니다. 기술적 누락과 보완 범위를 보고하고 실제 실행을 열지 않습니다.
- **READY**: 정해진 모든 필수 조건이 PASS입니다. 그래도 `actual_holdout_execution_allowed=false`, `holdout_locked=true`이며 사용자 명시 승인이 필요합니다.

빈 체크리스트나 누락된 조건은 READY가 될 수 없습니다. 잘못된 상태값도 BLOCKED입니다. 단위테스트는 세 상태와 READY의 접근 거부를 모두 검사합니다.

## 필수 증거

기존전체pytest와새검증, Baseline회귀, split/달력·7정책·모델/특징·OOF/보정·scenario/seed·운영/말기·metric 동결, Synthetic Preflight, 원천무접근, 이전artifact보존, solver/환경, 한계고지를 검사합니다. 추가로 실제 순차store/Bridge capability, 신규origin forecast adapter, OOF/scenario phase 지원,22/24 productionrunner/집계, 새origin의실제backend연결검증이 필요합니다.

현재 개발store·saved adapter·OOF phase/generator의validation-only guard는 의도적으로 유지합니다. Day9 CLI와Day10 보고코드의Validation고정값도 실평가경로에 사용할 수 없습니다. 날짜에 맞춘 fake backend와Synthetic pool이 통과한 것을 실제 production지원으로 판정하지 않습니다. 미해결 항목은 해당 run에NOT_VERIFIED/FAIL로 남깁니다.

## 해시와 변경

Freeze는 config·기존사양·관련코드·문서·테스트상태·증거파일을 실제파일SHA로 핀합니다. 원천가격값은열지않고이전검증hash와메타데이터를재사용합니다. 현재raw byte재검증을했다고표현하지않습니다. Manifest 자체는별도digest와보고서로연결합니다.

사용자승인은특정Freeze digest에연결돼야합니다. Manifest/관련파일이변하면기존freeze를무효로보고새감사·Synthetic재검증·새승인이필요합니다. 이hash체계는로컬무결성추적이며서명/OS보안경계를대체하지않습니다.

## 실제 실행 전에 필요한 작업

별도범위에서순차공표가격capability와새origin forecast/OOF/집계adapter를구현하고Synthetic로검증해야합니다. 기존개발잠금을제거하거나실제Holdout을사용해기능을디버깅하지않습니다. 그뒤새freeze·전체검증·명시승인을거쳐야실제단회평가를논의할수있습니다. Day11에서는이후작업을시작하지않습니다.
