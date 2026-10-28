#!/usr/bin/env python3
"""상품 등록 이슈를 읽어 스레드 게시 초안 이슈를 만든다.

상품 등록 이슈
  제목: '상품'으로 시작 (예: 상품 10/23). '바로'가 들어가면 승인 없이 바로 예약, '따로'가 들어가면 상품마다 따로 게시.
  본문: 토스 쉐어링크 공유 문구를 그대로 붙이고, 링크 바로 아래 줄에 가격, 그 아래에 토스 앱 캡처를 붙인다.
      ✱ 이 포스팅은 토스쇼핑 쉐어링크 활동의 일환으로, …
      크리스탈 생수, 무라벨, 2L, 12개
      https://toss.shopping/_m/D7AMJNwi
      5350/18000           ← 할인가/정가 (정가 없으면 5350/70% 또는 5350)
      한마디: 첫 줄 직접 쓰기  ← 선택. 없으면 자동
      (토스 앱 상품 화면 캡처)  ← 선택. 없으면 디자인 카드
  여러 상품을 이어서 붙이면 'BEST N' 모음 글 하나로 묶는다.

게시 형식 (2026-10-26 레퍼런스 반영)
  본문: '#광고' + 첫 한마디 + 가격·개당 가격·리뷰 + 이미지(캡처, 여러 장이면 넘겨 보기)
  댓글: 광고 표시 전체 문구 + '상품명 가격' + 링크 (이모지는 쓰지 않는다)

하는 일
  1. 링크에서 상품명·대표 사진·평점·리뷰 수·순위를 가져온다 (가격은 토스 웹에 없어서 사람이 적는다)
  2. 캡처는 images/shots/, 캡처가 없는 상품은 디자인 카드를 images/cards/ 에 저장한다
  3. 비어 있는 게시 시간대에 '초안 M/D HH:MM 이름' 이슈를 만든다
  4. 상품 등록 이슈에 '승인' 댓글이 달리면 그 초안들을 '예약'으로 바꾼다 → post_threads.py가 게시

환경 변수: GITHUB_TOKEN, GITHUB_REPOSITORY, EVENT_NAME, ISSUE_NUMBER, COMMENT_BODY
"""
import base64
import datetime as dt
import html
import io
import json
import math
import os
import re
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
from post_threads import IMG_MD, IMG_TAG, KST, REPLY_MARK, PostError, comment, download, gh, http  # noqa: E402

REPO = os.environ.get("GITHUB_REPOSITORY", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "assets", "fonts")

DISCLOSURE = "✱ 이 포스팅은 토스쇼핑 쉐어링크 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
SLOTS = ["08:30", "12:30", "20:30"]       # 하루 게시 시간대 (한국 시간)
MIN_LEAD = dt.timedelta(minutes=30)       # 지금부터 최소 이만큼 뒤 시간대부터
BATCH_MARK = "<!-- batch:{} -->"
DONE_PREFIX = "상품(처리됨)"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

URL_RE = re.compile(r"https?://(?:toss\.shopping|sharelink\.toss\.im|[\w.-]*toss\.im)/[A-Za-z0-9_\-./?=&%#]+")   # 토스 링크만 (다른 주소는 무시)
HOOK_RE = re.compile(r"^한마디\s*[:：]\s*(.+)$")
PRICE_RE = re.compile(r"^\s*(\d[\d,]*)\s*원?\s*(?:/\s*(\d[\d,]*)\s*(원|%)?)?\s*$")   # 할인가 / 정가 또는 할인율%


def fmt(n):
    return f"{round(n):,}"


