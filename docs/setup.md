# 설정

## GitHub Actions (운영)

워크플로는 [`.github/workflows/daily.yml`](../.github/workflows/daily.yml)입니다. 이름이 `daily.yml`인 건 예전 cron-job.org 설정을 그대로 쓰려고서예요. 실제로는 15분마다 돕니다.

| 비밀값 | 내용 |
|---|---|
| `ENV_FILE` | [`.env.example`](../.env.example) 형식의 `.env` 내용 (봇 토큰, 채널·thread ID, Gemini 키). `BOT_ENV`는 워크플로가 `prod`로 정함 |
| `PEOPLE_JSON` | 친구 이름·별명·Discord ID, **한 줄 JSON** (여러 줄이면 로그의 `]`까지 `***`로 가려짐) |
| `SEED_JSON` | 상태 캐시가 사라졌을 때 되살릴 알림 목록. `python -m app export-seed` 출력 |

```bash
gh secret set ENV_FILE < .env
python3 -c "import json;print(json.dumps(json.load(open('data/people.json')),ensure_ascii=False,separators=(',',':')))" | gh secret set PEOPLE_JSON
.venv/bin/python -m app export-seed | gh secret set SEED_JSON
gh workflow run daily.yml --ref main   # 한 번 직접 실행
```

**cron-job.org:** 15분마다

- URL: `POST https://api.github.com/repos/inticoy/buy-or-not/actions/workflows/daily.yml/dispatches`
- 헤더: `Authorization: Bearer <이 레포 Actions 쓰기 권한 토큰>`, `Accept: application/vnd.github+json`
- 본문: `{"ref":"main"}` → 성공하면 204

**상태:** `data/sallae.db`(딜·알림·올린 글 기록)와 `data/board.json`을 Actions 캐시에 실행마다 저장하고 다음 실행에서 복원합니다. 캐시가 사라지면 `SEED_JSON`으로 알림 목록을 되살리고, 첫 실행은 기록만 해서 중복 글·알림이 나가지 않습니다.

**공개 로그:** 공개 레포라 Actions 로그는 누구나 봅니다. 로그에는 출처별 개수·딜 제목·동작 이름만 남기고, 친구 이름·Discord ID·알림 내용은 남기지 않습니다. 외부 PR 워크플로는 항상 승인 후 실행되게 해 뒀습니다.

## 로컬

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env              # 토큰·채널 ID 채우기 (BOT_ENV=dev)
.venv/bin/python -m app cycle --dry-run   # 모으기·알림·멘션·글을 전송 없이 출력
.venv/bin/python -m app post hot          # 지금 인기 글을 DEV thread에 올려보기 (hot·game·digital·food)
.venv/bin/python -m unittest discover -s tests
```

**친구 목록:** "진호한테 알려줘"처럼 이름으로 부르려면 `data/people.json`에 넣습니다 (커밋 안 함).

```json
{"people": [{"name": "최진호", "aliases": ["진호"], "discord_id": "4966..."}]}
```

**관심사를 명령어로:** `watch-add --owner <ID> --want "메가커피" --keywords 메가커피`, `watch-list`, `board`(고정 메시지 갱신).

**GitHub 공유 미리보기:** 레포 Settings → General → Social preview에 `docs/images/social-preview.png`(1280×640)를 올립니다 (API로는 못 올림).

**README 카드 그림:** `.venv/bin/pip install pillow && .venv/bin/python -m tools.readme_cards` — 지금 딜로 `docs/images/card-*.png`를 다시 만듭니다 (멘션은 가명).
