# main.py
import os
import re
import csv
import time
import random
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

# 특정 날짜만 단일 실행하고 싶으면 (YYYY-MM-DD). 비우면 date.txt 전체 실행
TARGET_DATE_STR = os.getenv("TARGET_DATE", "").strip()

# 날짜 파일 (각 줄 첫 토큰이 YYYY-MM-DD 라면 OK)
DATES_FILE = os.getenv("DATES_FILE", "date.txt").strip()

# 페이지/부하 제어
LIST_NUM = int(os.getenv("LIST_NUM", "100"))  # 30/50/100 중 하나(기본 100 추천)
MAX_PAGE_LIMIT = int(os.getenv("MAX_PAGE_LIMIT", "20000"))  # 안전 상한

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "6"))
SLEEP_LIST = float(os.getenv("SLEEP_LIST", "0.9"))  # list 페이지 간 sleep
SLEEP_POST = float(os.getenv("SLEEP_POST", "0.7"))  # 상세 페이지 간 sleep

DEBUG = os.getenv("DEBUG", "0").strip() == "1"

# User-Agent (봇 차단 완화에 도움)
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# ✅ 일반갤/마이너갤 모두 대응(자동 선택)
BASE_LIST_URL_CANDIDATES = [
    "https://gall.dcinside.com/mgallery/board/lists/",  # 마이너
    "https://gall.dcinside.com/board/lists/",          # 일반
]

# =========================
# 데이터 구조
# =========================
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
def jitter_sleep(base: float) -> None:
    if base <= 0:
        return
    time.sleep(base + random.uniform(0, base * 0.35))


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def clean_title(s: str) -> str:
    """
    - 공백 정리
    - 제목 끝 댓글수 [12] 제거
    """
    s = re.sub(r"\s+", " ", (s or "")).strip()
    s = re.sub(r"\[\d+\]\s*$", "", s).strip()
    return s


def uniq_keep_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        x = (x or "").strip()
        if not x:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def build_list_url(page: int, base_list_url: str) -> str:
    """
    DCInside list URL 생성: id/page/list_num
    """
    parts = urlsplit(base_list_url)
    qs = parse_qs(parts.query)
    qs["id"] = [BOARD_ID]
    qs["page"] = [str(page)]
    qs["list_num"] = [str(LIST_NUM)]
    new_query = urlencode(qs, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def make_session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update(DEFAULT_HEADERS)
    return sess


# =========================
# 차단/봇방지 페이지 감지(200 OK로 내려오는 경우가 있어서 텍스트 기반 감지 추가)
# =========================
_BLOCK_KEYWORDS = [
    "보안문자",
    "자동입력",
    "자동 입력",
    "captcha",
    "캡차",
    "접근이 제한",
    "접근 제한",
    "비정상적인",
    "요청이 너무 많",
    "잠시 후 다시",
    "service unavailable",
    "access denied",
    "cloudflare",
]


def looks_like_blocked(html: str) -> bool:
    h = (html or "").lower()
    return any(kw.lower() in h for kw in _BLOCK_KEYWORDS)


def fetch_html(session: requests.Session, url: str, referer: Optional[str] = None) -> str:
    """
    재시도 + 백오프 fetch
    - HTTP 403/429 뿐 아니라, 200 OK + 차단/캡차 페이지도 감지해서 재시도
    """
    last_err: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = {}
            if referer:
                headers["Referer"] = referer

            resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 200 and resp.text:
                # ✅ 200이지만 차단 페이지(캡차/접근제한)일 수 있음
                if looks_like_blocked(resp.text):
                    last_err = RuntimeError("blocked(html)")
                    jitter_sleep(2.0 * attempt)
                    continue
                return resp.text

            # 차단/레이트리밋 가능 코드들
            if resp.status_code in (403, 429, 500, 502, 503, 504):
                last_err = RuntimeError(f"HTTP {resp.status_code}")
                jitter_sleep(1.5 * attempt)
                continue

            last_err = RuntimeError(f"HTTP {resp.status_code}")
            jitter_sleep(1.0 * attempt)

        except Exception as e:
            last_err = e
            jitter_sleep(1.5 * attempt)

    raise RuntimeError(f"요청 실패: {url} / 마지막 에러: {last_err}")


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

    # fallback: td들 중 날짜/시간 패턴을 찾기 (보통 가장 오른쪽에 있음)
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

        # title / data-xxx 에 전체 timestamp가 있는 경우
        for k, v in (td.attrs or {}).items():
            if isinstance(v, str) and re.search(r"\d{4}[./-]\d{2}[./-]\d{2}\s+[0-2]\d:[0-5]\d", v):
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


def _is_comment_count_text(txt: str) -> bool:
    # 댓글수 링크는 보통 "[3]" 형태
    return bool(re.fullmatch(r"\[\d+\]", (txt or "").strip()))


def _pick_best_view_anchor(tr) -> Tuple[Optional[BeautifulSoup], str]:
    """
    ✅ 코스피 갤러리처럼 한 행(tr)에 board/view 링크가 여러 개 들어가는 경우가 많음.
    (아이콘 링크 / 댓글수 링크 / 제목 링크)

    - 가능한 td.gall_tit 안에서 "제목 링크"를 고르고
    - 텍스트가 비었거나 "[3]" 같은 댓글수 링크는 제외
    - 남은 후보 중 '가장 긴 제목 텍스트'를 제목 링크로 선택
    """
    # 1) 제목 td 안에서 우선 탐색
    title_td = tr.select_one("td.gall_tit") or tr.find("td", class_=re.compile(r"gall_tit"))
    a_tags = title_td.find_all("a", href=True) if title_td else tr.find_all("a", href=True)

    candidates: List[Tuple[int, BeautifulSoup, str]] = []
    for a in a_tags:
        href = a.get("href", "")
        if "board/view" not in href:
            continue
        raw = a.get_text(" ", strip=True)
        if not raw:
            continue
        if _is_comment_count_text(raw):
            continue
        title = clean_title(raw)
        if not title:
            continue
        candidates.append((len(title), a, title))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1], candidates[0][2]

    # 2) fallback: tr 전체에서 텍스트가 있는 view 링크 중 하나
    for a in tr.find_all("a", href=True):
        href = a.get("href", "")
        if "board/view" not in href:
            continue
        raw = a.get_text(" ", strip=True)
        if not raw or _is_comment_count_text(raw):
            continue
        title = clean_title(raw)
        if title:
            return a, title

    # 3) 최후 fallback
    a = tr.select_one("a[href*='board/view']")
    if a and a.get("href"):
        title = clean_title(a.get_text(" ", strip=True))
        return a, title

    return None, ""


