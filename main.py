import os
import re
import csv
import time
import random
import hashlib
from dataclasses import dataclass
from datetime import datetime, date, time as dtime
from typing import Optional, Tuple, List, Dict, Iterable
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode, urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

# =========================
# 기본 설정
# =========================
KST = ZoneInfo("Asia/Seoul")

BOARD_ID = os.getenv("BOARD_ID", "krstock").strip()

# BASE_LIST_URL을 워크플로우에서 강제해도 되지만,
# 잘못 들어오면 자동으로 다른 후보를 시도해서 정상 동작하도록 함.
ENV_BASE_LIST_URL = os.getenv("BASE_LIST_URL", "").strip()

OUT_PREFIX = os.getenv("OUT_PREFIX", BOARD_ID).strip()
OUT_DIR = os.getenv("OUT_DIR", "outputs").strip()

START_TIME_STR = os.getenv("START_TIME", "08:50").strip()
END_TIME_STR = os.getenv("END_TIME", "15:40").strip()

TARGET_DATE_STR = os.getenv("TARGET_DATE", "").strip()
DATES_FILE = os.getenv("DATES_FILE", "date.txt").strip()

LIST_NUM = int(os.getenv("LIST_NUM", "100"))
MAX_PAGE_LIMIT = int(os.getenv("MAX_PAGE_LIMIT", "20000"))

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "25"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "6"))

SLEEP_LIST = float(os.getenv("SLEEP_LIST", "0.9"))
SLEEP_POST = float(os.getenv("SLEEP_POST", "0.6"))

DEBUG = os.getenv("DEBUG", "0").strip() == "1"

# requests로 막히면 playwright로 우회할지 선택
# - requests: requests만 사용(막히면 실패)
# - playwright: playwright만 사용(코스피 같은 강한 차단 대응)
# - auto: requests 시도 -> 막히면 playwright로 1회 자동 폴백
FETCH_MODE = os.getenv("FETCH_MODE", "requests").strip().lower()

# 차단 페이지를 파일로 남길지
SAVE_BLOCK_HTML = os.getenv("SAVE_BLOCK_HTML", "1").strip() == "1"
DEBUG_DIR = os.getenv("DEBUG_DIR", "debug_html").strip()

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
).strip()

# 가능하면 실제 크롬에 가깝게 헤더를 채움(차단 완화에 도움될 때가 있음)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "max-age=0",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    # sec-fetch 계열은 requests에서 의미가 없을 수도 있지만,
    # 일부 사이트/방화벽에서 단순 헤더 존재 여부만 보는 경우가 있어 포함
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

BASE_LIST_URL_CANDIDATES = [
    "https://gall.dcinside.com/mgallery/board/lists/",
    "https://gall.dcinside.com/board/lists/",
]

# =========================
# 예외 / 데이터 구조
# =========================
class BlockedBySiteError(RuntimeError):
    """요청은 성공(HTTP 200 등)했지만, 내용이 차단/보안문자 페이지일 때"""


@dataclass(frozen=True)
class PostRow:
    post_no: int
    head: str
    title: str
    url: str
    date_text: str
    date_attr: Optional[str]
    is_notice: bool


# =========================
# 유틸
# =========================
def parse_hhmm(s: str) -> dtime:
    return datetime.strptime(s, "%H:%M").time()


