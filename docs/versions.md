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

### 관심 키워드 알림
사람과 관심 상품(키워드)을 매핑해 두고, 해당 상품이 랭킹에 들어오면 그 사람을 태그해 알립니다.

```yaml
# watchlist.yaml (Discord ID가 들어가므로 커밋하지 않음)
- discord_id: "1234567890"
  keywords: ["에어팟 프로", "airpods pro"]
  max_price: 250000        # 선택
```

```
@친구  🔔 에어팟 프로 2 — 239,000원 (쿠팡 · 퀘이사존)
```

- 같은 딜을 두 번 알리지 않도록 알린 딜을 기록해야 합니다 (SQLite).
- 하루 한 번이면 놓치는 딜이 많아서, 30분~1시간 간격으로 확인하는 편이 맞습니다.

### 소스·카테고리 재검토
- 네이버페이 할인 같은 딜은 게임·IT·식품 3개 카테고리에 안 나옵니다.
- **hotdeal.zip 인기 게시판**이 커뮤니티 전체 인기 딜을 모아 보여줘서 더 나을 수 있습니다. Cloudflare 챌린지가 있지만 v2와 같은 Chrome 방식으로 읽을 수 있는지 확인해야 합니다.
- 카테고리별 TOP 10을 유지할지, 통합 인기 TOP N으로 갈지 결정이 필요합니다.

### 실행 방식
- 매일 TOP 10만 있으면 지금처럼 launchd가 하루 한 번 실행하는 게 가장 단순합니다.
- 키워드 알림만 추가하면 launchd `StartInterval`(예: 30분)로 충분합니다.
- Discord 명령(`/watch add 에어팟`)으로 키워드를 등록하려면 봇이 항상 켜져 있어야 해서, imposter-finder처럼 상주 서버(`KeepAlive`)로 바꿉니다.

### 그 밖의 후보
- 살래/말래 버튼으로 반응 기록
- 이벤트·상품권 카테고리 (categoryId=5)
