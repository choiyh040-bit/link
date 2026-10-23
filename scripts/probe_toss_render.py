#!/usr/bin/env python3
"""브라우저로 토스쇼핑 링크를 열어 화면 글자와 백그라운드 데이터 요청에서 가격을 찾는다."""
import json
import re
import sys
from playwright.sync_api import sync_playwright

url = sys.argv[1]
hits = []


def on_response(resp):
    ct = resp.headers.get("content-type", "")
    if "json" not in ct:
        return
    try:
        body = resp.text()
    except Exception:
        return
    keys = re.findall(r'"([A-Za-z]*(?:[Pp]rice|[Dd]iscount)[A-Za-z]*)"\s*:\s*"?(\d{3,8})', body)
    hits.append((resp.status, resp.url.split("?")[0], len(body), keys[:12]))


with sync_playwright() as p:
    b = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
    mobile = len(sys.argv) > 2 and sys.argv[2] == "mobile"
    dev = p.devices["iPhone 13"] if mobile else {"viewport": {"width": 1280, "height": 900}, "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"}
    ctx = b.new_context(**dev, locale="ko-KR", timezone_id="Asia/Seoul")
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    pg = ctx.new_page()
    pg.on("response", on_response)
    pg.goto(url, wait_until="domcontentloaded", timeout=45000)
    for _ in range(10):
        pg.wait_for_timeout(1500)
        if re.search(r"\d{1,3}(?:,\d{3})+\s*원", pg.inner_text("body") or ""):
            break
    text = pg.inner_text("body") or ""
    print("현재 주소:", pg.url)
    print("HTML 길이:", len(pg.content()))
    try:
        pg.screenshot(path="toss-page.png", full_page=False, timeout=8000)
    except Exception as e:
        print("스크린샷 실패:", str(e)[:80])
    b.close()

print("화면 글자 수:", len(text))
print("'원' 표기:", re.findall(r"\d{1,3}(?:,\d{3})+\s*원", text)[:15])
print("할인율 표기:", re.findall(r"\d{1,2}\s*%", text)[:10])
print("앞부분:", re.sub(r"\s+", " ", text)[:500])
print("JSON 응답 수:", len(hits))
for h in hits:
    print("  ", h)