def jitter_sleep(base: float) -> None:
    time.sleep(base + random.uniform(0, base * 0.35))


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def clean_title(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\[\d+\]\s*$", "", s).strip()  # 댓글수 [12] 제거
    return s


def uniq_keep_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        x = (x or "").strip()
        if not x:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()


def dump_debug_html(tag: str, url: str, html: str) -> None:
    if not SAVE_BLOCK_HTML:
        return
    try:
        ensure_dir(DEBUG_DIR)
        fname = f"{tag}_{BOARD_ID}_{sha1(url)[:10]}.html"
        path = os.path.join(DEBUG_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[DEBUG] HTML 저장: {path}")
    except Exception as e:
        print(f"[DEBUG] HTML 저장 실패: {e}")


def looks_like_blocked(html: str) -> bool:
    """
    디시 차단/보안문자/비정상 접근 페이지에 자주 등장하는 문구 기반 휴리스틱.
    (환경에 따라 문구가 조금씩 다를 수 있어 넉넉히 잡음)
    """
    if not html:
        return True

    text = re.sub(r"\s+", " ", html).lower()

    keywords = [
        "보안문자",
        "자동입력 방지",
        "자동 등록 방지",
        "비정상",
        "정상적인 접근",
        "접근이 제한",
        "접근 제한",
        "잠시 후 다시",
        "차단",
        "blocked",
        "access denied",
        "captcha",
        "security check",
    ]

    hit = sum(1 for k in keywords if k in text)
    # 너무 공격적으로 잡으면 오탐이 날 수 있어 2개 이상 일 때 차단으로 판단
    return hit >= 2


# =========================
# URL 빌더
# =========================
def build_list_url(page: int, base_list_url: str) -> str:
    parts = urlsplit(base_list_url)
    qs = parse_qs(parts.query)
    qs["id"] = [BOARD_ID]
    qs["page"] = [str(page)]
    qs["list_num"] = [str(LIST_NUM)]
    new_query = urlencode(qs, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


# =========================
# Fetcher (requests / playwright)
# =========================
class Fetcher:
    def get(self, url: str, referer: Optional[str] = None) -> str:
        raise NotImplementedError

    def close(self) -> None:
        pass


class RequestsFetcher(Fetcher):
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def warmup(self) -> None:
        # 쿠키/세션을 조금이라도 자연스럽게 만들기 위해 루트 1회 방문
        # (효과 없을 수도 있지만 비용이 작아서 넣어둠)
        try:
            self.session.get("https://www.dcinside.com", timeout=REQUEST_TIMEOUT)
        except Exception:
            pass

    def get(self, url: str, referer: Optional[str] = None) -> str:
        last_err: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                headers = {}
                if referer:
                    headers["Referer"] = referer

                resp = self.session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

                if resp.status_code == 200 and resp.text:
                    html = resp.text
                    if looks_like_blocked(html):
                        dump_debug_html("blocked", url, html)
                        raise BlockedBySiteError("blocked(html)")
                    return html

                if resp.status_code in (403, 429, 500, 502, 503, 504):
                    last_err = RuntimeError(f"HTTP {resp.status_code}")
                    jitter_sleep(1.2 * attempt)
                    continue

                last_err = RuntimeError(f"HTTP {resp.status_code}")
                jitter_sleep(0.8 * attempt)

            except BlockedBySiteError as e:
                # 차단은 재시도해도 같은 경우가 많아 즉시 종료(상위에서 playwright 폴백 가능)
                raise e
            except Exception as e:
                last_err = e
                jitter_sleep(1.2 * attempt)

        raise RuntimeError(f"요청 실패: {url} / 마지막 에러: {last_err}")


class PlaywrightFetcher(Fetcher):
    """
    Playwright(Chromium)로 HTML을 가져옴.
    - 디시가 requests(User-Agent만 바꾼 봇) 접근을 막는 환경에서 유효할 때가 있음
    - 단, playwright 설치 + 브라우저 설치가 필요(워크플로우 수정 필요)
    """

    def __init__(self):
        # 지연 import (krstock처럼 playwright 불필요한 워크플로우에서 의존성 강제하지 않기)
        from playwright.sync_api import sync_playwright  # type: ignore

        self._sync_playwright = sync_playwright
        self._pw = None
        self._browser = None
        self._context = None

    def _ensure(self):
        if self._pw is not None:
            return

        self._pw = self._sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)

        # locale/timezone/user_agent는 약간이라도 브라우저처럼 보이게
        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )

        # 불필요 리소스 차단(속도/부하 개선)
        def _route_handler(route, request):
            if request.resource_type in ("image", "media", "font", "stylesheet"):
                return route.abort()
            return route.continue_()

        try:
            self._context.route("**/*", _route_handler)
        except Exception:
            pass

    def get(self, url: str, referer: Optional[str] = None) -> str:
        self._ensure()

        last_err: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            page = None
            try:
                page = self._context.new_page()
                # referer는 goto 옵션으로
                page.goto(url, wait_until="domcontentloaded", referer=referer, timeout=REQUEST_TIMEOUT * 1000)

                # table이 나타날 때까지 아주 짧게만 대기
                try:
                    page.wait_for_timeout(300)  # 0.3s
                except Exception:
                    pass

                html = page.content() or ""
                if looks_like_blocked(html):
                    dump_debug_html("blocked_pw", url, html)
                    raise BlockedBySiteError("blocked(playwright)")

                return html

            except BlockedBySiteError as e:
                raise e
            except Exception as e:
                last_err = e
                jitter_sleep(1.0 * attempt)
            finally:
                try:
                    if page is not None:
                        page.close()
                except Exception:
                    pass

        raise RuntimeError(f"요청 실패: {url} / 마지막 에러: {last_err}")

    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass


# =========================
# HTML 파싱
# =========================
def extract_open_date_from_list(html: str) -> Optional[date]:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    m = re.search(r"개설일\s*(\d{4}-\d{2}-\d{2})", text)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _pick_main_table(soup: BeautifulSoup):
    # table.gall_list가 있으면 그게 최우선
    t = soup.select_one("table.gall_list")
    if t:
        return t

    # fallback: thead에 제목/작성일/글쓴이 포함 table 찾기
    for tb in soup.find_all("table"):
        thead = tb.find("thead")
        thead_text = thead.get_text(" ", strip=True) if thead else ""
        if ("제목" in thead_text) and ("작성일" in thead_text) and ("글쓴이" in thead_text):
            return tb

    return None


def _find_date_td(tr) -> Optional[BeautifulSoup]:
    date_td = tr.select_one("td.gall_date")
    if date_td:
        return date_td

    # fallback: td들 중 날짜/시간 패턴을 찾기
    tds = tr.find_all("td")
    for td in reversed(tds):
        txt = td.get_text(" ", strip=True)

        if re.fullmatch(r"\d{1,2}:\d{2}", txt):
            return td
        if re.fullmatch(r"\d{2}\.\d{2}", txt):
            return td
        if re.fullmatch(r"\d{2}[./-]\d{2}[./-]\d{2}", txt):
            return td
        if re.fullmatch(r"\d{4}[./-]\d{2}[./-]\d{2}", txt):
            return td

        if td.has_attr("title"):
            t = str(td.get("title", "")).strip()
            if re.search(r"\d{4}[./-]\d{2}[./-]\d{2}\s+[0-2]\d:[0-5]\d", t):
                return td

        child = td.find(attrs={"title": True})
        if child:
            t = str(child.get("title", "")).strip()
            if re.search(r"\d{4}[./-]\d{2}[./-]\d{2}\s+[0-2]\d:[0-5]\d", t):
                return td

    return None


def _pick_best_view_anchor(tr) -> Optional[BeautifulSoup]:
    """
    리스트 한 줄(tr) 안에서 진짜 '게시글 보기' 링크를 최대한 정확히 고른다.
    광고/설문/갤로그 링크 등 섞여 있어도 견딜 수 있게.
    """
    anchors = tr.find_all("a", href=True)
    if not anchors:
        return None

    # 1순위: board/view 링크
    candidates = [a for a in anchors if "board/view" in a["href"]]
    if candidates:
        candidates.sort(key=lambda a: len(a.get_text(" ", strip=True)), reverse=True)
        return candidates[0]

    # 2순위: no= 파라미터가 있는 링크 (view일 가능성)
    candidates = [a for a in anchors if re.search(r"[?&]no=\d+", a["href"])]
    if candidates:
        candidates.sort(key=lambda a: len(a.get_text(" ", strip=True)), reverse=True)
        return candidates[0]

    # 3순위: 텍스트가 가장 긴 링크
    anchors.sort(key=lambda a: len(a.get_text(" ", strip=True)), reverse=True)
    return anchors[0]


def extract_rows(html: str, page_url: str) -> List[PostRow]:
    soup = BeautifulSoup(html, "lxml")
    table = _pick_main_table(soup)
    if not table:
        return []

    tbody = table.find("tbody") or table
    trs = tbody.find_all("tr")
    rows: List[PostRow] = []

    for tr in trs:
        # 글 번호
        num_td = tr.select_one("td.gall_num") or (tr.find_all("td")[0] if tr.find_all("td") else None)
        if not num_td:
            continue
        num_text = num_td.get_text(strip=True)
        if not num_text.isdigit():
            continue
        post_no = int(num_text)

        # 말머리(없을 수도)
        head_td = tr.select_one("td.gall_subject")
        head = head_td.get_text(" ", strip=True) if head_td else ""
        is_notice = head.strip() == "공지"

        # ✅ 제목/링크: tr 전체에서 view 링크를 직접 찾는다
        a = _pick_best_view_anchor(tr)
        if not a or not a.get("href"):
            continue

        title = clean_title(a.get_text(" ", strip=True))
        if not title:
            continue
        url = urljoin(page_url, a["href"])

        # 작성일
        date_td = _find_date_td(tr)
        if not date_td:
            continue
        date_text = date_td.get_text(" ", strip=True)

        date_attr = None
        if date_td.has_attr("title"):
            date_attr = str(date_td.get("title", "")).strip() or None
        else:
            span_with_title = date_td.find(attrs={"title": True})
            if span_with_title:
                date_attr = str(span_with_title.get("title", "")).strip() or None

        rows.append(
            PostRow(
                post_no=post_no,
                head=head,
                title=title,
                url=url,
                date_text=date_text,
                date_attr=date_attr,
                is_notice=is_notice,
            )
        )

    return rows


# =========================
# 날짜/시간 파싱
# =========================
def parse_full_datetime(s: str) -> Optional[datetime]:
    s = s.strip()
    m = re.fullmatch(
        r"(\d{4})[.\-/](\d{2})[.\-/](\d{2})\s+([0-2]\d):([0-5]\d)(?::([0-5]\d))?",
        s,
    )
    if not m:
        return None
    y, mo, d, hh, mm, ss = m.groups()
    sec = int(ss) if ss is not None else 0
    try:
        return datetime(int(y), int(mo), int(d), int(hh), int(mm), sec, tzinfo=KST)
    except ValueError:
        return None


def parse_list_date_or_datetime(
    date_text: str, date_attr: Optional[str], now_kst: datetime
) -> Tuple[Optional[datetime], Optional[date]]:
    if date_attr:
        dt = parse_full_datetime(date_attr)
        if dt:
            return dt, None

    s = re.sub(r"\s+", " ", date_text.strip())

    # HH:MM -> 오늘로 결합
    if re.fullmatch(r"\d{1,2}:\d{2}", s):
        h, m = map(int, s.split(":"))
        return datetime.combine(now_kst.date(), dtime(h, m), tzinfo=KST), None

    # YY.MM.DD / YY/MM/DD / YY-MM-DD
    m = re.fullmatch(r"(\d{2})[.\-/](\d{2})[.\-/](\d{2})", s)
    if m:
        yy, mo, dd = map(int, m.groups())
        return None, date(2000 + yy, mo, dd)

    # YYYY.MM.DD / YYYY/MM/DD / YYYY-MM-DD
    m = re.fullmatch(r"(\d{4})[.\-/](\d{2})[.\-/](\d{2})", s)
    if m:
        y, mo, dd = map(int, m.groups())
        try:
            return None, date(y, mo, dd)
        except ValueError:
            return None, None

    # MM.DD -> 올해 기준(미래면 전년도)
    if re.fullmatch(r"\d{2}\.\d{2}", s):
        mo, dd = map(int, s.split("."))
        y = now_kst.year
        candidate = date(y, mo, dd)
        if candidate > now_kst.date():
            candidate = date(y - 1, mo, dd)
        return None, candidate

    return None, None


def parse_datetime_from_post(html: str) -> Optional[datetime]:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    # YYYY.MM.DD HH:MM:SS (or - /)
    m = re.search(r"(\d{4}[.\-/]\d{2}[.\-/]\d{2})\s+([0-2]\d:[0-5]\d:[0-5]\d)", text)
    if m:
        dt = parse_full_datetime(f"{m.group(1)} {m.group(2)}")
        if dt:
            return dt

    # YYYY.MM.DD HH:MM
    m = re.search(r"(\d{4}[.\-/]\d{2}[.\-/]\d{2})\s+([0-2]\d:[0-5]\d)", text)
    if m:
        dt = parse_full_datetime(f"{m.group(1)} {m.group(2)}:00")
        if dt:
            return dt

    return None


# =========================
# 입출력
# =========================
def load_dates_from_file(path: str) -> List[date]:
    dates: List[date] = []
    if not os.path.exists(path):
        raise FileNotFoundError(f"날짜 파일을 찾지 못했습니다: {path}")

    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if not re.match(r"^\d{4}-\d{2}-\d{2}\b", line):
                continue
            token = line.split()[0]
            try:
                dates.append(date.fromisoformat(token))
            except ValueError:
                continue

    return sorted(set(dates))


def write_csv(out_path: str, rows: List[Tuple[datetime, str, str]]) -> None:
    rows_sorted = sorted(rows, key=lambda x: x[0])
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["작성시간(KST)", "제목", "URL"])
        for dt, title, url in rows_sorted:
            w.writerow([dt.strftime("%Y-%m-%d %H:%M:%S"), title, url])


