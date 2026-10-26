#!/usr/bin/env python3
"""상품 등록 이슈를 읽어 스레드 게시 초안 이슈를 만든다.

상품 등록 이슈
  제목: '상품'으로 시작 (예: 상품 10/23). '상품 바로예약'이면 승인 없이 바로 예약.
  본문: 토스 쉐어링크 공유 문구를 그대로 붙이고, 링크 바로 아래 줄에 가격을 적는다.
      ✱ 이 포스팅은 토스쇼핑 쉐어링크 활동의 일환으로, …
      양계장사람들 무항생제 계란, 대란, 60구, 1개
      https://toss.shopping/_m/D54kVLUt
      15900/26900          ← 할인가/정가 (정가 없으면 15900만)
  여러 상품을 이어서 붙여도 된다.

하는 일
  1. 링크에서 상품명·대표 사진·평점·리뷰 수·순위를 가져온다 (가격은 토스 웹에 없어서 사람이 적는다)
  2. 글과 4:5 이미지 카드를 만들고 카드를 images/cards/ 에 저장한다
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
from post_threads import KST, PostError, comment, gh, http  # noqa: E402

REPO = os.environ.get("GITHUB_REPOSITORY", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "assets", "fonts")

DISCLOSURE = "✱ 이 포스팅은 토스쇼핑 쉐어링크 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
SLOTS = ["08:30", "12:30", "20:30"]       # 하루 게시 시간대 (한국 시간)
MIN_LEAD = dt.timedelta(minutes=30)       # 지금부터 최소 이만큼 뒤 시간대부터
BATCH_MARK = "<!-- batch:{} -->"
DONE_PREFIX = "상품(처리됨)"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

URL_RE = re.compile(r"https?://(?:toss\.shopping|sharelink\.toss\.im|[\w.-]*toss\.im)/[^\s)\]]+")   # 토스 링크만 (다른 주소는 무시)
PRICE_RE = re.compile(r"^\s*(\d[\d,]*)\s*원?\s*(?:/\s*(\d[\d,]*)\s*원?)?\s*$")


def fmt(n):
    return f"{round(n):,}"


# ---------- 붙여 넣은 공유 문구 해석 ----------
def parse_batch(body):
    items, pending, last = [], {"name": "", "disc": "", "price": None}, None
    for raw in (body or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        url = URL_RE.search(line)
        price = PRICE_RE.match(line)
        if url:
            last = {"name": pending["name"], "disc": pending["disc"] or DISCLOSURE,
                    "link": url.group(0), "sale": None, "orig": None}
            if pending["price"]:
                last["sale"], last["orig"] = pending["price"]
            items.append(last)
            pending = {"name": "", "disc": "", "price": None}
        elif price:
            nums = (int(price.group(1).replace(",", "")), int(price.group(2).replace(",", "")) if price.group(2) else None)
            if last and last["sale"] is None:
                last["sale"], last["orig"] = nums
            else:
                pending["price"] = nums
        elif line.startswith("✱") or "수수료" in line:
            pending["disc"] = line
        else:
            pending["name"] = line
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


# ---------- 상품 정보 정리 (도구 today-sale-maker.html 과 같은 규칙) ----------
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


PER_WORD = {"매": "장당", "장": "장당", "캔": "캔당", "병": "병당", "롤": "롤당", "팩": "팩당", "포": "포당"}


def build(item, meta):
    name = item["name"] or meta.get("title") or "오늘의 할인 상품"
    s = {"name": name, "link": item["link"], "disc": item["disc"], "sale": item["sale"] or 0, "orig": item["orig"] or 0}
    s["display"] = auto_display(name)
    s["short"] = guess_short(name)
    s["qty"], s["unit"] = guess_qty(name)
    s["pct"] = math.floor((1 - s["sale"] / s["orig"]) * 100) if s["orig"] > s["sale"] > 0 else 0
    s["per"] = round(s["sale"] / s["qty"]) if s["qty"] > 1 and s["sale"] else 0
    s["per_word"] = PER_WORD.get(s["unit"], "개당")
    s["rating"], s["reviews"], s["rank"] = meta.get("rating"), meta.get("reviews"), meta.get("rank", "")
    s["image"] = meta.get("image", "")
    return s


def post_text(s):
    if s["per"] and s["short"]:
        hook = f"{s['short']} 1{s['per_word'].replace('당', '')} {fmt(s['per'])}원?"
    elif s["pct"]:
        hook = f"{s['pct']}% 할인, {fmt(s['sale'])}원"
    else:
        hook = s["short"] or (s["display"][0] if s["display"] else "")
    d = s["display"]
    price = f"💰 {fmt(s['orig'])}원 → {fmt(s['sale'])}원" if s["orig"] > s["sale"] else f"💰 {fmt(s['sale'])}원"
    deal = " · ".join(x for x in [f"{s['pct']}% 할인" if s["pct"] else "", f"{s['per_word']} {fmt(s['per'])}원" if s["per"] else ""] if x)
    trust = " · ".join(x for x in [
        f"⭐ {s['rating']:.1f} (리뷰 {s['reviews']:,}개)" if s.get("rating") and s.get("reviews") else "",
        s["rank"]] if x)
    paras = [
        [s["disc"]],
        [hook],
        [f"📦 {d[0]}" if d else ""] + d[1:],
        [price, deal],
        [trust],
        [f"🔗 {s['link']}"],
    ]
    return "\n\n".join("\n".join(x for x in p if x) for p in paras if any(p))


# ---------- 4:5 이미지 카드 (도구의 drawStill과 같은 디자인) ----------
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
    d.rounded_rectangle([x + 14, y + 18, x + 14 + size, y + 18 + size], radius=40, fill=INK)
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
    prefix = "예약" if direct else "초안"
    slots = next_slots(len(items), taken_slots(open_issues(), now), now)
    rows = []
    for idx, (it, when) in enumerate(zip(items, slots), 1):
        meta = fetch_meta(it["link"])
        s = build(it, meta)
        card = render_card(s, load_photo(s["image"]))
        url = save_card(card, f"images/cards/{now:%Y%m%d}-b{number}-{idx}.png")
        title = f"{prefix} {when.month}/{when.day} {when:%H:%M} {s['short']}".strip()
        body_text = f"{post_text(s)}\n\n![카드]({url})\n\n{BATCH_MARK.format(number)}"
        new = gh("POST", f"/repos/{REPO}/issues", {"title": title, "body": body_text})
        rows.append(f"| {when.month}/{when.day} {when:%H:%M} | {s['short']} | {fmt(s['sale'])}원 | #{new['number']} |")
        print("만듦:", title)

    gh("PATCH", f"/repos/{REPO}/issues/{number}", {"title": f"{DONE_PREFIX} {issue['title'][2:].strip()}".strip()})
    head = "✅ 바로 예약했어요." if direct else "✅ 초안을 만들었어요. 확인한 뒤 이 이슈에 **`승인`** 댓글을 달면 모두 예약으로 바뀌어요."
    comment(number, head + "\n\n| 게시 시각 | 상품 | 가격 | 초안 |\n|---|---|---|---|\n" + "\n".join(rows)
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