# ---------- 붙여 넣은 공유 문구 해석 ----------
def parse_batch(body):
    items, pending, last = [], {"name": "", "disc": "", "price": None, "hook": "", "shots": []}, None
    body = re.sub(r"<!--.*?-->", "", (body or "").replace("\r\n", "\n"), flags=re.S)
    for raw in body.split("\n"):
        line = raw.strip()
        if not line:
            continue
        shots = [m.group(1) for m in IMG_MD.finditer(line)] + [m.group(1) for m in IMG_TAG.finditer(line)]
        if shots:   # 붙여 넣은 캡처: 바로 앞 상품의 것 (첫 상품 앞이면 다음 상품의 것)
            (last["shots"] if last else pending["shots"]).extend(shots)
            continue
        hook = HOOK_RE.match(line)
        if hook:
            if last and not last["hook"]:
                last["hook"] = hook.group(1).strip()
            else:
                pending["hook"] = hook.group(1).strip()
            continue
        url = URL_RE.search(line)
        price = PRICE_RE.match(line)
        if url:
            last = {"name": pending["name"], "disc": pending["disc"] or DISCLOSURE,
                    "link": url.group(0), "sale": None, "orig": None, "pct": None,
                    "hook": pending["hook"], "shots": pending["shots"]}
            if pending["price"]:
                last["sale"], last["orig"], last["pct"] = pending["price"]
            items.append(last)
            pending = {"name": "", "disc": "", "price": None, "hook": "", "shots": []}
        elif price:
            second = int(price.group(2).replace(",", "")) if price.group(2) else None
            if price.group(3) == "%":   # 토스 앱에 정가 없이 할인율만 보일 때: 5350/70%
                nums = (int(price.group(1).replace(",", "")), None, second)
            else:
                nums = (int(price.group(1).replace(",", "")), second, None)
            if last and last["sale"] is None:
                last["sale"], last["orig"], last["pct"] = nums
            else:
                pending["price"] = nums
        elif line.startswith("✱") or "수수료" in line:
            pending["disc"] = line
        else:
            pending["name"] = line
    # 캡처를 맨 끝에 몰아서 붙였으면 상품 순서대로 하나씩 나눠 준다
    all_shots = [u for it in items for u in it["shots"]]
    if len(items) > 1 and len(all_shots) == len(items) and any(not it["shots"] for it in items):
        for it, u in zip(items, all_shots):
            it["shots"] = [u]
    for it in items:   # 정가/할인가를 거꾸로 적은 경우
        if it["orig"] and it["sale"] and it["orig"] < it["sale"]:
            it["sale"], it["orig"] = it["orig"], it["sale"]
    return items


