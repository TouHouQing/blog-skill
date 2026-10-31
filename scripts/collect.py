"""Collect public RSS and HN nominations without keys; retain source failures."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import hashlib
import html
import json
import math
import re
from urllib.request import Request, urlopen
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
import xml.etree.ElementTree as ET
from runtime import save_json

FEEDS = [
    ('IT之家', 'https://www.ithome.com/rss/'),
    ('InfoQ 中文', 'https://www.infoq.cn/feed.xml'),
    ('少数派', 'https://sspai.com/feed'),
    ('虎嗅', 'https://www.huxiu.com/rss/0.xml'),
    ('钛媒体', 'https://www.tmtpost.com/feed'),
    ('Google News 中文 AI', 'https://news.google.com/rss/search?'+urlencode({'q':'AI OR 人工智能 when:3d','hl':'zh-CN','gl':'CN','ceid':'CN:zh-Hans'})),
    ('Hugging Face', 'https://huggingface.co/blog/feed.xml'),
    ('Google AI', 'https://blog.google/technology/ai/rss/'),
    ('Google Research', 'https://research.google/blog/rss/'),
    ('GitHub Blog AI', 'https://github.blog/ai-and-ml/feed/'),
]
AI_RE = re.compile(r'\b(ai|llm|agent|gpt|claude|codex|kimi|deepseek|gemini|qwen|minimax|model|inference|hugging|speech|tts|openai|neural|transformer|diffusion|mcp)\b|AI(?=[\u4e00-\u9fff])|(?<=[\u4e00-\u9fff])AI|人工智能|大模型|月之暗面|通义|千问|智谱|豆包|机器学习', re.I)


def fetch(url):
    req = Request(url, headers={'User-Agent': 'Blog-Skill/1.0 (public-source research)'})
    with urlopen(req, timeout=22) as response:
        return response.read(4_000_000)


def date_value(value):
    try:
        dt = parsedate_to_datetime(value)
    except Exception:
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except Exception:
            return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def text_of(item, names):
    for name in names:
        value = item.findtext(name)
        if value:
            return html.unescape(re.sub('<[^>]+>', ' ', value)).strip()
    return ''


def rss(name, url):
    root = ET.fromstring(fetch(url))
    atom = '{http://www.w3.org/2005/Atom}'
    items = root.findall('.//item') or root.findall(f'.//{atom}entry')
    out = []
    for item in items[:45]:
        title = text_of(item, ['title', f'{atom}title'])
        link = text_of(item, ['link'])
        if not link:
            node = item.find(f'{atom}link')
            link = node.attrib.get('href', '') if node is not None else ''
        raw_date = text_of(item, ['pubDate', f'{atom}published', f'{atom}updated'])
        dt = date_value(raw_date)
        if title and link.startswith('https://'):
            out.append({'title': title, 'url': link, 'source': name, 'published_at': dt.isoformat() if dt else None,
                        'summary': text_of(item, ['description', f'{atom}summary'])[:1100], 'engagement': None})
    return out


def hn():
    # Algolia's public index returns actual discussion counts; no API key.
    url = 'https://hn.algolia.com/api/v1/search_by_date?tags=story&query=AI&hitsPerPage=60'
    data = json.loads(fetch(url))
    return [{'title': h.get('title', ''), 'url': h.get('url') or f"https://news.ycombinator.com/item?id={h['objectID']}",
             'source': 'Hacker News', 'discussion_url': f"https://news.ycombinator.com/item?id={h['objectID']}",
             'published_at': h.get('created_at'), 'summary': '',
             'engagement': {'points': h.get('points', 0), 'comments': h.get('num_comments', 0)}}
            for h in data.get('hits', [])]


def releases():
    projects = ['huggingface/transformers', 'ollama/ollama', 'vllm-project/vllm', 'ggml-org/llama.cpp', 'MoonshotAI/kimi-cli']
    result = []
    failed = []
    for repo in projects:
        try:
            records = json.loads(fetch(f'https://api.github.com/repos/{repo}/releases?per_page=3'))
            for record in records:
                if record.get('draft'):
                    continue
                result.append({'title': f'{repo}: {record.get("name") or record["tag_name"]}',
                               'url': record['html_url'], 'source': 'GitHub Releases',
                               'published_at': record.get('published_at'),
                               'summary': re.sub('<[^>]+>', ' ', record.get('body') or '')[:1100],
                               'engagement': None})
        except Exception as e:
            failed.append(f'{repo}: {str(e)[:100]}')
    return result, failed


HOTLISTS = {
    'weibo': ['https://60s.viki.moe/v2/weibo', 'https://v2.xxapi.cn/api/weibohot'],
    'douyin': ['https://60s.viki.moe/v2/douyin', 'https://v2.xxapi.cn/api/douyinhot'],
    'zhihu': ['https://60s.viki.moe/v2/zhihu'],
    'bilibili': ['https://v2.xxapi.cn/api/bilibilihot'],
}


def trend_leads(platform):
    errors = []
    for endpoint in HOTLISTS[platform]:
        try:
            data = json.loads(fetch(endpoint))
            items = data.get('data', [])
            if isinstance(items, dict):
                items = items.get('data', items.get('list', []))
            if not isinstance(items, list) or not items:
                raise ValueError('No usable hotlist returned.')
            result = []
            for item in items[:50]:
                if isinstance(item, str):
                    item = {'title': item}
                if not isinstance(item, dict):
                    continue
                title = item.get('title') or item.get('word') or item.get('name') or ''
                url = item.get('url') or item.get('link') or ''
                is_search_link = False
                if title and not url:
                    # Some public lists expose only words, not a topic detail URL.
                    # Explicit search links are navigation aids, not original evidence.
                    searches = {'douyin': 'https://www.douyin.com/search/',
                                'bilibili': 'https://search.bilibili.com/all?keyword=',
                                'weibo': 'https://s.weibo.com/weibo?q=',
                                'zhihu': 'https://www.zhihu.com/search?type=content&q='}
                    from urllib.parse import quote
                    url = searches[platform] + quote(title, safe='')
                    is_search_link = True
                if not title or not url.startswith('https://'):
                    continue
                result.append({'title': title, 'url': url, 'source': 'Trend: '+platform,
                               'published_at': None, 'summary': '', 'engagement': None,
                               'observed_heat': item.get('hot', item.get('heat', item.get('hot_value'))),
                               'url_kind': 'platform_search' if is_search_link else 'supplied_link',
                               'signal_url': endpoint, 'signal_observed_at': datetime.now(timezone.utc).isoformat()})
            if not result:
                raise ValueError('Hotlist has no titled HTTPS leads.')
            return result, errors
        except Exception as error:
            errors.append({'source': 'Trend: '+platform, 'url': endpoint, 'error': str(error)[:350]})
    return [], errors


def canonical_url(url):
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith('utm_') and key.lower() not in ('fbclid', 'gclid')]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), urlencode(query), ''))


def collect(output, hours=168, limit=40, feeds_file=None, hotlists='', keywords=None):
    if hours <= 0 or limit <= 0:
        raise ValueError('hours and limit must be positive.')
    requested = list(dict.fromkeys(key.strip() for key in hotlists.split(',') if key.strip()))
    if set(requested)-HOTLISTS.keys():
        raise ValueError('Unknown hotlist. Use '+','.join(HOTLISTS))
    feeds = FEEDS
    if feeds_file:
        records = json.loads(__import__('pathlib').Path(feeds_file).read_text('utf-8-sig'))
        if not isinstance(records, list) or not records:
            raise ValueError('feeds must be a nonempty JSON list of name/url objects.')
        feeds = [(item['name'], item['url']) for item in records]
        if any(not name or not url.startswith('https://') for name, url in feeds):
            raise ValueError('Custom RSS feeds need names and public HTTPS URLs.')
    now = datetime.now(timezone.utc)
    nominations, errors = [], []
    jobs = [(name, lambda n=name, u=url: rss(n, u)) for name, url in feeds]
    jobs.append(('Hacker News', hn))
    jobs.append(('GitHub Releases', releases))
    jobs.extend(('Trend: '+key, lambda p=key: trend_leads(p)) for key in requested)
    with ThreadPoolExecutor(max_workers=5) as pool:
        pending = {pool.submit(fn): name for name, fn in jobs}
        for job in as_completed(pending):
            try:
                value = job.result()
                if pending[job] == 'GitHub Releases' or pending[job].startswith('Trend: '):
                    items, failures = value
                    nominations.extend(items)
                    errors.extend(error if isinstance(error, dict) else {'source': 'GitHub Releases', 'error': error} for error in failures)
                else:
                    nominations.extend(value)
            except Exception as e:
                errors.append({'source': pending[job], 'error': str(e)[:350]})
    cutoff = now - timedelta(hours=hours)
    seen, final, undated = set(), [], []
    for item in nominations:
        dt = date_value(item.get('published_at') or '')
        if dt and (dt < cutoff or dt > now + timedelta(hours=2)):
            continue
        if keywords != '*' and not (re.compile(keywords, re.I) if keywords else AI_RE).search(item['title']+' '+item.get('summary','')):
            continue
        if not item.get('url', '').startswith('https://'):
            continue
        key = canonical_url(item['url'])
        if key in seen:
            continue
        seen.add(key)
        age = max(0, (now - dt).total_seconds() / 3600) if dt else hours
        engagement = item.get('engagement') or {}
        score = 40 * math.exp(-age / 72) + min(30, math.log1p(engagement.get('points', 0)) * 5)
        score += 15 if re.search(r'open|local|free|tool|agent|speech|video|release', item['title'], re.I) else 0
        item.update(id=hashlib.sha256(key.encode()).hexdigest()[:12], heuristic_score=round(score, 1),
                    age_hours=round(age, 1) if dt else None, date_verified=bool(dt))
        if dt is None:
            item['date_status'] = 'unknown; verify original publication before calling this recent news'
            undated.append(item)
        else:
            final.append(item)
    final.sort(key=lambda item: item['heuristic_score'], reverse=True)
    # Discussion votes can otherwise push every domestic feed below one HN source.
    # A soft cap preserves breadth; remaining slots are filled if alternatives are scarce.
    cap = max(3, math.ceil(limit/3))
    selected, deferred, counts = [], [], Counter()
    for item in final:
        if counts[item['source']] < cap and len(selected) < limit:
            selected.append(item)
            counts[item['source']] += 1
        else:
            deferred.append(item)
    selected.extend(deferred[:max(0, limit-len(selected))])
    selected.sort(key=lambda item: item['heuristic_score'], reverse=True)
    fetched_counts = Counter(item['source'] for item in nominations)
    dated_counts = Counter(item['source'] for item in final)
    unknown_counts = Counter(item['source'] for item in undated)
    selected_counts = Counter(item['source'] for item in selected)
    coverage = {name: {'fetched_items': fetched_counts[name], 'dated_relevant': dated_counts[name],
                       'undated_relevant': unknown_counts[name], 'selected': selected_counts[name]}
                for name in sorted(fetched_counts)}
    result = {'collected_at': now.isoformat(), 'window_hours': hours, 'candidates': selected,
              'undated_leads': undated[:limit],
              'source_coverage': coverage, 'total_dated_relevant': len(final),
              'selection_note': 'Soft per-source cap then fill remaining slots; discussion votes do not define Chinese-audience relevance.',
              'source_errors': errors, 'paid_api_cost': 0,
              'scoring_note': 'Editorial nominations based on recency, tool relevance and available engagement; not viral probabilities.'}
    save_json(output, result)
    if not final:
        raise RuntimeError(f'No dated candidates collected. See source_errors in {output}. Verify network and widen the date window; do not fabricate news.')
    return result
