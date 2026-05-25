# 살래말래

algumon.com 랭킹 기반 Discord 핫딜 봇. 매일 12:00 KST에 게임/IT/식품 카테고리 TOP 10을 Discord 포럼 채널에 자동 게시합니다.

Components V2 레이아웃: 좌측 정보 + 우측 썸네일, 카테고리별 컬러 바.

## 구조

```
app/
  collector.py   # algumon 랭킹 페이지 스크래핑
  notifier.py    # Discord Bot API 전송 (Components V2)
  __main__.py    # 진입점
assets/
  placeholder.png             # 이미지 없는 딜용 투명 썸네일
.github/workflows/
  daily.yml      # PROD 자동 실행 (매일 12:00 KST)
  dev.yml        # DEV 수동 실행
```

## 환경 설정

```bash
cp .env.example .env
# .env 에서 토큰/채널 ID 채우기
```

| 변수 | 설명 |
|---|---|
| `BOT_ENV` | `dev` (로컬) / `prod` (GitHub Actions) |
| `DISCORD_BOT_TOKEN` | Discord Developer Portal에서 발급한 봇 토큰 |
| `DISCORD_CHANNEL_DEV` | DEV 포럼 채널 ID |
| `DISCORD_CHANNEL_PROD` | PROD 포럼 채널 ID |

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

## GitHub Actions

| 워크플로우 | 트리거 | 채널 |
|---|---|---|
| `daily.yml` | 매일 12:00 KST + 수동 | PROD |
| `dev.yml` | 수동 | DEV |

수동 실행: Actions 탭 → 워크플로우 선택 → **Run workflow**

**Repository Secrets:**

```bash
gh secret set DISCORD_BOT_TOKEN    --body "..." --repo inticoy/buy-or-not
gh secret set DISCORD_CHANNEL_DEV  --body "..." --repo inticoy/buy-or-not
gh secret set DISCORD_CHANNEL_PROD --body "..." --repo inticoy/buy-or-not
```

## 카테고리

| 카테고리 | algumon categoryId | 컬러 |
|---|---|---|
| 게임 🎮 | 6 | 블루퍼플 |
| IT 💻 | 2 | 하늘 |
| 식품 🍜 | 3 | 노랑 |