# ---------- 링크에서 상품 정보 ----------
def fetch_meta(link):
    meta = {}
    try:
        req = urllib.request.Request(link, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
        with urllib.request.urlopen(req, timeout=30) as r:
            page = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print("상품 페이지를 못 열었어요:", e)
        return meta

    def og(prop):
        m = re.search(r'<meta[^>]+property="%s"[^>]+content="([^"]*)"' % prop, page) or \
            re.search(r'<meta[^>]+content="([^"]*)"[^>]+property="%s"' % prop, page)
        return html.unescape(m.group(1)) if m else ""

    meta["title"] = re.sub(r"\s*\|\s*토스쇼핑\s*$", "", og("og:title"))
    meta["image"] = og("og:image")
    desc = og("og:description")
    rank = re.search(r",\s*([^,.]{1,20}?\d+위)", desc)
    meta["rank"] = rank.group(1).strip() if rank else ""
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        rating = data.get("aggregateRating") if isinstance(data, dict) else None
        if rating:
            meta["rating"] = float(rating.get("ratingValue") or 0)
            meta["reviews"] = int(rating.get("reviewCount") or 0)
    return meta


# ---------- 상품 정보 정리 ----------
def auto_display(name):
    parts = [p.strip() for p in name.split(",") if p.strip()]
    parts = [p for p in parts if not re.match(r"^1\s*(개|팩|박스|세트|봉|통|병)$", p)]
    if len(parts) <= 1:
        return parts
    return [parts[0], " · ".join(parts[1:])]


def guess_short(name):
    first = re.sub(r"\(.*?\)|\[.*?\]", "", name.split(",")[0]).strip()
    words = first.split()
    for w in reversed(words):
        if re.search(r"(형|용|식|타입)$", w) or w in ("대용량", "소용량", "특대", "국내산", "무료배송", "정품", "신상") or re.search(r"\d", w):
            continue
        return w
    return words[-1] if words else ""


def guess_qty(name):
    count, packs = None, 1
    for seg in (s.strip() for s in name.split(",")):
        m = re.match(r"^(\d[\d,]*)\s*([가-힣]+)$", seg)
        if not m:
            continue
        n, u = int(m.group(1).replace(",", "")), m.group(2)
        if re.match(r"^(구|개입|입|매|개|롤|캔|병|포|장|알)$", u) and not (u == "개" and n == 1 and count):
            if not count:
                count = (n, "개" if u == "개입" else u)
            elif u == "개":
                packs *= n
        elif re.match(r"^(팩|봉|박스|세트|묶음|통|번들)$", u):
            packs *= n
    if count and count[0] * packs > 1:
        return count[0] * packs, count[1]
    if packs > 1:
        return packs, "팩"
    return 1, "개"


def guess_grams(name):
    """총 무게(g). '1kg, 2개' → 2000, '200g, 5개' → 1000. 무게가 없으면 0."""
    grams, mult = 0, 1
    for seg in (x.strip() for x in re.split(r"\s\+\s", name)[0].split(",")):   # "A + B" 구성은 앞 상품만 ("1++" 등급은 그대로)
        w = re.match(r"^(\d+(?:\.\d+)?)\s*(kg|g)$", seg, re.I)
        if w:
            grams = float(w.group(1)) * (1000 if w.group(2).lower() == "kg" else 1)
            continue
        c = re.match(r"^(\d+)\s*(개|팩|봉|박스|세트|통)$", seg)
        if c:
            mult *= int(c.group(1))
    return round(grams * mult)


COUNTABLE = {"구", "알", "매", "장", "캔", "병", "롤", "포"}   # 낱개 가격이 더 와닿는 단위


PER_WORD = {"매": "장당", "장": "장당", "캔": "캔당", "병": "병당", "롤": "롤당", "팩": "팩당", "포": "포당"}


def build(item, meta):
    name = item["name"] or meta.get("title") or "오늘의 할인 상품"
    s = {"name": name, "link": item["link"], "disc": item["disc"], "sale": item["sale"] or 0, "orig": item["orig"] or 0}
    s["display"] = auto_display(name)
    s["short"] = guess_short(name)
    s["qty"], s["unit"] = guess_qty(name)
    s["pct"] = item.get("pct") or (math.floor((1 - s["sale"] / s["orig"]) * 100) if s["orig"] > s["sale"] > 0 else 0)
    s["per"] = round(s["sale"] / s["qty"]) if s["qty"] > 1 and s["sale"] else 0
    s["per_word"] = PER_WORD.get(s["unit"], "개당")
    bundle = bool(re.search(r"\s\+\s", name))   # "A + B" 묶음은 단위 가격을 계산하면 틀리기 쉬워서 뺀다
    s["bundle"] = bundle
    if bundle:
        s["qty"], s["per"] = 1, 0
    s["grams"] = 0 if bundle else guess_grams(name)
    s["per100"] = int(s["sale"] / s["grams"] * 100 + 0.5) if s["grams"] >= 200 and s["sale"] else 0   # 토스와 같은 반올림
    if s["per100"] and s["unit"] not in COUNTABLE:   # 고기·과일처럼 무게로 파는 건 100g 가격으로 보여 준다
        s["per"] = 0
    s["rating"], s["reviews"], s["rank"] = meta.get("rating"), meta.get("reviews"), meta.get("rank", "")
    s["image"] = meta.get("image", "")
    s["hook"], s["shots"] = item.get("hook", ""), item.get("shots", [])
    return s


ONE = {"개": "한 개", "구": "한 알", "알": "한 알", "장": "한 장", "매": "한 장", "캔": "한 캔",
       "병": "한 병", "롤": "한 롤", "팩": "한 팩", "포": "한 포"}


def pick(options, key):
    """같은 상품이면 늘 같은 문장, 상품마다 다른 문장 (무작위 대신 링크로 고른다)."""
    return options[sum(map(ord, key)) % len(options)]


EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")


def no_emoji(text):
    return re.sub(r"\s{2,}", " ", EMOJI_RE.sub("", text)).strip()


# 상품 종류별 첫 줄(상황)과 쓰는 때. 첫 줄에는 상품 이름을 넣지 않는다 (2026-10-27 레퍼런스: 쿠파스 자동화 7원칙).
# 누구나 공감하는 상황만 쓰고, 써 본 척하는 문장은 넣지 않는다.
CATEGORIES = [
    ("고기", r"삼겹|목살|한우|돼지|소고기|갈비|등심|닭|오리|양고기|우삼겹|차돌",
     ["오늘 저녁 메뉴 고민 끝남", "집에서 고기 굽는 날임", "주말 캠핑 고기 아직 안 샀으면 이거 봐봐"],
     "굽기만 하면 바로 한 끼"),
    ("음료", r"생수|먹는샘물|탄산|콜라|사이다|주스|차,|수염차|보리차|커피|우유|두유|음료",
     ["물 떨어질 때마다 마트 가는 거 귀찮음", "무거운 거 들고 오기 싫은 사람 손", "집에 음료 쟁여두는 타입이면 봐봐"],
     "박스째 쟁여두면 한동안 걱정 없음"),
    ("계란", r"계란|달걀|메추리알",
     ["계란 진짜 금방 떨어짐", "계란 한 판 사면 일주일도 못 감"],
     "아침마다 계란 프라이 해도 넉넉함"),
    ("반찬", r"반찬|장조림|김치|만두|국,|찌개|밀키트|즉석|볶음밥|돈까스|떡볶이|어묵",
     ["퇴근하고 밥 차리기 싫은 날", "반찬 하기 귀찮은 날 있잖음", "냉동실에 하나 있으면 든든함"],
     "밥만 있으면 한 끼 해결"),
    ("과일", r"감귤|귤|사과|배,|복숭아|포도|딸기|바나나|키위|망고|토마토|과일",
     ["요즘 과일값 생각하면 이건 봐야 됨", "후식 없으면 허전한 사람 손"],
     "식후에 하나씩 까먹기 좋음"),
    ("수납", r"수납|정리함|리빙박스|선반|행거|바구니|보관함",
     ["계절 바뀔 때마다 이불 둘 데 없음", "옷장 정리하다 포기한 적 있으면"],
     "계절 지난 옷이랑 이불 넣어두기 좋음"),
    ("침구", r"토퍼|이불|매트|베개|담요|전기요|패드",
     ["점점 추워짐", "이불 밖은 위험한 계절 옴"],
     "바닥 차가워지는 밤에 딱임"),
    ("생필품", r"물티슈|휴지|화장지|세제|샴푸|린스|바디워시|칫솔|치약|키친타월|섬유유연제|캡슐",
     ["생필품은 꼭 급할 때 떨어짐", "어차피 계속 쓰는 거라 쌀 때 사두는 게 이득임"],
     "어차피 매일 쓰는 거임"),
]
DEFAULT_CAT = ("기타", "", ["이건 쌀 때 사두는 게 맞음", "생활비 아끼는 중이면 이거 봐봐"], "")


def category(name):
    for cat in CATEGORIES:
        if re.search(cat[1], name):
            return cat
    return DEFAULT_CAT


# 상품 해시태그 (2026-10-28 사용자 요청: #광고만 있으면 아까우니 상품 태그도 같이). 맨 끝 줄에 '#광고 #상품 #종류 #핫딜'.
TAGS = {"고기": ["고기", "집밥"], "음료": ["음료"], "계란": ["계란"], "반찬": ["반찬", "자취요리"], "과일": ["과일"],
        "수납": ["수납정리"], "침구": ["침구"], "생필품": ["생필품"]}


def tag_line(products):
    tags = ["광고"]
    for p in products:
        tags += [re.sub(r"[^\w]", "", p["short"] or "")] + TAGS.get(category(p["name"])[0], [])
    tags.append("핫딜")
    seen = []
    for t in tags:
        if t and t not in seen:
            seen.append(t)
    return " ".join("#" + t for t in seen[:5])


def hook_lines(s):
    """본문. 스레드체(음슴체: ~임, ~됨, ~함 + ;; ㄷㄷ), 이모지 없음, 사실만 쓴다.
    1줄: 상황(상품 이름 없음) 또는 사용자 한마디 / 2줄: 이름 + 단가 충격 / 빈 줄 / 쓰는 때 / 가격·할인 / 리뷰·순위"""
    short = s["short"] or "이거"
    _, _, situations, use = category(s["name"])
    if s["hook"]:   # 직접 쓴 한마디는 상황 줄만 바꾸고 나머지는 그대로 둔다
        lines = [no_emoji(x) for x in s["hook"].split("/") if no_emoji(x)]
    else:
        lines = [pick(situations, s["link"])]
    weight = "" if s.get("bundle") else next((x.strip() for x in s["name"].split(",") if re.match(r"^\d+(?:\.\d+)?\s*(kg|g)$", x.strip(), re.I)), "")
    shown_pct = False
    if s.get("per100") and not s["per"]:
        lines.append(pick([f"{short} 100g에 {s['per100'] // 100 * 100:,}원대 실화냐;;", f"{short} 100g에 {fmt(s['per100'])}원꼴임ㄷㄷ"], s["link"]))
    elif s["per"]:
        lines.append(f"{short} {ONE.get(s['unit'], '한 개')}에 {fmt(s['per'])}원꼴임ㄷㄷ")
    elif s["pct"] >= 50:
        lines.append(f"{short} {s['pct']}% 할인 실화냐;;")
        shown_pct = True
    else:
        lines.append(f"{short} {weight + ' ' if weight else ''}{fmt(s['sale'])}원임")
    lines.append("")
    if use:
        lines.append(use)
    amount = f"{s['qty']}{s['unit']}에 " if s["qty"] > 1 else (f"{weight} " if weight else "")
    if s["orig"] > s["sale"] and shown_pct:
        lines.append(f"{amount}{fmt(s['sale'])}원, 정가 {fmt(s['orig'])}원임")
    elif s["orig"] > s["sale"]:
        lines.append(f"{amount}{fmt(s['sale'])}원, 정가 {fmt(s['orig'])}원에서 {s['pct']}% 할인임")
    elif shown_pct:
        lines.append(f"{amount}{fmt(s['sale'])}원임")
    else:
        lines.append(f"{amount}{fmt(s['sale'])}원" + (f", {s['pct']}% 할인임" if s["pct"] else "임"))
    trust = [x for x in [s.get("rank", ""), f"리뷰 {s['reviews']:,}개 평점 {s['rating']:.1f}" if s.get("reviews") and s["reviews"] >= 100 and s.get("rating") else ""] if x]
    if trust:   # 순위·리뷰가 없으면 줄을 비운다 (급함은 단점 줄이 맡는다)
        lines.append(" · ".join(trust))
    return lines


def item_line(s):
    return f"{s['name']} {fmt(s['sale'])}원\n{s['link']}"


BANNED = ["강추", "꿀템", "삶의 질", "삶의질", "인생템", "완벽", "최고", "무조건", "합니다", "입니다", "습니다"]
MAX_BODY = 300   # 길면 안 읽는다 (레퍼런스 프롬프트 규칙)


def downside(s):
    """단점 1개. 상품명에 있는 사실(무게·수량·크기·사이즈)에서만 만든다. 모르면 선착순 사실로."""
    name, cat = s["name"], category(s["name"])[0]
    liters = re.search(r"(\d+)\s*L\b", name)
    if cat in ("고기", "반찬") and s.get("grams", 0) >= 1000:
        return "양 많아서 혼자면 소분해서 얼려야 됨"
    if cat == "음료" and s["qty"] >= 6:
        return "한 번에 와서 둘 자리는 있어야 됨"
    if cat == "계란" and s["qty"] >= 30:
        return "양 많아서 빨리 먹을 집 아니면 좀 버거움"
    if cat == "수납" and liters and int(liters.group(1)) >= 100:
        return f"{liters.group(1)}L라 생각보다 큼, 둘 자리 먼저 재 봐야 됨"
    if cat == "침구" and re.search(r"\bSS\b|\bS\b|슈퍼싱글|싱글", name):
        return "SS 사이즈라 혼자 쓰는 용임" if "SS" in name or "슈퍼싱글" in name else "싱글 사이즈라 혼자 쓰는 용임"
    if cat == "과일" and s.get("grams", 0) >= 3000:
        return "양 많아서 빨리 먹어야 됨"
    return "선착순 특가라 금방 끝날 수 있는 게 단점임"


def lint(main):
    """금지어·길이 검사. 문제가 있으면 초안 요약에 적는다."""
    issues = [f"금지어 `{w}`" for w in BANNED if w in main]
    if len(main) > MAX_BODY:
        issues.append(f"본문 {len(main)}자 ({MAX_BODY}자 넘음)")
    return issues


def single_post(s):
    lines = hook_lines(s)
    lines += [downside(s), "", "링크는 댓글에 둠"]
    main = "\n".join(lines + [tag_line([s])])   # 광고 표시는 본문 맨 끝 해시태그 (2026-10-28 사용자 결정)
    reply = f"{s['disc']}\n\n{item_line(s)}"
    return main, reply


def roundup_post(products):
    n = len(products)
    best = max((p["pct"] for p in products), default=0)
    custom = next((p["hook"] for p in products if p["hook"]), "")   # 모음 글은 처음 나온 한마디를 머리말로
    head = [no_emoji(x) for x in custom.split("/") if no_emoji(x)] if custom else [f"오늘 토스 핫딜 BEST {n} 모아봄"]
    lines = head + [""]
    if best:
        lines.append(f"최대 {best}% 할인까지 있음ㄷㄷ")
    for p in products:
        lines.append(f"· {p['short']} {fmt(p['sale'])}원" + (f" ({p['pct']}%↓)" if p["pct"] else ""))
    lines += ["", "링크는 댓글에 둠", tag_line(products)]
    reply = products[0]["disc"] + "\n\n" + "\n\n".join(item_line(p) for p in products)
    return "\n".join(lines), reply


# ---------- 4:5 이미지 카드 (캡처가 없을 때 대체용) ----------
BG = (197, 229, 232)   # 카드 배경 #C5E5E8
Y, INK, SALE, WHITE, GREY = (255, 216, 61), (23, 25, 30), (216, 38, 28), (255, 255, 255), (90, 82, 67)


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def disp(size):
    return font("SUIT-Heavy.ttf", size)


def body(size, bold=True):
    return font("SUIT-ExtraBold.ttf" if bold else "SUIT-Bold.ttf", size)


def fit(text, maker, max_w, start, minimum):
    for size in range(start, minimum - 1, -2):
        f = maker(size)
        if f.getlength(text) <= max_w:
            return f, text
    f = maker(minimum)
    while text and f.getlength(text + "…") > max_w:
        text = text[:-1]
    return f, text + "…"


def load_photo(url):
    if not url:
        return None
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read()
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as e:
        print("상품 사진을 못 받았어요:", e)
        return None


def cover(img, size):
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side))
    return img.resize((size, size), Image.LANCZOS)


