// 턱시도 코숏 3컷툰 초안: SVG로 그리고 Playwright로 PNG 저장
// 손글씨 글꼴(SDUnicefSunny.ttf)은 재배포 금지라 저장소에 없음. 같은 폴더에 두고 실행.
const { chromium } = require('playwright');
const fs = require('fs');
const FONT = 'file:///home/user/link/assets/fonts/';
const OUT = process.argv[2] || '.';

const INK = '#1d1d1f', WHITE = '#ffffff', PINK = '#ffb3c1', NOSE = '#f48aa0';

// 앉은 고양이. eyes: 'sleep' | 'wide' | 'sparkle'
function cat(cx, cy, s, eyes, opts = {}) {
  const g = [];
  g.push(`<g transform="translate(${cx},${cy}) scale(${s})">`);
  // 꼬리
  g.push(`<path d="M120 150 C210 140 220 40 170 20" stroke="${INK}" stroke-width="34" fill="none" stroke-linecap="round"/>`);
  // 몸
  g.push(`<ellipse cx="0" cy="110" rx="150" ry="125" fill="${INK}"/>`);
  // 가슴 흰 털(턱시도)
  g.push(`<path d="M-70 20 Q0 120 70 20 Q75 150 0 205 Q-75 150 -70 20Z" fill="${WHITE}"/>`);
  // 앞발
  if (opts.rightPawUp) {
    // 오른쪽 앞발은 들어 올렸으니 바닥엔 왼발만
    g.push(`<ellipse cx="-55" cy="222" rx="42" ry="26" fill="${WHITE}"/>`);
    g.push(`<path d="M-62 212v18M-48 212v18" stroke="#d9d9de" stroke-width="3"/>`);
    g.push(`<path d="M95 70 Q170 -20 230 -140" stroke="${INK}" stroke-width="44" stroke-linecap="round" fill="none"/>`);
    g.push(`<ellipse cx="236" cy="-152" rx="36" ry="28" fill="${WHITE}" transform="rotate(-50 236 -152)"/>`);
  } else {
    g.push(`<ellipse cx="-55" cy="222" rx="42" ry="26" fill="${WHITE}"/><ellipse cx="55" cy="222" rx="42" ry="26" fill="${WHITE}"/>`);
    g.push(`<path d="M-62 212v18M-48 212v18M48 212v18M62 212v18" stroke="#d9d9de" stroke-width="3"/>`);
  }
  // 귀
  g.push(`<path d="M-125 -95 L-110 -230 L-25 -150Z" fill="${INK}"/><path d="M125 -95 L110 -230 L25 -150Z" fill="${INK}"/>`);
  g.push(`<path d="M-108 -118 L-102 -195 L-50 -148Z" fill="${PINK}"/><path d="M108 -118 L102 -195 L50 -148Z" fill="${PINK}"/>`);
  if (opts.earsDown) { /* 기본 귀 그대로 */ }
  // 머리 (넓적하고 둥근 얼굴)
  g.push(`<ellipse cx="0" cy="-55" rx="178" ry="145" fill="${INK}"/>`);
  // 턱시도: 코 아래 흰 주둥이 + 턱
  g.push(`<ellipse cx="0" cy="12" rx="78" ry="52" fill="${WHITE}"/>`);
  // 볼 (크고 부드럽게)
  g.push(`<ellipse cx="-112" cy="0" rx="40" ry="24" fill="#f4a7b4" opacity=".85"/><ellipse cx="112" cy="0" rx="40" ry="24" fill="#f4a7b4" opacity=".85"/>`);
  // 눈
  if (eyes === 'sleep') {
    g.push(`<path d="M-92 -62 Q-62 -40 -32 -62" stroke="${WHITE}" stroke-width="9" fill="none" stroke-linecap="round"/>`);
    g.push(`<path d="M32 -62 Q62 -40 92 -62" stroke="${WHITE}" stroke-width="9" fill="none" stroke-linecap="round"/>`);
  } else if (eyes === 'side') {
    for (const x of [-62, 62]) {
      g.push(`<ellipse cx="${x}" cy="-58" rx="33" ry="30" fill="#74c493"/>`);
      g.push(`<ellipse cx="${x + 14}" cy="-56" rx="11" ry="22" fill="#1f2430"/>`);
      g.push(`<path d="M${x - 36} -66 Q${x} -78 ${x + 36} -66 L${x + 36} -92 L${x - 36} -92Z" fill="${INK}"/>`);
      g.push(`<circle cx="${x + 20}" cy="-62" r="5" fill="${WHITE}"/>`);
    }
  } else {
    const big = eyes === 'sparkle';
    for (const x of [-62, 62]) {
      g.push(`<ellipse cx="${x}" cy="-62" rx="${big ? 38 : 33}" ry="${big ? 42 : 37}" fill="#74c493"/>`);
      g.push(`<ellipse cx="${x}" cy="-60" rx="${big ? 22 : 14}" ry="${big ? 34 : 28}" fill="#1f2430"/>`);
      g.push(`<circle cx="${x + 9}" cy="-80" r="${big ? 12 : 10}" fill="${WHITE}"/><circle cx="${x - 9}" cy="-44" r="${big ? 7 : 5}" fill="${WHITE}"/>`);
      if (big) g.push(`<path d="M${x - 8} -70 l3 8 8 3 -8 3 -3 8 -3 -8 -8 -3 8 -3Z" fill="${WHITE}"/>`);
    }
  }
  // 코·입 (ㅅ자)
  g.push(`<path d="M-13 -8 L13 -8 L0 7Z" fill="#ee9aa6"/>`);
  g.push(`<path d="M0 7 L0 14 M0 14 Q-12 30 -26 34 M0 14 Q12 30 26 34" stroke="#3b4252" stroke-width="5" fill="none" stroke-linecap="round"/>`);
  if (opts.mouthOpen) g.push(`<ellipse cx="0" cy="30" rx="8" ry="6" fill="#ee9aa6"/>`);
  // 수염 (얇게)
  g.push(`<path d="M-150 2 L-215 -12 M-150 16 L-218 22 M150 2 L215 -12 M150 16 L218 22" stroke="#c9ccd3" stroke-width="4" stroke-linecap="round"/>`);
  g.push(`</g>`);
  return g.join('');
}

