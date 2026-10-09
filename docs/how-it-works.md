# 동작 방식

현재 버전(v2) 기준입니다. 흐름도는 [flow.html](flow.html)에 있어요.

## 흐름

```
launchd (매일 12:00 KST)
  └─ python -m app run-once
       ├─ browser.py    Chrome 탭을 열어 랭킹 페이지 HTML 읽기 (AppleScript)
       ├─ collector.py  Svelte hydration 데이터 파싱 → 중복 제거 → TOP 10
       └─ notifier.py   Discord 고정 thread에 댓글로 게시 (Components V2)
```

카테고리 3개를 차례로 처리합니다. 실패한 카테고리는 **1시간 뒤 한 번 더** 시도하고, 그래도 실패하면 exit 1로 끝납니다.

## 카테고리

| 카테고리 | algumon categoryId | 컬러 |
|---|---|---|
| 게임 🎮 | 6 | 블루퍼플 |
| IT 💻 | 2 | 하늘 |
| 식품 🍜 | 3 | 노랑 |

`app/__main__.py`의 `CATEGORIES`에서 바꿉니다.

## 알구몬 접근

알구몬은 의심스러운 요청에 Cloudflare Turnstile 챌린지(403 `CHALLENGE_REQUIRED`)를 겁니다. 챌린지는 항상 켜져 있지 않고, 같은 IP에서 자동화 요청이 몰리면 한동안 켜졌다가 풀립니다.

| 요청 | 평소 | IP가 의심받을 때 |
|---|---|---|
| requests / curl | 통과 | 403 |
| Playwright | 체크박스 → 클릭해도 실패 | 실패 |
| 일반 Chrome (AppleScript) | 통과 | 체크박스가 뜰 수 있음 |

그래서 CDP 없이 AppleScript로 평소 Chrome을 조종합니다.

- 페이지마다 탭이 3~5초 열렸다 닫힙니다.
- 챌린지 페이지에 걸리면 45초 후 탭을 열어둔 채 실패합니다. 1시간 뒤 재시도 전에 그 탭을 직접 체크해 두면 재시도가 성공합니다.
- 개발할 때는 `tests/fixtures/`의 저장된 HTML을 쓰고, 알구몬에 반복 요청하지 마세요.

## 운영

```bash
launchctl print gui/$(id -u)/com.inticoy.buy-or-not   # 상태
tail -f logs/buy-or-not.log logs/buy-or-not-error.log  # 로그
launchctl kickstart gui/$(id -u)/com.inticoy.buy-or-not  # 즉시 실행 (PROD 게시됨)
```

- 12:00에 Mac이 꺼져 있거나 로그아웃 상태면 실행되지 않습니다. 잠자기 중이었다면 깨어날 때 한 번 실행됩니다.
- `HEALTHCHECK_BUY_OR_NOT_URL`을 넣으면 성공·실패를 Healthchecks.io로 보고합니다.