def render_card(s, photo):
    W, H = 1080, 1350
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    # 계정 이름 + 날짜
    f = disp(58)
    bw = f.getlength("오늘의 할인") + 64
    d.rounded_rectangle([60, 50, 60 + bw, 150], radius=50, fill=INK)
    d.text((92, 100), "오늘의 할인", font=f, fill=Y, anchor="lm")
    now = dt.datetime.now(KST)
    d.text((W - 60, 100), f"{now.month}월 {now.day}일", font=body(40, False), fill=INK, anchor="rm")

    # 상품 사진
    size, x, y = 640, (W - 640) // 2, 190
    d.rounded_rectangle([x - 10, y - 10, x + size + 10, y + size + 10], radius=48, fill=WHITE)
    if photo:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, size, size], radius=40, fill=255)
        im.paste(cover(photo, size), (x, y), mask)
    else:
        f, t = fit(s["short"] or "오늘의 할인", disp, size - 80, 120, 50)
        d.text((W // 2, y + size // 2), t, font=f, fill=INK, anchor="mm")

    # 할인 뱃지
    if s["pct"]:
        b = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
        bd = ImageDraw.Draw(b)
        bd.ellipse([10, 10, 250, 250], fill=SALE, outline=WHITE, width=7)
        bd.text((130, 118), f"{s['pct']}%", font=disp(80), fill=WHITE, anchor="mm")
        bd.text((130, 184), "할인", font=disp(40), fill=WHITE, anchor="mm")
        b = b.rotate(12, resample=Image.BICUBIC, expand=False)
        im.paste(b, (x + size - 40 - 130, y + 60 - 130), b)

    # 상품명 (1줄 상품, 2줄 규격)
    yy = 905
    if s["display"]:
        f, t = fit(s["display"][0], lambda z: body(z), W - 140, 54, 36)
        d.text((W // 2, yy), t, font=f, fill=INK, anchor="mm")
        if len(s["display"]) > 1:
            f, t = fit(s["display"][1], lambda z: body(z, False), W - 160, 42, 30)
            d.text((W // 2, yy + 60), t, font=f, fill=GREY, anchor="mm")

    # 가격
    if s["orig"] > s["sale"] > 0:
        f = disp(64)
        t = f"{fmt(s['orig'])}원"
        tw = f.getlength(t)
        d.text((W // 2, 1040), t, font=f, fill=GREY, anchor="mm")
        d.line([(W / 2 - tw / 2 - 10, 1042), (W / 2 + tw / 2 + 10, 1038)], fill=SALE, width=9)
    if s["sale"]:
        d.text((W // 2, 1132), f"{fmt(s['sale'])}원", font=disp(136), fill=SALE, anchor="mm")
    if s["per"]:
        f = disp(54)
        t = f"{s['per_word']} {fmt(s['per'])}원 · {s['qty']}{s['unit']}"
        tw = f.getlength(t) + 72
        d.rounded_rectangle([W / 2 - tw / 2, 1232, W / 2 + tw / 2, 1324], radius=46, fill=INK)
        d.text((W // 2, 1280), t, font=f, fill=Y, anchor="mm")
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


# ---------- 시간대 ----------
SLOT_RE = re.compile(r"^(?:예약|초안|실패 예약)\s+(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})")


def taken_slots(issues, now):
    taken = set()
    for i in issues:
        m = SLOT_RE.match(i["title"].strip())
        if m:
            mo, d, h, mi = map(int, m.groups())
            taken.add((mo, d, h, mi))
    return taken


def next_slots(n, taken, now):
    out, day = [], now.date()
    while len(out) < n:
        for slot in SLOTS:
            h, mi = map(int, slot.split(":"))
            t = dt.datetime(day.year, day.month, day.day, h, mi, tzinfo=KST)
            if t < now + MIN_LEAD or (t.month, t.day, h, mi) in taken:
                continue
            out.append(t)
            taken.add((t.month, t.day, h, mi))
            if len(out) == n:
                break
        day += dt.timedelta(days=1)
    return out


# ---------- 저장소 ----------
def save_card(png, path):
    res = gh("PUT", f"/repos/{REPO}/contents/{path}", {
        "message": f"Add card {os.path.basename(path)}",
        "content": base64.b64encode(png).decode(),
    })
    return f"https://raw.githubusercontent.com/{REPO}/{res['commit']['sha']}/{path}"


def trim_screenshot(data):
    """토스 앱 상품 화면 캡처(세로로 긴 폰 화면)에서 위쪽 버튼 줄과 아래쪽 적립·뽑기·구매 버튼 영역을 잘라 낸다."""
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        raise PostError("캡처 이미지를 열 수 없어요. PNG나 JPG로 다시 붙여 주세요.")
    w, h = im.size
    if h / w >= 1.8:   # 폰 전체 화면 캡처일 때만 (이미 잘린 이미지는 그대로)
        im = im.crop((0, round(h * 0.06), w, round(h * 0.805)))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=92)
    return out.getvalue()


def save_shot(url, path_base):
    data, ctype = download(url)
    if not any(t in ctype for t in ("png", "jpeg", "jpg")):
        raise PostError(f"캡처는 PNG나 JPG만 쓸 수 있어요 (받은 형식: {ctype or '알 수 없음'}).")
    return save_card(trim_screenshot(data), f"{path_base}.jpg")


def images_for(s, number, idx, now):
    """상품 이미지: 붙여 준 캡처가 있으면 캡처, 없으면 디자인 카드."""
    if s["shots"]:
        return [save_shot(u, f"images/shots/{now:%Y%m%d}-b{number}-{idx}-{j}") for j, u in enumerate(s["shots"], 1)]
    card = render_card(s, load_photo(s["image"]))
    return [save_card(card, f"images/cards/{now:%Y%m%d}-b{number}-{idx}.png")]


def draft_body(main, urls, reply, number):
    pics = "\n".join(f"![이미지]({u})" for u in urls)
    return f"{main}\n\n{pics}\n\n{REPLY_MARK}\n{reply}\n\n{BATCH_MARK.format(number)}"


def open_issues():
    return [i for i in gh("GET", f"/repos/{REPO}/issues?state=open&per_page=100") if "pull_request" not in i]


def process_batch(issue):
    number = issue["number"]
    items = parse_batch(issue.get("body"))
    if not items:
        comment(number, "❌ 공유 문구에서 링크(https://…)를 찾지 못했어요. 토스 쉐어링크 공유 문구를 그대로 붙여 주세요.")
        return
    missing = [it["name"] or it["link"] for it in items if not it["sale"]]
    if missing:
        comment(number, "❌ 가격이 없는 상품이 있어요. 링크 바로 아래 줄에 `할인가/정가`를 적어 주세요 (예: `15900/26900`).\n\n"
                + "\n".join(f"- {m}" for m in missing) + "\n\n본문을 고쳐 저장하면 다시 처리해요.")
        return

    now = dt.datetime.now(KST)
    direct = "바로" in issue["title"]
    separate = "따로" in issue["title"] or len(items) == 1
    prefix = "예약" if direct else "초안"
    products = [build(it, fetch_meta(it["link"])) for it in items]
    groups = [[p] for p in products] if separate else [products]
    slots = next_slots(len(groups), taken_slots(open_issues(), now), now)
    rows = []
    for gi, (group, when) in enumerate(zip(groups, slots), 1):
        urls = []
        for pi, p in enumerate(group, 1):
            urls += images_for(p, number, f"{gi}-{pi}", now)
        if len(group) == 1:
            main, reply = single_post(group[0])
            label = group[0]["short"]
        else:
            main, reply = roundup_post(group)
            label = f"핫딜 BEST {len(group)}"
        if len(main) > 500:
            raise PostError(f"본문이 {len(main)}자라 스레드 제한(500자)을 넘어요. 상품 수를 줄여 주세요.")
        title = f"{prefix} {when.month}/{when.day} {when:%H:%M} {label}".strip()
        new = gh("POST", f"/repos/{REPO}/issues", {"title": title, "body": draft_body(main, urls, reply, number)})
        names = ", ".join(p["short"] for p in group)
        shots = "캡처" if all(p["shots"] for p in group) else ("카드" if not any(p["shots"] for p in group) else "캡처+카드")
        warn = ", ".join(lint(main))
        rows.append(f"| {when.month}/{when.day} {when:%H:%M} | {names} | {shots} | #{new['number']}{' ⚠️ ' + warn if warn else ''} |")
        print("만듦:", title)

    gh("PATCH", f"/repos/{REPO}/issues/{number}", {"title": f"{DONE_PREFIX} {issue['title'][2:].strip()}".strip()})
    head = "✅ 바로 예약했어요." if direct else "✅ 초안을 만들었어요. 확인한 뒤 이 이슈에 **`승인`** 댓글을 달면 모두 예약으로 바뀌어요."
    comment(number, head + "\n\n| 게시 시각 | 상품 | 이미지 | 초안 |\n|---|---|---|---|\n" + "\n".join(rows)
            + "\n\n- 고칠 게 있으면 각 초안 이슈의 본문을 직접 고치면 돼요.\n- 빼고 싶은 상품은 그 초안 이슈를 닫으면 돼요.")
    if direct:
        gh("PATCH", f"/repos/{REPO}/issues/{number}", {"state": "closed", "state_reason": "completed"})


def approve(issue):
    number = issue["number"]
    mark = BATCH_MARK.format(number)
    changed = []
    for i in open_issues():
        if i["title"].startswith("초안") and mark in (i.get("body") or ""):
            new_title = "예약" + i["title"][2:]
            gh("PATCH", f"/repos/{REPO}/issues/{i['number']}", {"title": new_title})
            changed.append(f"- #{i['number']} {new_title}")
    if not changed:
        comment(number, "승인할 초안이 없어요. 이미 승인했거나 초안을 모두 닫았어요.")
        return
    comment(number, "✅ 승인했어요. 정한 시각이 지나면 차례로 올라가요.\n\n" + "\n".join(changed))
    gh("PATCH", f"/repos/{REPO}/issues/{number}", {"state": "closed", "state_reason": "completed"})


def main():
    event = os.environ.get("EVENT_NAME", "")
    number = int(os.environ.get("ISSUE_NUMBER") or 0)
    issue = gh("GET", f"/repos/{REPO}/issues/{number}")
    title = issue["title"].strip()
    try:
        if event == "issue_comment":
            if os.environ.get("COMMENT_BODY", "").strip() in ("승인", "승인!", "ㅇㅋ 승인") and title.startswith("상품"):
                approve(issue)
        elif title.startswith("상품") and not title.startswith(DONE_PREFIX):
            process_batch(issue)
    except PostError as e:
        comment(number, f"❌ 처리 중 문제가 생겼어요.\n\n```\n{e}\n```")
        raise


if __name__ == "__main__":
    main()