# =========================
# 페이지 탐색(이진탐색 + break)
# =========================
def choose_base_list_url(fetcher: Fetcher) -> Tuple[str, str]:
    candidates = uniq_keep_order([ENV_BASE_LIST_URL] + BASE_LIST_URL_CANDIDATES)

    blocked_exc: Optional[Exception] = None

    for base in candidates:
        try:
            test_url = build_list_url(1, base)
            html = fetcher.get(test_url)
            rows = extract_rows(html, test_url)

            valid = [r for r in rows if f"id={BOARD_ID}" in r.url]
            if DEBUG:
                print(f"[DEBUG] base 후보: {base} -> rows={len(rows)}, valid_id_rows={len(valid)}")
                if valid:
                    s = valid[0]
                    print(f"[DEBUG] sample row: no={s.post_no}, date='{s.date_text}', title='{s.title[:40]}'")
            if valid:
                return base, html

        except BlockedBySiteError as e:
            blocked_exc = e
            if DEBUG:
                print(f"[DEBUG] base 후보 차단: {base} / {e}")
            continue
        except Exception as e:
            if DEBUG:
                print(f"[DEBUG] base 후보 실패: {base} / {e}")
            continue

    if blocked_exc is not None:
        raise BlockedBySiteError(
            "리스트 페이지가 차단(보안문자/비정상 접근)으로 보입니다. "
            "GitHub-hosted runner에서는 코스피 갤이 특히 잘 막힙니다."
        )

    raise RuntimeError(f"유효한 리스트 페이지를 찾지 못했습니다. BOARD_ID='{BOARD_ID}'")


