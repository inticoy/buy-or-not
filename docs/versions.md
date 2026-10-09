# 버전별 스펙

| 버전 | 상태 | 한 줄 요약 |
|---|---|---|
| v1 | 종료 | requests로 알구몬 랭킹 수집, 매일 TOP 10 게시 |
| v2 | v3에 포함 | 수집을 Chrome + AppleScript로 교체 |
| v3 | **운영 중** (2026-10-09~) | hotdeal.zip TOP 10, 관심사 DM 알림, `@멘션` 자연어 봇 |

## v1 — requests 수집

- 알구몬 `/n/deal/rank?categoryId=` 랭킹을 requests + BeautifulSoup으로 파싱
- 게임·IT·식품 TOP 10을 Discord 고정 thread에 게시
- GitHub Actions(cron-job.org 트리거)로 운영하다 로컬 launchd로 이전
- **종료 사유:** 알구몬이 자동화 요청을 Turnstile 챌린지로 막음
  - GitHub Actions: 2026-07-22부터 403 (데이터센터 IP)
  - 로컬 Mac: 2026-10-09부터 403
  - 실패해도 exit 0이라 3주 가까이 모르고 지나감

## v2 — Chrome + AppleScript

- 평소 쓰는 Chrome 프로필에 탭을 열고 AppleScript로 HTML을 읽음 (CDP 미사용)
- 파싱·중복 제거·게시는 v1 그대로
- 실패한 카테고리만 1시간 뒤 1회 재시도, 그래도 실패하면 exit 1 + Healthchecks.io 핑(선택)
- GitHub Actions 워크플로 제거 (데이터센터 IP는 계속 차단)
- 자세한 내용: [how-it-works.md](how-it-works.md), [flow.html](flow.html)

## v3 — 관심사 알림과 자연어 봇 (현재)

자세한 설계: [v3-design.md](v3-design.md), 동작: [how-it-works.md](how-it-works.md)

- **매일 TOP 10:** 알구몬 카테고리 3개 → hotdeal.zip 인기 1개 (카테고리 랭킹은 요청 시)
- **관심사 알림:** 상품명·가격 또는 설명("괜찮은 게이밍 모니터")으로 등록, 매시 30분 새 딜을 훑어 맞으면 알림. 대신 등록, 한 번만, 가격 인하 재알림
- **`@멘션` 봇:** Gemini가 말을 해석해 등록·해제·목록·검색·랭킹 보기
- **조용한 스레드 + DM:** 스레드 글은 모두 `@silent`, 받을 사람에게만 DM
- **알림 키워드:** 핫딜 스레드 고정 메시지에 전체 알림 목록, 변경 시 자동 수정
- **남은 것:** hotdeal.zip 인기 특성 조사(스냅샷 수집 중), imposter-finder에 같은 자연어 구조 적용
