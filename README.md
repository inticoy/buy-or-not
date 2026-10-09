# 살래말래

hotdeal.zip 인기 핫딜 TOP 10을 매일 12:00 KST에 Discord로 보내고, 친구들이 등록한 관심사에 맞는 딜이 올라오면 DM으로 알려주는 봇입니다. `@살래말래`로 말을 걸면 알림 등록·검색·랭킹 보기를 해줍니다.

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
| `GEMINI_API_KEY` | Google AI Studio에서 발급한 Gemini API 키 (말 해석·설명형 판단) |
| `HEALTHCHECK_BUY_OR_NOT_URL` | 선택: Healthchecks.io 핑 URL |

**Chrome 설정:** 보기 → 개발자 정보 → **Apple 이벤트의 자바스크립트 허용**을 켭니다. 사용할 프로필 창에서 켜야 합니다.

**친구 목록:** "진호한테 알려줘"처럼 이름으로 부르려면 `data/people.json`에 이름·별명·Discord ID를 넣습니다(커밋 안 함).

```json
{"people": [{"name": "최진호", "aliases": ["진호"], "discord_id": "4966..."}]}
```

## 디스코드에서 쓰기

| 말하면 | 봇이 하는 일 |
|---|---|
| `@살래말래 메가커피 뜨면 알려줘` | 알림 등록 (상품명은 키워드로) |
| `@살래말래 괜찮은 게이밍 모니터 50만원 이하 뜨면 @진호 한테 한 번만 알려줘` | 진호에게 알림 등록 (종류는 AI가 판단), 진호에게 DM으로 안내 |
| `@살래말래 메가커피 올라왔어?` | 최근 3일 딜에서 검색 |
| `@살래말래 지금 뭐 알림 받게 되어있어?` / `다들 뭐 걸어놨어?` | 내 알림 / 전체 알림 |
| `@살래말래 메가커피 알림 꺼줘` | 알림 해제 |
| `@살래말래 오늘 게임 핫딜 뭐 있어?` | 알구몬 카테고리 랭킹 (없으면 hotdeal.zip 인기) |

- 봇이 스레드에 올리는 글은 모두 조용히(`@silent`) 가고, 알림 받을 사람에게만 DM이 갑니다.
- 핫딜 스레드의 고정 메시지 **🔔 알림 키워드**에 전체 알림 목록이 있고, 봇이 바뀔 때마다 고칩니다. 봇에게 고정 권한이 없으면 처음 한 번만 직접 고정합니다.

## 실행

```bash
.venv/bin/python -m app run-once --dry-run   # 전송 없이 출력만
.venv/bin/python -m app run-once             # BOT_ENV 채널로 전송 (hotdeal.zip 인기 TOP 10)
.venv/bin/python -m app run-once --source algumon   # 알구몬 게임·IT·식품 랭킹
.venv/bin/python -m unittest discover -s tests
```

관심사 알림을 명령어로 다룰 때:

```bash
.venv/bin/python -m app watch-add --owner <Discord ID> --want "메가커피" --keywords 메가커피
.venv/bin/python -m app watch-add --owner <Discord ID> --want "게이밍 모니터"   # 키워드 없으면 Gemini가 판단
.venv/bin/python -m app watch-list
.venv/bin/python -m app watch --dry-run   # 최신 딜을 훑어 알림 대상만 출력
.venv/bin/python -m app board             # 고정된 '알림 키워드' 메시지 갱신
```

## 자동 실행 (launchd)

```bash
for job in buy-or-not buy-or-not.watch buy-or-not.serve; do
  cp ops/launchd/com.inticoy.$job.plist ~/Library/LaunchAgents/
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.inticoy.$job.plist
done
```

매일 12:00에 TOP 10을, 매시 30분에 관심사 알림을 PROD로 보냅니다. `serve`는 `@멘션`에 답하는 상주 봇입니다. 처음 실행할 때 뜨는 "Chrome 제어" 권한 팝업을 허용해야 합니다.
