# 살래말래

hotdeal.zip 인기 핫딜 TOP 10을 매일 12:00 KST에 Discord로 보내는 봇입니다.

동작 방식과 버전별 계획은 [docs/](docs/)에 있습니다.

## 설정

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # 토큰·채널 ID 채우기
```

| 변수 | 설명 |
|---|---|
| `BOT_ENV` | `dev` / `prod` — 보낼 채널 선택 |
| `DISCORD_BOT_TOKEN` | Discord 봇 토큰 |
| `DISCORD_CHANNEL_DEV` / `_PROD` | 포럼 채널 ID |
| `DISCORD_THREAD_DEV` / `_PROD` | 선택: 고정 thread에 댓글로 보낼 때 |
| `CHROME_PROFILE` | 선택: 알구몬을 열 Chrome 프로필 (기본 `Default`) |
| `HEALTHCHECK_BUY_OR_NOT_URL` | 선택: Healthchecks.io 핑 URL |

**Chrome 설정:** 보기 → 개발자 정보 → **Apple 이벤트의 자바스크립트 허용**을 켭니다. 사용할 프로필 창에서 켜야 합니다.

## 실행

```bash
.venv/bin/python -m app run-once --dry-run   # 전송 없이 출력만
.venv/bin/python -m app run-once             # BOT_ENV 채널로 전송 (hotdeal.zip 인기 TOP 10)
.venv/bin/python -m app run-once --source algumon   # 알구몬 게임·IT·식품 랭킹
.venv/bin/python -m unittest discover -s tests
```

## 자동 실행 (launchd)

```bash
cp ops/launchd/com.inticoy.buy-or-not.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.inticoy.buy-or-not.plist
```

매일 12:00에 PROD로 게시합니다. 처음 실행할 때 뜨는 "Chrome 제어" 권한 팝업을 허용해야 합니다.
