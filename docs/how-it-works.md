# 동작 방식

현재 버전 기준입니다. 흐름도는 [flow.html](flow.html)에 있어요.

## 흐름

```
launchd (매일 12:00 KST)
  └─ python -m app run-once
       ├─ browser.py     Chrome 탭을 열어 HTML 읽기 (AppleScript)
       ├─ hotdealzip.py  hotdeal.zip 인기·최신 파싱
       ├─ collector.py   알구몬 랭킹 파싱, 크로스포스트 중복 제거
       └─ notifier.py    Discord 고정 thread에 댓글로 게시 (Components V2)
```

게시판마다 메시지 하나를 올립니다. 실패한 게시판은 **1시간 뒤 한 번 더** 시도하고, 그래도 실패하면 exit 1로 끝납니다.

## 게시판

| `--source` | 게시판 | 컬러 |
|---|---|---|
| `hotdeal` (기본) | 🔥 hotdeal.zip 오늘 인기, 중복 제거 후 TOP 10 | 빨강 |
| `algumon` | 🎮 게임(6) · 💻 IT(2) · 🍜 식품(3) 랭킹 | 블루퍼플 · 하늘 · 노랑 |

`app/__main__.py`의 `BOARDS`에서 바꿉니다.

## 관심사 알림

매시 30분에 `python -m app watch`가 hotdeal.zip 최신 75개를 읽어, 처음 보는 딜을 관심사와 대조합니다.

- **키워드가 있는 관심사:** 키워드의 단어가 제목에 모두 있으면 매칭 (`matcher.py`)
- **설명형 관심사:** 새 딜 목록과 함께 Gemini에 한 번 물어 판단 (`nl.py`, 기본 `gemini-3.5-flash-lite`). 실패하면 키워드 매칭만 돕니다.
- 여러 커뮤니티의 같은 딜은 묶어서 1번만, 이미 알린 딜은 가격이 내려가면 다시 알립니다.
- 알림은 핫딜 고정 thread에 대상자만 태그해서 보냅니다.
- 데이터는 `data/sallae.db`(SQLite, 커밋 안 함). 첫 실행은 지난 딜을 기록만 합니다.

## @멘션 봇

`python -m app serve`(launchd `com.inticoy.buy-or-not.serve`, 상주)가 봇을 멘션한 메시지를 받아 Gemini로 동작을 고릅니다 (`bot.py`, `nl.parse_command`).

| 말하면 | 동작 |
|---|---|
| 메가커피 핫딜 뜨면 알려줘 | 키워드 알림 등록 + "알림 설정 완료" 답장 |
| 게이밍 모니터 50만원 이하 뜨면 @진호 한테 한 번만 알려줘 | 진호에게 AI 판단 알림 등록, 진호 태그로 안내 |
| 지금 뭐 알림 받게 되어있어? / 다들 뭐 걸어놨어? | 내 목록 / 전체 목록 (태그 없이 이름으로 표시) |
| 메가커피 알림 꺼줘 | 해제 |
| 메가커피 올라왔어? / 게이밍 모니터 핫딜 있었어? | 최근 3일 딜 기록에서 검색 (제목에 없으면 Gemini가 판단). 사이트 요청 없음 |
| 오늘 게임 핫딜 뭐 있어? | 알구몬 게임 랭킹 카드 (카테고리 없으면 hotdeal.zip 인기) |