def get_page_date_range(
    fetcher: Fetcher,
    base_list_url: str,
    page: int,
    now_kst: datetime,
    cache: Dict[int, Tuple[Optional[date], Optional[date]]],
) -> Tuple[Optional[date], Optional[date]]:
    if page in cache:
        return cache[page]

    url = build_list_url(page, base_list_url)
    html = fetcher.get(url)
    rows = extract_rows(html, url)

    d_list: List[date] = []
    for r in rows:
        if r.is_notice:
            continue
        dt, d = parse_list_date_or_datetime(r.date_text, r.date_attr, now_kst)
        row_date = dt.date() if dt else d
        if row_date:
            d_list.append(row_date)

    if not d_list:
        cache[page] = (None, None)
        return None, None

    cache[page] = (d_list[0], d_list[-1])
    return d_list[0], d_list[-1]


def find_upper_bound_for_min_date(
    fetcher: Fetcher, base_list_url: str, min_date: date, now_kst: datetime
) -> Tuple[int, Dict[int, Tuple[Optional[date], Optional[date]]]]:
    cache: Dict[int, Tuple[Optional[date], Optional[date]]] = {}

    hi = 1
    while hi <= MAX_PAGE_LIMIT:
        _first_d, last_d = get_page_date_range(fetcher, base_list_url, hi, now_kst, cache)
        if last_d is None:
            return hi, cache
        if last_d <= min_date:
            return hi, cache
        hi *= 2

    return MAX_PAGE_LIMIT, cache