function pouch(x, y, r) {
  // 츄르 스틱: 길쭉한 빨간 파우치, 위쪽 뜯는 부분
  return `<g transform="translate(${x},${y}) rotate(${r})">
    <rect x="-34" y="-120" width="68" height="240" rx="12" fill="#e8343a"/>
    <path d="M-34 -96 h68" stroke="#fff" stroke-width="4" stroke-dasharray="7 6"/>
    <rect x="-34" y="-120" width="68" height="22" rx="8" fill="#c4242a"/>
    <rect x="-24" y="-60" width="48" height="120" rx="10" fill="#fff"/>
    <text x="0" y="-18" font-family="SUIT" font-weight="900" font-size="26" fill="#e8343a" text-anchor="middle">츄</text>
    <text x="0" y="16" font-family="SUIT" font-weight="900" font-size="26" fill="#e8343a" text-anchor="middle">르</text>
    <path d="M-12 40 q12 -14 24 0 q-12 14 -24 0" fill="#ffb3c1"/>
  </g>`;
}

function hand(x, y) {
  return `<g transform="translate(${x},${y})"><path d="M0 0 h220 v70 h-220z" fill="#ffd9c2"/>
    <rect x="-40" y="-8" width="60" height="86" rx="30" fill="#ffd9c2"/></g>`;
}

