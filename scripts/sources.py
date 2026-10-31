"""Fetch public source text and take actual browser screenshots with provenance."""
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from runtime import digest, save_json


def public_url(url):
    value = urlparse(url)
    if value.scheme not in ('http', 'https') or not value.hostname or value.username:
        raise ValueError('Use a public HTTP(S) URL without embedded credentials.')
    return url


def fetch(url, output):
    from bs4 import BeautifulSoup
    public_url(url)
    request = Request(url, headers={'User-Agent':'Blog-Skill/1.0 (public-source research)'})
    with urlopen(request, timeout=30) as response:
        if 'html' not in response.headers.get('Content-Type', '').lower():
            raise ValueError('Use a webpage URL; binary documents need a dedicated reader.')
        raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ValueError('Page exceeds the source reader size limit.')
        final_url = response.url
    soup = BeautifulSoup(raw, 'html.parser')
    title = soup.title.get_text(' ',strip=True) if soup.title else ''
    container = soup.select_one('article') or soup.select_one('main') or soup.body or soup
    for tag in container.select('script,style,nav,footer,header,noscript'):
        tag.decompose()
    text = container.get_text('\n', strip=True)
    if len(text) < 120 or any(x in title.lower() for x in ('just a moment', 'access denied', 'sign in')):
        raise RuntimeError('The page appears gated or incomplete; fetch did not establish access to the source.')
    data = {'url':url,'final_url':final_url,'title':title,'text':text,
            'checked_at':datetime.now(timezone.utc).isoformat(),'method':'http-html-extraction'}
    save_json(output, data)
    return {key:value for key,value in data.items() if key != 'text'} | {'characters':len(text)}


def capture(url, output, selector=None, width=1280, height=850, wait_selector=None, clip_height=None, full_page=False):
    from playwright.sync_api import sync_playwright
    public_url(url)
    path = Path(output).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
            response = page.goto(url,wait_until='domcontentloaded',timeout=30000)
            if response and response.status >= 400:
                raise RuntimeError(f'Page returned HTTP {response.status}. No substitute screenshot was generated.')
            page.wait_for_timeout(900)
            if wait_selector:
                page.locator(wait_selector).first.wait_for(state='visible',timeout=20000)
            page.wait_for_function("!document.body.innerText.includes('正在加载编辑器')",timeout=20000)
            page.evaluate('document.fonts.ready')
            body = page.locator('body').inner_text()
            if len(body.strip())<60 or any(x in page.title().lower() for x in ('just a moment','access denied')):
                raise RuntimeError('Page is still a loading/gate shell; no usable source screenshot was established.')
            if selector:
                locator = page.locator(selector).first
                locator.wait_for(state='visible',timeout=10000)
                locator.scroll_into_view_if_needed()
                box = locator.bounding_box()
                if full_page:
                    locator.screenshot(path=str(path))
                else:
                    page.screenshot(path=str(path),clip={**box,'height':min(box['height'],clip_height or height),'width':min(box['width'],width)})
            else:
                page.screenshot(path=str(path),full_page=full_page)
            data = {'url':url,'final_url':page.url,'title':page.title(),'method':'real-browser-screenshot',
                    'checked_at':datetime.now(timezone.utc).isoformat(),'sha256':digest(path),
                    'selector':selector,'wait_selector':wait_selector,'clip_height':clip_height,'full_page':full_page,'viewport':{'width':width,'height':height}}
            save_json(path.with_suffix('.capture.json'),data)
            return data
        finally:
            browser.close()