def extract_rows(html: str, page_url: str) -> List[PostRow]:
    """
    리스트 페이지에서:
    - 글 번호(숫자)인 행만 추출 (AD/설문은 '-'라서 자연스럽게 제외)
    - 제목/링크/작성일 텍스트(+가능하면 전체 timestamp attr)
    """
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

        # ✅ 제목 링크(가장 중요한 수정 포인트)
        a, title = _pick_best_view_anchor(tr)
        if not a or not a.get("href"):
            continue
        if not title:
            continue
        url = urljoin(page_url, a["href"])

        # 작성일
        date_td = _find_date_td(tr)
        if not date_td:
            continue

        date_text = date_td.get_text(" ", strip=True)

        # title / data-xxx 등에서 전체 timestamp 뽑기
        date_attr = None
        if date_td.has_attr("title"):
            date_attr = str(date_td.get("title", "")).strip() or None
        else:
            child = date_td.find(attrs={"title": True})
            if child:
                date_attr = str(child.get("title", "")).strip() or None

        if not date_attr:
            # data-* 속성에 들어있는 경우까지 커버
            for k, v in (date_td.attrs or {}).items():
                if isinstance(v, str) and re.search(r"\d{4}[./-]\d{2}[./-]\d{2}\s+[0-2]\d:[0-5]\d", v):
                    date_attr = v.strip()
                    break

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
# 시간/날짜 파싱
# =========================
def parse_full_datetime(s: str) -> Optional[datetime]:
    s = (s or "").strip()
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
    """
    (dt, d) 반환:
    - dt: 시간까지 확정된 경우 (오늘 HH:MM, 혹은 attr로 전체 timestamp 확보)
    - d : 날짜만 아는 경우 (YY.MM.DD / MM.DD 등)
    """
    # 1) attr에 전체 timestamp가 있으면 최우선
    if date_attr:
        dt = parse_full_datetime(date_attr)
        if dt:
            return dt, None

    s = re.sub(r"\s+", " ", (date_text or "").strip())

    # 2) HH:MM -> 오늘 날짜로 결합
    if re.fullmatch(r"\d{1,2}:\d{2}", s):
        h, m = map(int, s.split(":"))
        return datetime.combine(now_kst.date(), dtime(h, m), tzinfo=KST), None

    # 3) YY.MM.DD / YY/MM/DD / YY-MM-DD
    m = re.fullmatch(r"(\d{2})[.\-/](\d{2})[.\-/](\d{2})", s)
    if m:
        yy, mo, dd = map(int, m.groups())
        return None, date(2000 + yy, mo, dd)

    # 4) YYYY.MM.DD / YYYY/MM/DD / YYYY-MM-DD
    m = re.fullmatch(r"(\d{4})[.\-/](\d{2})[.\-/](\d{2})", s)
    if m:
        y, mo, dd = map(int, m.groups())
        try:
            return None, date(y, mo, dd)
        except ValueError:
            return None, None

    # 5) MM.DD -> 올해 기준 + 롤오버 보정
    if re.fullmatch(r"\d{2}\.\d{2}", s):
        mo, dd = map(int, s.split("."))
        y = now_kst.year
        candidate = date(y, mo, dd)
        if candidate > now_kst.date():
            candidate = date(y - 1, mo, dd)
        return None, candidate

    return None, None


