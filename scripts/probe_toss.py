#!/usr/bin/env python3
"""토스쇼핑 공유 링크에서 상품 정보(제목, 이미지, 가격)를 읽을 수 있는지 시험한다."""
import html
import re
import sys
import urllib.request

url = sys.argv[1]
req = urllib.request.Request(url, headers={
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept-Language": "ko-KR,ko;q=0.9",
})
with urllib.request.urlopen(req, timeout=30) as r:
    print("최종 주소:", r.geturl())
    print("상태:", r.status, r.headers.get("Content-Type"))
    body = r.read().decode("utf-8", errors="replace")
print("본문 길이:", len(body))
for prop in ["og:title", "og:description", "og:image", "product:price:amount", "twitter:title", "twitter:image"]:
    m = re.search(r'<meta[^>]+(?:property|name)="%s"[^>]+content="([^"]*)"' % re.escape(prop), body) or \
        re.search(r'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="%s"' % re.escape(prop), body)
    print(f"{prop}:", html.unescape(m.group(1)) if m else "-")
m = re.search(r"<title>(.*?)</title>", body, re.S)
print("title:", html.unescape(m.group(1)).strip() if m else "-")
print("ld+json:", "있음" if "application/ld+json" in body else "없음")
print("__NEXT_DATA__:", "있음" if "__NEXT_DATA__" in body else "없음")
prices = re.findall(r'"(?:price|salePrice|discountedPrice|originalPrice|sellingPrice|listPrice)"\s*:\s*"?(\d{3,7})', body)
print("가격 후보:", prices[:12])
won = re.findall(r"(\d{1,3}(?:,\d{3})+)\s*원", html.unescape(re.sub(r"<[^>]+>", " ", body)))
print("'원' 표기 후보:", won[:12])
print("본문 앞부분:", re.sub(r"\s+", " ", body[:600]))