- 멘션된 메시지만 읽어서 Message Content 특수 권한이 필요 없습니다.
- 같은 딜에 여러 사람의 관심사가 걸리면 메시지 하나로 모두 태그합니다.
- **알림은 조용히, 받을 사람에게만 DM.** 봇이 스레드에 올리는 글은 모두 `@silent`(푸시 없음)입니다. 관심사 알림과 '대신 걸어준 알림' 안내는 대상자에게 DM으로 따로 보냅니다(스레드 글 링크 포함). 서버 멤버 DM을 막은 사람은 DM이 실패하고 `logs/`에 경고가 남습니다.
- 핫딜 thread의 고정 메시지 **🔔 알림 키워드**에 전체 알림 목록이 있습니다. 등록·해제·'한 번만' 자동 해제 때 봇이 같은 메시지를 수정합니다(알림 없음, 메시지 ID는 `data/board.json`). 지워지면 새로 올리고, 고정은 봇에게 권한이 없으면 직접 합니다. `python -m app board`로 수동 갱신.
- Gemini 한도를 넘으면 "오늘 AI 한도를 다 썼어요"라고 답합니다.

## 알구몬 접근

hotdeal.zip은 Cloudflare, 알구몬은 자체 Turnstile 챌린지를 씁니다. 알구몬은 의심스러운 요청에 Cloudflare Turnstile 챌린지(403 `CHALLENGE_REQUIRED`)를 겁니다. 챌린지는 항상 켜져 있지 않고, 같은 IP에서 자동화 요청이 몰리면 한동안 켜졌다가 풀립니다.

| 요청 | 평소 | IP가 의심받을 때 |
|---|---|---|
| requests / curl | 통과 | 403 |
| Playwright | 체크박스 → 클릭해도 실패 | 실패 |
| 일반 Chrome (AppleScript) | 통과 | 체크박스가 뜰 수 있음 |

그래서 CDP 없이 AppleScript로 평소 Chrome을 조종합니다.

- 페이지마다 탭이 3~5초 열렸다 닫힙니다.
- 챌린지 페이지에 걸리면 45초 후 탭을 열어둔 채 실패합니다. 1시간 뒤 재시도 전에 그 탭을 직접 체크해 두면 재시도가 성공합니다.
- hotdeal.zip 최신 목록은 '더보기' 버튼을 클릭해 3페이지(75개, 저녁 기준 약 3시간 분량)까지 읽습니다. AppleScript JS는 페이지의 함수에 접근할 수 없어 버튼을 클릭합니다.
- 개발할 때는 `tests/fixtures/`의 저장된 HTML을 쓰고, 사이트에 반복 요청하지 마세요.

## 운영

```bash
launchctl print gui/$(id -u)/com.inticoy.buy-or-not   # 상태
tail -f logs/buy-or-not.log logs/buy-or-not-error.log  # 로그
launchctl kickstart gui/$(id -u)/com.inticoy.buy-or-not  # 즉시 실행 (PROD 게시됨)
```

관심사 알림은 `com.inticoy.buy-or-not.watch`(매시 30분, 로그 `logs/watch.log`)가 돌립니다.

v3 소스 조사용으로 `com.inticoy.buy-or-not.snapshot`이 하루 4번(09·15·21·23:50) hotdeal.zip 인기 HTML과 최신 목록을 `data/snapshots/`에 저장합니다. 조사가 끝나면 지웁니다.

- 12:00에 Mac이 꺼져 있거나 로그아웃 상태면 실행되지 않습니다. 잠자기 중이었다면 깨어날 때 한 번 실행됩니다.
- `com.inticoy.keep-awake`(`caffeinate -i -s`)가 유휴 잠자기를 막습니다. 덮개를 닫으면 잠드는 건 `sudo pmset -a disablesleep 1`로만 막을 수 있습니다.
- `HEALTHCHECK_BUY_OR_NOT_URL`을 넣으면 매일 TOP 10 성공·실패를 Healthchecks.io로 보고합니다.
- `HEALTHCHECK_SERVE_URL`을 넣으면 상주 봇이 5분마다 신호를 보냅니다. 맥이 잠들거나 꺼져 30분(period 20분 + grace 10분) 동안 신호가 없으면 Healthchecks가 Down, 돌아오면 Up을 알립니다. 관심사 수집 실패는 이 check로 잡지 않고 `logs/watch.log`에만 남습니다.
