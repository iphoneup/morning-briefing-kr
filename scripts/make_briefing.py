#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
매일 아침 브리핑 JSON 생성기
- 뉴스: Google News RSS (경제/정치/연예/증시)
- 상한가: '상한가' 키워드 뉴스 제목에서 종목명/이유 추출 (키 없음, 휴리스틱)
- 섹터: data/sectors.json 고정 리스트

출력: 리포 루트에 briefing.json
"""
from urllib.parse import quote_plus
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any

import feedparser
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_FILE = ROOT / "briefing.json"

# -------- CONFIG --------
KST = timezone(timedelta(hours=9))
MAX_HEADLINES_PER_CAT = 5

NEWS_QUERIES = {
    "economy": "경제",
    "politics": "정치",
    "entertainment": "연예",
    "market": "증시 OR 코스피 OR 코스닥"
}

# Google News RSS base
GN_RSS = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"})

# ------------------------


def now_kst() -> datetime:
    return datetime.now(tz=KST)


def last_trading_day(base_dt: datetime) -> datetime:
    # 주말 처리: 토(5)/일(6) → 금(4)로
    wd = base_dt.weekday()  # 월=0 ... 일=6
    if wd == 5:   # 토
        return (base_dt - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if wd == 6:   # 일
        return (base_dt - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    if wd == 0 and base_dt.hour < 9:
        # 월요일 아침 9시 전엔 전 영업일(금) 기준으로 표기하고 싶으면 여기서 -3일
        return (base_dt - timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)
    return base_dt.replace(hour=0, minute=0, second=0, microsecond=0)


def get_google_news(query: str, max_items: int = 5) -> List[Dict[str, Any]]:
    url = GN_RSS.format(q=quote_plus(query))
    feed = feedparser.parse(url)
    items = []
    for e in feed.entries[:max_items]:
        title = e.get("title", "").strip()
        link = e.get("link", "").strip()
        # publisher/source
        src = ""
        if "source" in e and e.source and hasattr(e.source, "title"):
            src = getattr(e.source, "title", "") or ""
        # 일부는 feedburner형식. publisher 추출 실패 시 도메인으로 대체
        if not src and link:
            try:
                host = requests.utils.urlparse(link).netloc
                src = host.replace("www.", "")
            except Exception:
                src = ""
        items.append(
            {
                "title": title,
                "url": link,
                "src": src
            }
        )
    return items


def clean_title(txt: str) -> str:
    t = re.sub(r"\[[^\]]+\]", "", txt)            # [브라켓] 제거
    t = re.sub(r"\([^)]*\)", "", t)               # (괄호) 제거
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


def extract_names_from_title(title: str) -> List[str]:
    """
    뉴스 제목에서 '상한가' 문맥의 종목명 후보 추출 (휴리스틱)
    예) "에코프로비엠 상한가… 양극재 반등" → ["에코프로비엠"]
        "한화에어로·LIG넥스 상한가" → ["한화에어로", "LIG넥스"]
    """
    t = clean_title(title)
    if "상한가" not in t:
        return []
    # 구분자 기준으로 나눠 앞쪽(상한가 앞부분) 후보에서 종목명 추출
    left = t.split("상한가")[0]
    # 나열 구분자 분해
    parts = re.split(r"[·,／/∙ㆍ•&]|와|및|과|\+", left)
    names = []
    for p in parts:
        p = p.strip(" -—:·,")
        # 종목명 형태: 한글/영문/숫자/하이픈/닷 조합, 길이 2~20
        if re.fullmatch(r"[가-힣A-Za-z0-9\.\-&]{2,20}", p):
            names.append(p)
        else:
            # 공백 포함 케이스 처리
            p2 = re.sub(r"[^가-힣A-Za-z0-9\.\-&\s]", "", p).strip()
            if 2 <= len(p2) <= 20 and re.search(r"[가-힣A-Za-z]", p2):
                names.append(p2)
    # 중복 제거, 길이 필터
    out = []
    for n in names:
        if n and n not in out:
            out.append(n)
    return out


def extract_reason_from_title(title: str) -> str:
    """
    제목에서 간단 이유 추정: '—', '-', ':', '…' 이후의 짧은 구절
    """
    t = clean_title(title)
    # 후보 구분자
    for sep in ["—", "-", ":", "…", "..", "··", "·"]:
        if sep in t:
            seg = t.split(sep, 1)[-1].strip()
            if 4 <= len(seg) <= 60:
                return seg
    # '상한가' 이후 문장을 짧게
    if "상한가" in t:
        seg = t.split("상한가", 1)[-1].strip(" .!?,/·-—")
        if 4 <= len(seg) <= 60:
            return seg
    # fallback: 원제목 60자 자르기
    return t[:60]


def fetch_article_text(url: str, timeout: int = 8) -> str:
    try:
        resp = SESSION.get(url, timeout=timeout)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, "lxml")
        # 메타 설명이나 본문에서 텍스트 추출
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        # 일반 본문 후보
        ps = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        txt = " ".join(ps)
        return re.sub(r"\s{2,}", " ", txt).strip()
    except Exception:
        return ""


def extract_limit_up(max_items: int = 10) -> List[Dict[str, str]]:
    """
    '상한가' 키워드 뉴스에서 종목명 후보를 모아 최대 10개 생성.
    - 정확도: 제목 기반 휴리스틱(키 없음)
    - 개선: 백엔드에 증권사 API나 공시 크롤링을 붙이면 정확도 ↑
    """
    queries = [
        '상한가 종목',
        '특징주 상한가',
        '코스닥 상한가',
        '코스피 상한가'
    ]
    entries: List[Dict[str, Any]] = []
    seen_titles = set()
    for q in queries:
        items = get_google_news(q, max_items=8)
        for it in items:
            t = it["title"]
            if t in seen_titles:
                continue
            seen_titles.add(t)
            if "상한가" in t:
                entries.append(it)

    # 제목에서 종목명 후보 추출
    picks: List[Dict[str, str]] = []
    seen_names = set()
    for e in entries:
        title = e["title"]
        names = extract_names_from_title(title)
        if not names:
            # 기사 본문에서 한 번 더 시도
            body = fetch_article_text(e["url"])
            if "상한가" in body:
                # 간단 추정: '… 상한가' 앞 단어 1~2개
                m = re.search(r"([가-힣A-Za-z0-9\.\-&\s]{2,20})\s*상한가", body)
                if m:
                    names = [m.group(1).strip()]
        reason = extract_reason_from_title(title)
        for n in names:
            if n in seen_names:
                continue
            seen_names.add(n)
            picks.append({"name": n, "reason": reason})
            if len(picks) >= max_items:
                break
        if len(picks) >= max_items:
            break

    return picks


def load_sectors() -> Dict[str, List[str]]:
    p = DATA_DIR / "sectors.json"
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def build_news_section() -> Dict[str, List[Dict[str, str]]]:
    res: Dict[str, List[Dict[str, str]]] = {}
    for key, q in NEWS_QUERIES.items():
        items = get_google_news(q, max_items=MAX_HEADLINES_PER_CAT)
        res[key] = items
        # 살짝 쉬기(과도요청 방지)
        time.sleep(0.4)
    return res


def main() -> int:
    ts = now_kst()
    ltd = last_trading_day(ts)
    is_weekend = ts.weekday() >= 5

    news = build_news_section()
    limit_up = extract_limit_up(max_items=10)
    sectors = load_sectors()

    sector_order = list(sectors.keys())  # 추가

    out = {
        "generated_at": ts.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "date": ts.strftime("%Y-%m-%d"),
        "last_trading_day": ltd.strftime("%Y-%m-%d"),
        "weekend_note": "금요일 장 기준 브리핑입니다." if is_weekend else "",
        "news": news,
        "limit_up": limit_up,
        "sectors": sectors,
        "sector_order": sector_order     # 추가
    }

    with OUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