def parse_datetime_from_post(html: str) -> Optional[datetime]:
    """
    글 상세에서 'YYYY.MM.DD HH:MM:SS' 패턴을 텍스트 기반으로 추출
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    m = re.search(r"(\d{4}[.\-/]\d{2}[.\-/]\d{2})\s+([0-2]\d:[0-5]\d:[0-5]\d)", text)
    if m:
        for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", fmt)
                return dt.replace(tzinfo=KST)
            except ValueError:
                pass

    m = re.search(r"(\d{4}[.\-/]\d{2}[.\-/]\d{2})\s+([0-2]\d:[0-5]\d)", text)
    if m:
        for fmt in ("%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", fmt)
                return dt.replace(tzinfo=KST)
            except ValueError:
                pass

    return None


def parse_hhmm(s: str) -> dtime:
    s = (s or "").strip()
    m = re.fullmatch(r"([0-2]?\d):([0-5]\d)", s)
    if not m:
        raise ValueError(f"시간 형식 오류(HH:MM): {s}")
    h = int(m.group(1))
    mi = int(m.group(2))
    if h > 23:
        raise ValueError(f"시간 범위 오류: {s}")
    return dtime(h, mi)


def load_dates_from_file(path: str) -> List[date]:
    """
    date.txt에서 각 줄 첫 토큰이 YYYY-MM-DD인 것만 읽음
    (BOM 제거를 위해 utf-8-sig 사용)
    """
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
# BASE_LIST_URL 자동 선택
# =========================
def choose_base_list_url(session: requests.Session) -> Tuple[str, str]:
    candidates = uniq_keep_order([ENV_BASE_LIST_URL] + BASE_LIST_URL_CANDIDATES)

    for base in candidates:
        try:
            test_url = build_list_url(1, base)
            html = fetch_html(session, test_url)
            rows = extract_rows(html, test_url)

            # view 링크 중 id=BOARD_ID가 포함된 row가 1개라도 있으면 성공으로 간주
            valid = [r for r in rows if f"id={BOARD_ID}" in r.url]
            if DEBUG:
                print(f"[DEBUG] base 후보: {base} -> rows={len(rows)}, valid_id_rows={len(valid)}")
                if valid:
                    s = valid[0]
                    print(f"[DEBUG] sample row: no={s.post_no}, date='{s.date_text}', title='{s.title[:40]}'")
            if valid:
                return base, html

        except Exception as e:
            if DEBUG:
                print(f"[DEBUG] base 후보 실패: {base} / {e}")

    raise RuntimeError(f"유효한 리스트 페이지를 찾지 못했습니다. BOARD_ID='{BOARD_ID}'")


# =========================
# 페이지 탐색(이진탐색 + break)
# =========================
def get_page_date_range(
    session: requests.Session,
    base_list_url: str,
    page: int,
    now_kst: datetime,
    cache: Dict[int, Tuple[Optional[date], Optional[date]]],
) -> Tuple[Optional[date], Optional[date]]:
    """
    페이지의 (첫 글 날짜, 마지막 글 날짜)만 뽑아서 반환 (이진탐색용)
    """
    if page in cache:
        return cache[page]

    url = build_list_url(page, base_list_url)
    html = fetch_html(session, url)
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
    session: requests.Session, base_list_url: str, min_date: date, now_kst: datetime
) -> Tuple[int, Dict[int, Tuple[Optional[date], Optional[date]]]]:
    """
    min_date(가장 과거 목표 날짜)까지 도달 가능한 hi 페이지를 지수적으로 탐색
    """
    cache: Dict[int, Tuple[Optional[date], Optional[date]]] = {}

    hi = 1
    while hi <= MAX_PAGE_LIMIT:
        _first_d, last_d = get_page_date_range(session, base_list_url, hi, now_kst, cache)
        if last_d is None:
            return hi, cache
        if last_d <= min_date:
            return hi, cache
        hi *= 2

    return MAX_PAGE_LIMIT, cache


def find_start_page_for_date(
    session: requests.Session,
    base_list_url: str,
    target: date,
    now_kst: datetime,
    hi: int,
    cache: Dict[int, Tuple[Optional[date], Optional[date]]],
) -> int:
    """
    last_date(page) <= target 을 만족하는 가장 작은 page를 찾는다.
    """
    lo = 1
    r = hi
    ans = hi

    while lo <= r:
        mid = (lo + r) // 2
        _first, last_d = get_page_date_range(session, base_list_url, mid, now_kst, cache)

        if last_d is None:
            ans = mid
            r = mid - 1
            continue

        if last_d <= target:
            ans = mid
            r = mid - 1
        else:
            lo = mid + 1

    return max(1, ans)


def _fetch_post_datetime_with_retry(
    session: requests.Session, url: str, referer: str
) -> Optional[datetime]:
    """
    상세 페이지에서 datetime 파싱이 실패할 경우,
    (차단/일시 오류) 가능성 때문에 몇 번 더 시도.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        post_html = fetch_html(session, url, referer=referer)
        dt = parse_datetime_from_post(post_html)
        if dt is not None:
            return dt
        jitter_sleep(1.0 * attempt)
    return None


