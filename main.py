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

TARGET_DATE_STR = os.getenv("TARGET_DATE", "").strip()
DATES_FILE = os.getenv("DATES_FILE", "date.txt").strip()

LIST_NUM = int(os.getenv("LIST_NUM", "100"))
MAX_PAGE_LIMIT = int(os.getenv("MAX_PAGE_LIMIT", "20000"))

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))

SLEEP_LIST = float(os.getenv("SLEEP_LIST", "0.8"))
SLEEP_POST = float(os.getenv("SLEEP_POST", "0.5"))

DEBUG = os.getenv("DEBUG", "0").strip() == "1"

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
).strip()

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

BASE_LIST_URL_CANDIDATES = [
    "https://gall.dcinside.com/mgallery/board/lists/",
    "https://gall.dcinside.com/board/lists/",
]


@dataclass(frozen=True)
class PostRow:
    post_no: int
    head: str
    title: str
    url: str
    date_text: str
    date_attr: Optional[str]
    is_notice: bool


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


def build_list_url(page: int, base_list_url: str) -> str:
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


def fetch_html(session: requests.Session, url: str, referer: Optional[str] = None) -> str:
    last_err: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = {}
            if referer:
                headers["Referer"] = referer

            resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 200 and resp.text:
                return resp.text

            if resp.status_code in (403, 429, 500, 502, 503, 504):
                last_err = RuntimeError(f"HTTP {resp.status_code}")
                jitter_sleep(1.2 * attempt)
                continue

            last_err = RuntimeError(f"HTTP {resp.status_code}")
            jitter_sleep(0.8 * attempt)

        except Exception as e:
            last_err = e
            jitter_sleep(1.2 * attempt)

    raise RuntimeError(f"요청 실패: {url} / 마지막 에러: {last_err}")


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

        # ✅ 제목/링크: td 인덱스가 아니라 tr에서 board/view 링크를 직접 찾는다
        a = tr.select_one("a[href*='board/view']") or tr.find("a", href=True)
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


def choose_base_list_url(session: requests.Session) -> Tuple[str, str]:
    candidates = uniq_keep_order([ENV_BASE_LIST_URL] + BASE_LIST_URL_CANDIDATES)

    for base in candidates:
        try:
            test_url = build_list_url(1, base)
            html = fetch_html(session, test_url)
            rows = extract_rows(html, test_url)

            # view 링크 중 id=BOARD_ID가 포함된 row가 1개라도 있으면 성공으로 간주
            valid = [r for r in rows if f"id={BOARD_ID}" in r.url]
            print(f"[DEBUG] base 후보: {base} -> rows={len(rows)}, valid_id_rows={len(valid)}")
            if valid:
                if DEBUG:
                    s = valid[0]
                    print(f"[DEBUG] sample row: no={s.post_no}, date='{s.date_text}', title='{s.title[:40]}'")
                return base, html

        except Exception as e:
            print(f"[DEBUG] base 후보 실패: {base} / {e}")

    raise RuntimeError(f"유효한 리스트 페이지를 찾지 못했습니다. BOARD_ID='{BOARD_ID}'")


def get_page_date_range(
    session: requests.Session,
    base_list_url: str,
    page: int,
    now_kst: datetime,
    cache: Dict[int, Tuple[Optional[date], Optional[date]]],
) -> Tuple[Optional[date], Optional[date]]:
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

    return ans


def scrape_one_date(
    session: requests.Session,
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
        html = fetch_html(session, page_url)
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
                    post_html = fetch_html(session, r.url, referer=page_url)
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

    # ✅ base 자동 선택
    base_list_url, first_page_html = choose_base_list_url(session)
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
    hi, cache = find_upper_bound_for_min_date(session, base_list_url, min_date, now_kst)
    print(f"[INFO] 페이지 상한(hi) 추정: {hi} (min_target_date={min_date})")

    for target in sorted(target_dates, reverse=True):
        start_page = find_start_page_for_date(session, base_list_url, target, now_kst, hi, cache)
        print(f"\n=== {target} 시작 페이지: {start_page} ===")
        rows = scrape_one_date(session, base_list_url, target, start_t, end_t, now_kst, start_page)
        all_results_by_date[target] = rows
        print(f"[OK] {target} 수집 {len(rows)}건")

    # 날짜별 CSV
    for d in requested_dates:
        out_path = os.path.join(OUT_DIR, f"{OUT_PREFIX}_{d.isoformat()}.csv")  # ✅ 언더스코어 수정
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


if __name__ == "__main__":
    main()
