#!/usr/bin/env python3
"""브라우저로 토스쇼핑 링크를 열어, 화면에 그려진 뒤의 가격 표기를 찾는다."""
import re
import sys
from playwright.sync_api import sync_playwright

url = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(**p.devices["iPhone 13"], locale="ko-KR")
    pg.goto(url, wait_until="networkidle", timeout=45000)
    pg.wait_for_timeout(3000)
    text = pg.inner_text("body")
    pg.screenshot(path="toss-page.png", full_page=False)
    b.close()
print("화면 글자 수:", len(text))
print("'원' 표기:", re.findall(r"\d{1,3}(?:,\d{3})+\s*원", text)[:15])
print("할인율 표기:", re.findall(r"\d{1,2}\s*%", text)[:10])
print("앞부분:", re.sub(r"\s+", " ", text)[:700])
