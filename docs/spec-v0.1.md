# 살래말래 v0.1 명세

## 한 줄 요약

30분마다 algumon.com을 긁어서, **watchlist 매칭** 또는 **눈길 끄는 딜**이면 Discord에 알린다.

---

## 알림 트리거 (딱 두 가지)

| 트리거 | 채널 | 조건 |
|--------|------|------|
| Watchlist 매칭 | #살래말래 | watchlist 키워드 포함 + 목표가 이하 |
| 눈길 끄는 딜 | #살래말래 | 추천수 or 댓글수 임계값 초과 |
| 위 둘 다 아님 | 저장만 | SQLite에 기록, 알림 없음 |

> "눈길 끄는 딜" 기준은 algumon이 제공하는 추천수 / "N명 보는중" 수치를 사용.
> 초기값: 추천 10 이상 OR 보는중 30 이상 (실제 데이터 보고 조정)

---

## 아키텍처

```
[cron 30분]
    │
    ▼
collector.py          algumon.com SSR HTML 수집 (BeautifulSoup)
    │
    ▼
dedup.py              URL 기준 중복 확인 (SQLite deals 테이블)
    │ 새 딜만
    ▼
matcher.py            트리거 판단
    ├─ watchlist.yaml 키워드 매칭
    └─ 추천/댓글수 임계값 확인
    │
    ├─ 해당 없음 → SQLite 저장만
    └─ 해당 있음 → notifier.py → Discord Webhook
```

---

## SQLite 스키마

### `deals`

```sql
CREATE TABLE deals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT UNIQUE NOT NULL,
    title       TEXT,
    price       INTEGER,        -- 원 단위, 파싱 실패 시 NULL
    community   TEXT,           -- 출처 커뮤니티 (루리웹, 퀘이사존 등)
    recommend   INTEGER,        -- 추천수
    viewers     INTEGER,        -- "N명 보는중"
    fetched_at  TEXT,           -- ISO8601
    notified_at TEXT            -- NULL이면 알림 안 보낸 것
);
```

### `watchlist_matches`

```sql
CREATE TABLE watchlist_matches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id     INTEGER REFERENCES deals(id),
    item_name   TEXT,           -- watchlist 항목 이름
    notified_at TEXT
);
```

테이블 두 개가 전부. 나중에 필요하면 추가.

---

## watchlist.yaml

```yaml
items:
  - name: "MX Master 3S"
    keywords:
      - "mx master 3s"
      - "마스터 3s"
    target_price: 85000        # 이하일 때만 알림

  - name: "NVMe SSD 2TB"
    keywords:
      - "ssd 2tb"
      - "nvme 2tb"
      - "990 pro 2tb"
    target_price: 160000

  - name: "에어팟"
    keywords:
      - "에어팟 프로"
      - "airpods pro"
    target_price: 200000
```

- `target_price` 없으면 가격 무관하게 키워드 매칭만으로 알림
- 키워드는 소문자 변환 후 `in` 체크 (정규식 없음)

---

## Discord 메시지 포맷

### Watchlist 매칭

```
[살래말래] MX Master 3S 매칭

제목: 로지텍 MX Master 3S 무선 마우스
가격: 83,000원 (목표가 85,000원 이하)
출처: 퀘이사존
링크: https://...
```

### 눈길 끄는 딜

```
[살래말래] 추천 42 / 87명 보는중

제목: 삼성 T7 포터블 SSD 2TB
가격: 89,000원
출처: 쿠팡 (via 알구몬)
링크: https://...
```

DEV 채널은 v0.1에서 사용하지 않음. 에러는 stderr / 로컬 로그 파일로.

---

## 디렉토리 구조

```
buy-or-not/
├── docker-compose.yml
├── Dockerfile
├── config/
│   └── watchlist.yaml
├── app/
│   ├── __main__.py         # python -m app run-once
│   ├── collector.py        # algumon.com 수집
│   ├── dedup.py            # URL 중복 확인
│   ├── matcher.py          # 트리거 판단
│   ├── notifier.py         # Discord Webhook 전송
│   └── db.py               # SQLite 연결/쿼리
├── data/
│   └── deals.db            # volume mount
└── docs/
    └── spec-v0.1.md
```

---

## 실행 방법

```bash
# 자동: docker-compose가 30분마다 실행
docker compose up -d

# 수동
docker compose exec bot python -m app run-once

# 디버그 (알림 전송 없이 출력만)
docker compose exec bot python -m app run-once --dry-run
```

---

## 환경 변수 (.env)

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
RECOMMEND_THRESHOLD=10
VIEWERS_THRESHOLD=30
```

---

## v0.1에서 하지 않는 것

- Deal 그룹핑 (같은 상품 묶기)
- 점수화 (90점/75점 티어)
- AI API 호출
- #살래말래-DEV 채널
- Discord Bot / Slash command
- 하루 digest
- algumon.com 외 다른 소스 (hotdeal.zip은 JS SPA라 별도 처리 필요, arca.live는 403 차단)

---

## 구현 순서

1. `collector.py` — algumon.com HTML 파싱 (requests + BeautifulSoup), 딜 목록 반환
2. `db.py` + `dedup.py` — SQLite 초기화, URL 중복 확인
3. `matcher.py` — watchlist 키워드 매칭, 임계값 확인
4. `notifier.py` — Discord Webhook POST
5. `__main__.py` — 위 4개를 연결, `--dry-run` 플래그
6. `docker-compose.yml` + cron 설정
