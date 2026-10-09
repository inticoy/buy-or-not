"""평소 쓰는 Chrome 프로필로 페이지 HTML을 가져온다.

알구몬은 requests/Playwright 같은 자동화 요청에 Turnstile 챌린지를 건다.
CDP 없이 AppleScript로 실제 Chrome 탭을 열고 읽으면 일반 방문으로 처리된다.

필요 설정: Chrome 보기 → 개발자 정보 → "Apple 이벤트의 자바스크립트 허용"
(프로필마다 따로 켜야 한다)
"""
import logging
import os
import subprocess
import time
import uuid

logger = logging.getLogger(__name__)

CHROME_PROFILE = os.environ.get("CHROME_PROFILE", "Default")
OSA_TIMEOUT_S = 15

_FIND_TAB = '''
on run argv
  set marker to item 1 of argv
  tell application "Google Chrome"
    repeat with w in windows
      repeat with t in tabs of w
        if URL of t contains marker then return (id of t) as text
      end repeat
    end repeat
  end tell
  return ""
end run
'''

_EXEC_JS = '''
on run argv
  set tabId to item 1 of argv
  tell application "Google Chrome"
    repeat with w in windows
      repeat with t in tabs of w
        if ((id of t) as text) is tabId then return execute t javascript (item 2 of argv)
      end repeat
    end repeat
  end tell
  error "tab not found"
end run
'''

_CLOSE_TAB = '''
on run argv
  set tabId to item 1 of argv
  tell application "Google Chrome"
    repeat with w in windows
      repeat with t in tabs of w
        if ((id of t) as text) is tabId then
          close t
          return
        end if
      end repeat
    end repeat
  end tell
end run
'''

_STATUS_JS = "location.pathname + '\\n' + document.readyState"


class BrowserFetchError(Exception):
    pass


class ChallengeRequired(BrowserFetchError):
    pass


def _osa(script: str, *args: str) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-", *args],
            input=script, capture_output=True, text=True, timeout=OSA_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as e:
        raise BrowserFetchError("osascript timed out") from e
    if result.returncode != 0:
        raise BrowserFetchError(result.stderr.strip())
    return result.stdout.rstrip("\n")


def fetch_html(url: str, timeout: float = 45) -> str:
    """Open url in Chrome, wait until it finishes loading off the challenge page, and return the HTML.

    On a challenge page the tab is left open so it can be solved by hand.
    """
    # fragment는 서버로 전송되지 않고 리다이렉트 후에도 유지돼 탭을 찾는 표식으로 쓴다
    tag = f"sallae-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        ["open", "-na", "Google Chrome", "--args",
         f"--profile-directory={CHROME_PROFILE}", f"{url}#{tag}"],
        check=True, timeout=OSA_TIMEOUT_S,
    )

    deadline = time.monotonic() + timeout
    tab_id = ""
    while not tab_id:
        if time.monotonic() > deadline:
            raise BrowserFetchError(f"Chrome tab did not open: {url}")
        time.sleep(0.5)
        tab_id = _osa(_FIND_TAB, tag)

    path = ""
    try:
        while time.monotonic() < deadline:
            time.sleep(1)
            try:
                path, state = _osa(_EXEC_JS, tab_id, _STATUS_JS).split("\n")
            except (BrowserFetchError, ValueError):
                continue  # 페이지 전환 중
            if state == "complete" and "/challenge" not in path:
                html = _osa(_EXEC_JS, tab_id, "document.documentElement.outerHTML")
                _osa(_CLOSE_TAB, tab_id)
                return html
    except BaseException:
        _osa(_CLOSE_TAB, tab_id)
        raise

    if "/challenge" in path:
        raise ChallengeRequired(f"challenge page left open in Chrome: {url}")
    _osa(_CLOSE_TAB, tab_id)
    raise BrowserFetchError(f"timed out at {path or 'unknown page'}: {url}")
