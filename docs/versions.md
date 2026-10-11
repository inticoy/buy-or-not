# 버전별 스펙

| 버전 | 상태 | 한 줄 요약 |
|---|---|---|
| v1 | 종료 | requests로 핫딜 모음 사이트 랭킹 수집, 매일 TOP 10 게시 |
| v2 | v3에 포함 | 수집을 Chrome + AppleScript로 교체 |
| v3 | 종료 (2026-10-09~11) | 다른 모음 사이트 인기 TOP 10, 관심사 DM 알림, `@멘션` 자연어 봇 (맥 상주) |
| v4 | **운영 중** (2026-10-11~) | GitHub Actions로 이전: Actions에서 읽히는 출처로, 직접 매기는 TOP 5, 실행마다 멘션 처리 |

## v1 — requests 수집

- 핫딜 모음 사이트의 카테고리 랭킹을 requests + BeautifulSoup으로 파싱
- 게임·IT·식품 TOP 10을 Discord 고정 thread에 게시
- GitHub Actions(cron-job.org 트리거)로 운영하다 로컬 launchd로 이전
- **종료 사유:** 그 사이트가 자동화 요청을 Turnstile 챌린지로 막음
  - GitHub Actions: 2026-07-22부터 403 (데이터센터 IP)
  - 로컬 Mac: 2026-10-09부터 403
  - 실패해도 exit 0이라 3주 가까이 모르고 지나감

## v2 — Chrome + AppleScript

- 평소 쓰는 Chrome 프로필에 탭을 열고 AppleScript로 HTML을 읽음 (CDP 미사용)
- 파싱·중복 제거·게시는 v1 그대로
- 실패한 카테고리만 1시간 뒤 1회 재시도, 그래도 실패하면 exit 1 + Healthchecks.io 핑(선택)
- GitHub Actions 워크플로 제거 (데이터센터 IP는 계속 차단)
- 자세한 내용: [how-it-works.md](how-it-works.md), [flow.html](flow.html)

## v3 — 관심사 알림과 자연어 봇

자세한 설계: [v3-design.md](v3-design.md), 동작: [how-it-works.md](how-it-works.md)

- **매일 TOP 10:** 모음 사이트 카테고리 3개 → 다른 모음 사이트 인기 1개 (카테고리 랭킹은 요청 시)
- **관심사 알림:** 상품명·가격 또는 설명("괜찮은 게이밍 모니터")으로 등록, 매시 30분 새 딜을 훑어 맞으면 알림. 대신 등록, 한 번만, 가격 인하 재알림
- **`@멘션` 봇:** Gemini가 말을 해석해 등록·해제·목록·검색·랭킹 보기
- **조용한 스레드 + DM:** 스레드 글은 모두 `@silent`, 받을 사람에게만 DM
- **알림 키워드:** 핫딜 스레드 고정 메시지에 전체 알림 목록, 변경 시 자동 수정
- **남은 것:** 인기 목록 특성 조사(스냅샷 수집 중), imposter-finder에 같은 자연어 구조 적용

**종료 사유:** 맥이 배터리로 꺼지거나 잠들면 12시 글·알림·봇이 끊김 (2026-10-11 12시 글 누락). 범인찾기도 같은 이유로 Actions로 옮김.

## v4 — GitHub Actions (현재)

동작: [how-it-works.md](how-it-works.md)

- **출처 교체:** 예전 모음 사이트 2곳은 Actions에서 막혀서(Cloudflare/Turnstile) Actions에서 읽히는 모음 사이트 API 1곳 + 커뮤니티 게시판 2곳 직접. 직접 막히는 큰 커뮤니티는 모음 사이트를 통해
- **순위를 직접:** 커뮤니티별 댓글(추천) 백분위 + 댓글 수 + 여러 곳 보너스, 같은 딜·같은 행사 묶기
- **글:** 인기 TOP 5 하루 2번(12·21시), 게임·IT·식품 TOP 5 하루 1번(12시). 딜마다 썸네일, 맨 아래 더 보기 버튼. 이미 올린 딜은 2일간 다시 안 올림
- **@멘션:** 상주 봇 대신 15분마다 새 멘션을 읽어 Gemini로 처리. "오늘 ○○ 핫딜" 순위 보기는 정해진 글로 대신해 뺌
- **상태:** SQLite를 Actions 캐시로 넘김, 알림 목록은 `SEED_JSON`으로 복원 가능
- 맥 launchd 작업(매일 글·알림·상주 봇·스냅숏)은 끄고 `~/Library/LaunchAgents/disabled-buy-or-not/`에 보관