def find_start_page_for_date(
    fetcher: Fetcher,
    base_list_url: str,
    target: date,
    now_kst: datetime,
    hi: int,
    cache: Dict[int, Tuple[Optional[date], Optional[date]]],
) -> int:
    lo = 1
    r = hi
    ans = hi

    while lo <= r:
        mid = (lo + r) // 2
        _first, last_d = get_page_date_range(fetcher, base_list_url, mid, now_kst, cache)

        if last_d is None:
            ans = mid
            r = mid - 1
            continue

        if last_d <= target:
            ans = mid
            r = mid - 1
        else:
            lo = mid + 1

    return ans


def scrape_one_date(
    fetcher: Fetcher,
    base_list_url: str,
    target: date,
    start_t: dtime,
    end_t: dtime,
    now_kst: datetime,
    start_page: int,
) -> List[Tuple[datetime, str, str]]:
    results: List[Tuple[datetime, str, str]] = []
    done = False
    post_dt_cache: Dict[str, datetime] = {}

    page = start_page
    while page <= MAX_PAGE_LIMIT:
        page_url = build_list_url(page, base_list_url)
        html = fetcher.get(page_url)
        rows = extract_rows(html, page_url)
        if not rows:
            break

        for r in rows:
            if r.is_notice:
                continue

            dt_guess, d_guess = parse_list_date_or_datetime(r.date_text, r.date_attr, now_kst)
            row_date = dt_guess.date() if dt_guess else d_guess
            if row_date is None:
                continue

            if row_date > target:
                continue

            if row_date < target:
                done = True
                break

            # row_date == target -> 시간 확정 필요
            if dt_guess is None:
                if r.url in post_dt_cache:
                    dt = post_dt_cache[r.url]
                else:
                    jitter_sleep(SLEEP_POST)
                    post_html = fetcher.get(r.url, referer=page_url)
                    dt = parse_datetime_from_post(post_html)
                    if dt is None:
                        continue
                    post_dt_cache[r.url] = dt
            else:
                dt = dt_guess

            t = dt.timetz().replace(tzinfo=None)

            # ✅ 08:50 이전으로 내려가면 즉시 중단
            if t < start_t:
                done = True
                break

            if start_t <= t <= end_t:
                results.append((dt, r.title, r.url))

        if done:
            break

        jitter_sleep(SLEEP_LIST)
        page += 1

    return results


