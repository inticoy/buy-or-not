# 버전별 스펙

| 버전 | 상태 | 한 줄 요약 |
|---|---|---|
| v1 | 종료 | requests로 알구몬 랭킹 수집, 매일 TOP 10 게시 |
| v2 | **운영 중** | 수집을 Chrome + AppleScript로 교체 |
| v3 | 계획 | 사람별 관심 키워드 알림, 소스·카테고리 재검토 |

## v1 — requests 수집

- 알구몬 `/n/deal/rank?categoryId=` 랭킹을 requests + BeautifulSoup으로 파싱
- 게임·IT·식품 TOP 10을 Discord 고정 thread에 게시
- GitHub Actions(cron-job.org 트리거)로 운영하다 로컬 launchd로 이전
- **종료 사유:** 알구몬이 자동화 요청을 Turnstile 챌린지로 막음
  - GitHub Actions: 2026-07-22부터 403 (데이터센터 IP)
  - 로컬 Mac: 2026-10-09부터 403
  - 실패해도 exit 0이라 3주 가까이 모르고 지나감

## v2 — Chrome + AppleScript (현재)

- 평소 쓰는 Chrome 프로필에 탭을 열고 AppleScript로 HTML을 읽음 (CDP 미사용)
- 파싱·중복 제거·게시는 v1 그대로
- 실패한 카테고리만 1시간 뒤 1회 재시도, 그래도 실패하면 exit 1 + Healthchecks.io 핑(선택)
- GitHub Actions 워크플로 제거 (데이터센터 IP는 계속 차단)
- 자세한 내용: [how-it-works.md](how-it-works.md), [flow.html](flow.html)

## v3 — 계획

자세한 설계: [v3-design.md](v3-design.md)

- **관심사 알림:** 상품명·가격("에어팟 프로 25만 이하")이나 설명("괜찮은 게이밍 모니터")으로 등록, 맞는 딜이 오르면 태그해서 알림. 다른 사람 대신 등록, 한 번만 알림 지원
- **자연어 인터페이스:** `@멘션`으로 말하면 Gemini가 동작으로 바꿔 실행 (사전 테스트 10/10 통과)
- **소스 확장:** hotdeal.zip 인기 게시판 추가 검토
- **상주 서버 전환:** `@멘션`에 답하려고 imposter-finder처럼 `serve`로 상주
- imposter-finder에도 같은 자연어 구조 적용
