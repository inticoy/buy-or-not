# 살래말래

algumon.com 랭킹 기반 Discord 핫딜 봇. 매일 09:00 KST에 게임/IT/식품 카테고리 TOP 10을 Discord 포럼 채널에 자동 게시합니다.

## 구조

```
app/
  collector.py   # algumon 랭킹 페이지 스크래핑
  notifier.py    # Discord 웹후크 전송
  __main__.py    # 진입점
.github/workflows/daily.yml  # PROD 자동 실행 (매일 09:00 KST)
.github/workflows/dev.yml    # DEV 수동 실행
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
```

`.env`는 자동으로 읽어요 — `source` 불필요.

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
python -m app run-once --style cards   # 기본: 딜마다 좌측 정보 + 우측 썸네일
python -m app run-once --style thumb1  # 1위 썸네일 + 전체 리스트
python -m app run-once --style thumb3  # 1~3위 이미지 + 나머지 리스트
python -m app run-once --style text    # embed 없이 텍스트만
```

## GitHub Actions

| 워크플로우 | 트리거 | 채널 |
|---|---|---|
| `daily.yml` | 매일 09:00 KST + 수동 | PROD |
| `dev.yml` | 수동만 (스타일 선택 가능) | DEV |

수동 실행: Actions 탭 → 워크플로우 선택 → **Run workflow**

**Repository Secrets:**

```bash
gh secret set DISCORD_WEBHOOK_PROD --body "https://discord.com/api/webhooks/..." --repo inticoy/buy-or-not
gh secret set DISCORD_WEBHOOK_DEV  --body "https://discord.com/api/webhooks/..." --repo inticoy/buy-or-not
```

## 카테고리

| 카테고리 | algumon categoryId |
|---|---|
| 게임 🎮 | 6 |
| IT 💻 | 2 |
| 식품 🍜 | 3 |