def run_once(fetcher: Fetcher) -> None:
    now_kst = datetime.now(KST)
    start_t = parse_hhmm(START_TIME_STR)
    end_t = parse_hhmm(END_TIME_STR)
    ensure_dir(OUT_DIR)

    print("=== DCInside Backtest Scraper ===")
    print(f"BOARD_ID   = {BOARD_ID}")
    print(f"FETCH_MODE = {FETCH_MODE}")
    print(f"OUT_PREFIX = {OUT_PREFIX}")
    print(f"OUT_DIR    = {OUT_DIR}")
    print(f"TIME       = {START_TIME_STR} ~ {END_TIME_STR} (KST)")
    print("=================================")

    # ✅ base 자동 선택
    base_list_url, first_page_html = choose_base_list_url(fetcher)
    print(f"[INFO] 선택된 BASE_LIST_URL = {base_list_url}")

    # 날짜 확정
    if TARGET_DATE_STR:
        requested_dates = [date.fromisoformat(TARGET_DATE_STR)]
        target_dates = requested_dates[:]
    else:
        requested_dates = load_dates_from_file(DATES_FILE)
        target_dates = requested_dates[:]

    if not requested_dates:
        print("대상 날짜가 없습니다. date.txt / TARGET_DATE를 확인하세요.")
        return

    # 개설일 이전 스킵
    open_date = extract_open_date_from_list(first_page_html)
    if open_date:
        target_dates = [d for d in target_dates if d >= open_date]

    all_results_by_date: Dict[date, List[Tuple[datetime, str, str]]] = {d: [] for d in requested_dates}

    if not target_dates:
        # 전부 개설일 이전 -> 빈 파일 생성
        for d in requested_dates:
            out_path = os.path.join(OUT_DIR, f"{OUT_PREFIX}_{d.isoformat()}.csv")
            write_csv(out_path, [])
        combined_path = os.path.join(OUT_DIR, f"{OUT_PREFIX}_all.csv")
        with open(combined_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["작성시간(KST)", "날짜", "제목", "URL"])
        print("[DONE] 모든 날짜가 개설일 이전이라 빈 CSV만 생성했습니다.")
        return

    min_date = min(target_dates)
    hi, cache = find_upper_bound_for_min_date(fetcher, base_list_url, min_date, now_kst)
    print(f"[INFO] 페이지 상한(hi) 추정: {hi} (min_target_date={min_date})")

    for target in sorted(target_dates, reverse=True):
        start_page = find_start_page_for_date(fetcher, base_list_url, target, now_kst, hi, cache)
        print(f"\n=== {target} 시작 페이지: {start_page} ===")
        rows = scrape_one_date(fetcher, base_list_url, target, start_t, end_t, now_kst, start_page)
        all_results_by_date[target] = rows
        print(f"[OK] {target} 수집 {len(rows)}건")

    # 날짜별 CSV
    for d in requested_dates:
        out_path = os.path.join(OUT_DIR, f"{OUT_PREFIX}_{d.isoformat()}.csv")
        write_csv(out_path, all_results_by_date.get(d, []))

    # 합본 CSV
    combined_path = os.path.join(OUT_DIR, f"{OUT_PREFIX}_all.csv")
    combined_rows: List[Tuple[datetime, str, str, str]] = []
    for d in requested_dates:
        for dt, title, url in all_results_by_date.get(d, []):
            combined_rows.append((dt, d.isoformat(), title, url))
    combined_rows.sort(key=lambda x: x[0])

    with open(combined_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["작성시간(KST)", "날짜", "제목", "URL"])
        for dt, d_str, title, url in combined_rows:
            w.writerow([dt.strftime("%Y-%m-%d %H:%M:%S"), d_str, title, url])

    print("\n[DONE] CSV 생성 완료")
    print(f"- 폴더: {OUT_DIR}")
    print(f"- 합본: {combined_path}")