def scrape_one_date(
    session: requests.Session,
    base_list_url: str,
    target: date,
    start_t: dtime,
    end_t: dtime,
    now_kst: datetime,
    start_page: int,
) -> List[Tuple[datetime, str, str]]:
    """
    start_page부터 순차 탐색.
    - target 날짜인 글만 상세 시간 확인(필요할 때)
    - target 날짜에서 작성시간이 start_t보다 이전이면 즉시 break
    """
    results: List[Tuple[datetime, str, str]] = []
    done = False
    post_dt_cache: Dict[str, datetime] = {}

    page = start_page
    while page <= MAX_PAGE_LIMIT:
        page_url = build_list_url(page, base_list_url)
        html = fetch_html(session, page_url)
        rows = extract_rows(html, page_url)

        # rows가 비면 보통 차단/오류일 확률이 높아서 "바로 종료" 대신 재시도 유도
        if not rows:
            if DEBUG:
                print(f"[WARN] rows=0 (page={page}) -> 잠시 후 재시도")
            jitter_sleep(2.0)
            html = fetch_html(session, page_url)
            rows = extract_rows(html, page_url)
            if not rows:
                if DEBUG:
                    print(f"[WARN] rows=0 (page={page}) -> 종료")
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

            # row_date == target
            if dt_guess is None:
                if r.url in post_dt_cache:
                    dt = post_dt_cache[r.url]
                else:
                    jitter_sleep(SLEEP_POST)
                    dt = _fetch_post_datetime_with_retry(session, r.url, referer=page_url)
                    if dt is None:
                        continue
                    post_dt_cache[r.url] = dt
            else:
                dt = dt_guess

            t = dt.timetz().replace(tzinfo=None)

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


def main():
    now_kst = datetime.now(KST)
    start_t = parse_hhmm(START_TIME_STR)
    end_t = parse_hhmm(END_TIME_STR)
    ensure_dir(OUT_DIR)

    print("=== DCInside Backtest Scraper ===")
    print(f"BOARD_ID   = {BOARD_ID}")
    print(f"OUT_PREFIX = {OUT_PREFIX}")
    print(f"OUT_DIR    = {OUT_DIR}")
    print(f"TIME       = {START_TIME_STR} ~ {END_TIME_STR} (KST)")
    print("=================================")

    session = make_session()

    base_list_url, first_page_html = choose_base_list_url(session)
    if DEBUG:
        print(f"[INFO] 선택된 BASE_LIST_URL = {base_list_url}")

    if TARGET_DATE_STR:
        requested_dates = [date.fromisoformat(TARGET_DATE_STR)]
        target_dates = requested_dates[:]
    else:
        requested_dates = load_dates_from_file(DATES_FILE)
        target_dates = requested_dates[:]

    if not requested_dates:
        print("대상 날짜가 없습니다. date.txt / TARGET_DATE를 확인하세요.")
        return

    open_date = extract_open_date_from_list(first_page_html)
    if open_date:
        target_dates = [d for d in target_dates if d >= open_date]
        if DEBUG:
            print(f"[INFO] open_date = {open_date}")

    all_results_by_date: Dict[date, List[Tuple[datetime, str, str]]] = {d: [] for d in requested_dates}

    if not target_dates:
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
    hi, cache = find_upper_bound_for_min_date(session, base_list_url, min_date, now_kst)
    print(f"[INFO] 페이지 상한(hi) 추정: {hi} (min_target_date={min_date})")

    for target in sorted(target_dates, reverse=True):
        start_page = find_start_page_for_date(session, base_list_url, target, now_kst, hi, cache)
        print(f"\n=== {target} 시작 페이지: {start_page} ===")
        rows = scrape_one_date(session, base_list_url, target, start_t, end_t, now_kst, start_page)
        all_results_by_date[target] = rows
        print(f"[OK] {target} 수집 {len(rows)}건")

    for d in requested_dates:
        out_path = os.path.join(OUT_DIR, f"{OUT_PREFIX}_{d.isoformat()}.csv")
        write_csv(out_path, all_results_by_date.get(d, []))

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


if __name__ == "__main__":
    main()