const b64 = f => fs.readFileSync('/home/user/link/assets/fonts/' + f).toString('base64');
const css = `@font-face{font-family:SUIT;src:url(data:font/ttf;base64,${b64('SUIT-Heavy.ttf')});font-weight:900}
@font-face{font-family:SUIT;src:url(data:font/ttf;base64,${b64('SUIT-ExtraBold.ttf')});font-weight:800}`;

function panel(n, bg, body, caption) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">
  <style>${css}</style>
  <rect width="1080" height="1080" fill="${bg}"/>
  ${body}
  <rect x="60" y="900" width="960" height="120" rx="30" fill="${INK}"/>
  <text x="540" y="980" font-family="SUIT" font-weight="800" font-size="56" fill="#ffd83d" text-anchor="middle">${caption}</text>
  </svg>`;
}

function tag(x, y, r, name) {
  return `<g transform="translate(${x},${y}) rotate(${r})">
    <path d="M0 -95 L0 -60" stroke="#c9a46b" stroke-width="5"/>
    <rect x="-95" y="-60" width="190" height="110" rx="22" fill="#fff" stroke="${INK}" stroke-width="7"/>
    <circle cx="0" cy="-40" r="9" fill="#ffd9c2" stroke="${INK}" stroke-width="4"/>
    <text x="0" y="22" font-family="SUIT" font-weight="900" font-size="54" fill="${INK}" text-anchor="middle">${name}</text>
  </g>`;
}

function laptop(x, y) {
  return `<g transform="translate(${x},${y})">
    <rect x="-230" y="-250" width="460" height="260" rx="18" fill="#8e96a3"/>
    <rect x="-205" y="-228" width="410" height="215" rx="8" fill="#cfe3f7"/>
    <path d="M-180 -190 h200 M-180 -160 h300 M-180 -130 h240 M-180 -100 h280" stroke="#9fb6cf" stroke-width="12" stroke-linecap="round"/>
    <path d="M-280 10 h560 l-40 50 h-480Z" fill="#6f7784"/>
  </g>`;
}

// 비뚤빼뚤 손글씨 흉내: 글자마다 기울기·높이·크기를 조금씩 다르게
function scribble(text, cx, y) {
  const rot = [-5, 4, -2, 5, -4, 3, -6, 4], dy = [3, -5, 4, -2, 6, -4, 1, -3], fs = [62, 56, 66, 58, 64, 54, 60, 63];
  const chars = [...text], gap = 72;
  const xs = []; let x = 0;
  for (const c of chars) { xs.push(x); x += c === ' ' ? 26 : gap; }
  const shift = cx - (xs[xs.length - 1]) / 2;
  return chars.map((c, i) => c === ' ' ? '' :
    `<text x="${shift + xs[i]}" y="${y + dy[i % 8]}" font-family="Hand" font-size="${fs[i % 8] + 30}"
      fill="#5ef2ff" stroke="#5ef2ff" stroke-width="4" stroke-linejoin="round" text-anchor="middle"
      transform="rotate(${rot[i % 8]} ${shift + xs[i]} ${y + dy[i % 8]})">${c}</text>`).join('');
}

function digitalHouse(x, y) {
  // 반짝이는 픽셀 상자 집 (앞면만, 고양이 몸을 가림)
  return `<g transform="translate(${x},${y})">
    <rect x="-250" y="-40" width="500" height="300" rx="24" fill="#2c2f6b"/>
    <rect x="-250" y="-40" width="500" height="300" rx="24" fill="none" stroke="#5ef2ff" stroke-width="10"/>
    <g fill="#5ef2ff" opacity=".85">
      <rect x="-215" y="10" width="26" height="26"/><rect x="-180" y="40" width="26" height="26"/>
      <rect x="170" y="10" width="26" height="26"/><rect x="200" y="220" width="26" height="26"/>
      <rect x="-200" y="190" width="26" height="26"/><rect x="150" y="190" width="26" height="26"/>
    </g>
    ${scribble('디지털 숨숨집', 0, 150)}
  </g>`;
}

function bubble(x, y, w, text, tailX) {
  return `<g><rect x="${x}" y="${y}" width="${w}" height="120" rx="60" fill="#fff" stroke="${INK}" stroke-width="7"/>
   <path d="M${tailX} ${y + 116} l30 54 l26 -56" fill="#fff" stroke="${INK}" stroke-width="7" stroke-linejoin="round"/>
   <rect x="${tailX - 4}" y="${y + 106}" width="66" height="16" fill="#fff"/>
   <text x="${x + w / 2}" y="${y + 78}" font-family="SUIT" font-weight="900" font-size="50" fill="${INK}" text-anchor="middle">${text}</text></g>`;
}


function chatWin(inner, placeholder) {
  return `<g>
    <rect x="80" y="60" width="920" height="800" rx="36" fill="#fff" stroke="${INK}" stroke-width="7"/>
    <path d="M80 150 h920" stroke="#e3e5ea" stroke-width="5"/>
    <circle cx="130" cy="105" r="13" fill="#ff8b7a"/><circle cx="170" cy="105" r="13" fill="#ffd36b"/><circle cx="210" cy="105" r="13" fill="#7ad48b"/>
    <text x="540" y="118" font-family="SUIT" font-weight="900" font-size="40" fill="#8a8f98" text-anchor="middle">클로드</text>
    ${inner}
    <rect x="130" y="760" width="820" height="72" rx="36" fill="#f2f3f6"/>
    <text x="175" y="808" font-family="SUIT" font-weight="800" font-size="34" fill="#a3a8b0">${placeholder}</text>
  </g>`;
}
function tears(cx, cy, s) {
  return `<g transform="translate(${cx},${cy}) scale(${s})" fill="#7cc8ff" stroke="#3b8fd6" stroke-width="4">
    <path d="M-70 -20 q-14 40 0 70 q14 -30 0 -70Z"/><path d="M70 -20 q-14 40 0 70 q14 -30 0 -70Z"/>
    <path d="M-80 70 q-10 30 0 50 q10 -20 0 -50Z"/><path d="M80 70 q-10 30 0 50 q10 -20 0 -50Z"/></g>`;
}
function clock(x, y) {
  return `<g transform="translate(${x},${y})"><circle r="70" fill="#fff" stroke="${INK}" stroke-width="7"/>
    <path d="M0 0 V-45 M0 0 L32 18" stroke="${INK}" stroke-width="8" stroke-linecap="round"/></g>`;
}
const p1 = panel('1', '#e8f4f6',
  chatWin(cat(540, 470, 0.85, 'wide') +
    `<text x="790" y="260" font-family="SUIT" font-weight="900" font-size="80" fill="#9aa0a6">?</text>`,
    '집사가 아무 말도 안 씀...'),
  '집사가 바쁜 날');
const p2 = panel('2', '#fdf3e7',
  chatWin(cat(470, 500, 0.8, 'sleep') + clock(820, 320) +
    `<text x="820" y="450" font-family="SUIT" font-weight="900" font-size="44" fill="${INK}" text-anchor="middle">3시간째</text>`,
    '...'),
  '기다리다 잠듦');
const p3 = panel('3', '#fff0f3',
  cat(540, 560, 1.0, 'wide') + tears(540, 500, 1.0) +
  `<path d="M150 620 l40 -30 M130 560 l50 -5 M930 620 l-40 -30 M950 560 l-50 -5" stroke="${INK}" stroke-width="9" stroke-linecap="round"/>` +
  bubble(150, 60, 780, '클로드 찾아와라 잉잉', 560),
  '디지털 고양이는 외로워');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1080 } });
  for (const [i, svg] of [p1, p2, p3].entries()) {
    await page.setContent(`<html><body style="margin:0">${svg}</body></html>`);
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/p${i + 1}.png`, clip: { x: 0, y: 0, width: 1080, height: 1080 } });
  }
  await browser.close();
})();