def main():
    # auto 모드면 requests 먼저, 막히면 playwright로 1회 재시도
    mode = FETCH_MODE

    if mode not in ("requests", "playwright", "auto"):
        print(f"[WARN] FETCH_MODE='{mode}' 는 지원하지 않습니다. requests로 실행합니다.")
        mode = "requests"

    tried_playwright = False

    def _run_with(fetcher: Fetcher):
        try:
            run_once(fetcher)
        finally:
            try:
                fetcher.close()
            except Exception:
                pass

    if mode in ("requests", "auto"):
        fetcher = RequestsFetcher()
        fetcher.warmup()
        try:
            _run_with(fetcher)
            return
        except BlockedBySiteError as e:
            print(f"[WARN] requests 접근이 차단된 것으로 보입니다: {e}")
            if mode != "auto":
                raise
            tried_playwright = True
        except RuntimeError as e:
            msg = str(e)
            if "blocked" in msg.lower() and mode == "auto":
                print(f"[WARN] requests가 차단된 것으로 보입니다: {e}")
                tried_playwright = True
            else:
                raise

    if mode == "playwright" or tried_playwright:
        try:
            fetcher = PlaywrightFetcher()
        except Exception as e:
            raise RuntimeError(
                "Playwright 모드로 전환하려 했지만 playwright가 설치되어 있지 않거나 초기화 실패했습니다. "
                "워크플로우에서 playwright 설치/브라우저 설치 단계를 추가하세요."
            ) from e

        _run_with(fetcher)
        return


if __name__ == "__main__":
    main()
