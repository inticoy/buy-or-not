# 살래말래

친구들 디스코드 핫딜 스레드에 **인기 핫딜 TOP 5**(12시·21시)와 **게임·IT·식품 TOP 5**(12시)를 올리고, 친구들이 걸어둔 관심사에 맞는 딜이 올라오면 그 사람에게 알려주는 봇입니다. `@살래말래`로 말을 걸면 알림 등록·해제·목록·검색을 해줍니다.

GitHub Actions에서 15분마다 돌아갑니다(cron-job.org가 실행). 맥이 꺼져 있어도 됩니다. 동작 방식과 버전 기록은 [docs/](docs/)에 있습니다.

## 디스코드에서 쓰기

| 말하면 | 봇이 하는 일 |
|---|---|
| `@살래말래 메가커피 뜨면 알려줘` | 알림 등록 (상품명은 키워드로) |
| `@살래말래 괜찮은 게이밍 모니터 50만원 이하 뜨면 @진호 한테 한 번만 알려줘` | 진호에게 알림 등록 (종류는 AI가 판단), 진호에게 DM으로 안내 |
| `@살래말래 메가커피 올라왔어?` | 최근 3일 딜에서 검색 |
| `@살래말래 지금 뭐 알림 받게 되어있어?` / `다들 뭐 걸어놨어?` | 내 알림 / 전체 알림 |
| `@살래말래 메가커피 알림 꺼줘` | 알림 해제 |

- 15분마다 확인해서 답이 최대 15분 늦을 수 있습니다.
- 봇이 스레드에 올리는 글은 모두 조용히(`@silent`) 가고, 알림 받을 사람에게만 DM이 갑니다.
- 핫딜 스레드의 고정 메시지 **🔔 알림 키워드**에 전체 알림 목록이 있고, 바뀔 때마다 봇이 고칩니다.

## 설정 (GitHub Actions)

워크플로: [`.github/workflows/daily.yml`](.github/workflows/daily.yml). 이름은 예전 cron-job.org 설정을 그대로 쓰려고 `daily.yml`입니다.

| 비밀값 | 내용 |
|---|---|
| `ENV_FILE` | `.env.example` 형식의 `.env` 내용 (봇 토큰, 채널·thread ID, Gemini 키) |
| `PEOPLE_JSON` | 친구 이름·별명·Discord ID, **한 줄 JSON** (여러 줄이면 로그의 `]`까지 가려짐) |
| `SEED_JSON` | 상태 캐시가 사라졌을 때 되살릴 알림 목록 (`python -m app export-seed`) |

**cron-job.org:** 15분마다 `POST https://api.github.com/repos/inticoy/buy-or-not/actions/workflows/daily.yml/dispatches`, 본문 `{"ref":"main"}`, 헤더 `Authorization: Bearer <Actions 쓰기 권한 토큰>`.

상태(딜·알림·올린 글 기록, `data/sallae.db`)는 Actions 캐시에 실행마다 저장하고 다음 실행에서 복원합니다. 캐시가 사라지면 `SEED_JSON`으로 알림 목록을 되살리고, 첫 실행은 기록만 해서 중복 글·알림이 나가지 않습니다.

## 로컬에서 실행

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env              # 토큰·채널 ID 채우기 (BOT_ENV=dev)
.venv/bin/python -m app cycle --dry-run   # 모으기·알림·멘션·글을 전송 없이 출력
.venv/bin/python -m app post hot          # 지금 인기 글을 DEV thread에 올려보기
.venv/bin/python -m unittest discover -s tests
```

**친구 목록:** "진호한테 알려줘"처럼 이름으로 부르려면 `data/people.json`에 넣습니다(커밋 안 함).

```json
{"people": [{"name": "최진호", "aliases": ["진호"], "discord_id": "4966..."}]}
```

관심사를 명령어로 다룰 때: `python -m app watch-add --owner <ID> --want "메가커피" --keywords 메가커피`, `watch-list`, `board`(고정 메시지 갱신).
