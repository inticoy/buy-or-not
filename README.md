# 살래말래

algumon.com 랭킹 기반 Discord 핫딜 봇. 매일 09:00 KST에 게임/IT/식품 카테고리 TOP 10을 Discord 포럼 채널에 자동 게시합니다.

## 구조

```
app/
  collector.py   # algumon 랭킹 페이지 스크래핑
  db.py          # SQLite 중복 게시 방지
  notifier.py    # Discord 웹후크 전송
  __main__.py    # 진입점
.github/workflows/daily.yml  # GitHub Actions 스케줄러
```

## 환경 설정

```bash
cp .env.example .env
# .env 에서 웹후크 URL 채우기
```

| 변수 | 설명 |
|---|---|
| `BOT_ENV` | `dev` (로컬) / `prod` (GitHub Actions) |
| `DISCORD_WEBHOOK_DEV` | 테스트용 Discord 포럼 채널 웹후크 |
| `DISCORD_WEBHOOK_PROD` | 실제 서비스 Discord 포럼 채널 웹후크 |

## 로컬 실행

```bash
pip install -r requirements.txt
source .env
```

**실제 전송 없이 출력만 확인 (dry-run):**
```bash
python -m app run-once --dry-run
```

**DEV 채널에 실제 전송:**
```bash
python -m app run-once
```

**스타일 지정:**
```bash
python -m app run-once --style thumb1   # 기본: 1위 썸네일
python -m app run-once --style thumb3   # 1~3위 이미지
python -m app run-once --style text     # embed 없이 텍스트만
```

**오늘 게시 기록 초기화 (재실행 시):**
```bash
rm -f data/deals.db
```

## GitHub Actions

- 스케줄: 매일 00:00 UTC (= 09:00 KST)
- 수동 실행: Actions 탭 → `살래말래 일일 핫딜` → **Run workflow**

**필요한 Repository Secret:**

| Secret | 값 |
|---|---|
| `DISCORD_WEBHOOK_PROD` | PROD 채널 웹후크 URL |

```bash
# Secret 등록 방법
gh secret set DISCORD_WEBHOOK_PROD --body "https://discord.com/api/webhooks/..." --repo inticoy/buy-or-not
```

## 카테고리

| 카테고리 | algumon categoryId |
|---|---|
| 게임 🎮 | 6 |
| IT 💻 | 2 |
| 식품 🍜 | 3 |
