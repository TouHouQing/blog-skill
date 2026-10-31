"""Render portable article packages, check actual browser layout and finalize."""
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import zipfile
from runtime import ROOT, digest, node, read_json, run, save_json
from project import IMAGE, load, local

LABELS = {'blog':'博客', 'wechat':'微信公众号', 'post':'社区帖子'}


def now():
    return datetime.now(timezone.utc).isoformat()


def hashes(folder, paths):
    return {str(p).replace('\\','/'):digest(Path(folder)/p) for p in sorted(set(paths))}


def check_artifacts(folder, expected):
    for filename, sha in expected.items():
        p = Path(folder)/filename
        if not p.is_file() or digest(p) != sha:
            raise ValueError('Rendered artifact changed or disappeared: '+filename)


def inspect_article_cover(folder, soup, required):
    """Check the actual article fragment, not the separate delivery-page hero."""
    result={'required':required,'passed':True}
    if not required:
        return result
    out=Path(folder).resolve()
    article=soup.select_one('#article')
    first=article.find(True,recursive=False) if article else None
    image=first.find('img') if first and first.name=='figure' else None
    records=[item for item in read_json(out/'assets.json') if item.get('id')=='__article_cover']
    expected=records[0].get('file','') if len(records)==1 else ''
    actual=image.get('src','') if image else ''
    image_path=(out/actual).resolve()
    matches=bool(actual.startswith('assets/') and image_path.is_relative_to(out/'assets')
                 and image_path.is_file() and digest(image_path)==digest(out/'cover-wide.png'))
    result.update(first_block_is_cover=bool(image and expected and actual==expected),
                  cover_bytes_match=matches,
                  single_managed_cover=bool(expected and article and
                      sum(img.get('src')==expected for img in article.find_all('img'))==1),
                  no_duplicate_caption=bool(first and first.name=='figure' and not first.find('figcaption')))
    result['passed']=all(result[key] for key in ('first_block_is_cover','cover_bytes_match',
                                                'single_managed_cover','no_duplicate_caption'))
    return result


def render(project_path, output):
    data = load(project_path)
    project, out = data['project'], Path(output).resolve()
    if any(item['path'].is_relative_to(out) for item in data['drafts'].values()):
        raise ValueError('Render output must not contain input drafts; use a separate output folder.')
    if any(item['absolute_path'].is_relative_to(out) for item in data['assets'].values()):
        raise ValueError('Render output must not contain source assets.')
    if any(item['absolute_path'].is_relative_to(out) for item in data['cover_design'].values()):
        raise ValueError('Render output must not contain source promotion covers.')
    out.mkdir(parents=True,exist_ok=True)
    (out/'assets').mkdir(exist_ok=True)
    source = out/'source'
    (source/'drafts').mkdir(parents=True,exist_ok=True)
    asset_paths, asset_records, tracked = {}, [], []
    portable = json.loads(json.dumps(project))
    portable['research_file'] = 'research.json' if data['research'] else None
    portable['review_file'] = 'review.json'
    portable.pop('account_dir',None)
    portable['assets'] = []
    used_assets={match[2][6:] for draft in data['drafts'].values() for match in IMAGE.finditer(draft['text'])}
    used_assets.update(project.get('cover',{}).get(shape+'_asset') for shape in ('wide','square'))
    originals={read_json(local(data['base'],item['capture_manifest'])).get('source_asset_id')
               for item in data['assets'].values() if item.get('capture_manifest')}
    for key, item in data['assets'].items():
        stem = re.sub(r'[^a-zA-Z0-9_-]','-',key)[:50] or 'image'
        name = f'{stem}-{item["sha256"][:12]}{item["absolute_path"].suffix.lower()}'
        # Raw annotation evidence may expose identities; keep it out of publishable assets/.
        rel = ('source/originals/' if key in originals and key not in used_assets else 'assets/')+name
        (out/rel).parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(item['absolute_path'],out/rel)
        asset_paths[key] = rel
        tracked.append(rel)
        record = {k:v for k,v in item.items() if k not in ('absolute_path','path','capture_manifest')}
        record['file'] = rel
        asset_records.append(record)
        portable_asset = {**record,'path':'../'+rel}
        portable_asset.pop('file',None)
        if item.get('capture_manifest'):
            capture_name = f'captures/{stem}.capture.json'
            (source/'captures').mkdir(exist_ok=True)
            shutil.copy2(local(data['base'],item['capture_manifest']),source/capture_name)
            portable_asset['capture_manifest'] = capture_name
            tracked.append('source/'+capture_name)
        portable['assets'].append(portable_asset)
    articles, code_blocks, frontmatters = {}, {}, {}
    for platform, item in data['drafts'].items():
        spec = project['platforms'][platform]
        summary = item['summary']
        if not summary:
            raise ValueError('Provide a written summary for '+platform)
        if platform=='wechat':
            (out/'wechat-description.txt').write_text(summary+'\n','utf-8')
            tracked.append('wechat-description.txt')
        rewritten = IMAGE.sub(lambda m:'!['+m[1]+']('+asset_paths[m[2][6:]]+')',item['text'])
        articles[platform] = {'title':item['title'],'summary':summary,'markdown':rewritten}
        code_blocks[platform] = [m[1].rstrip('\n') for m in re.finditer(r'^```[^\n]*\n([\s\S]*?)^```\s*$',item['text'],re.M)]
        metadata = {'title':item['title'],'description':summary,'tags':spec.get('tags',project.get('tags',[]))}
        if project.get('author'):
            metadata['author'] = project['author']
        if spec.get('slug'):
            metadata['slug'] = spec['slug']
        frontmatter = '\n'.join(k+': '+json.dumps(v,ensure_ascii=False) for k,v in metadata.items())
        frontmatters[platform]='---\n'+frontmatter+'\n---\n\n'
        (out/(platform+'.md')).write_text(frontmatters[platform]+rewritten,'utf-8')
        shutil.copy2(item['path'],source/'drafts'/(platform+'.md'))
        portable['platforms'][platform]['file'] = 'drafts/'+platform+'.md'
        tracked += [platform+'.md','source/drafts/'+platform+'.md']
    cover_spec = project.get('cover',{})
    if data['cover_design']:
        from PIL import Image
        for shape,item in data['cover_design'].items():
            target=out/('cover-'+shape+'.png')
            with Image.open(item['absolute_path']) as image:
                dimensions=list(image.size)
                if image.format=='PNG':
                    shutil.copy2(item['absolute_path'],target)
                else:
                    image.convert('RGB').save(target,format='PNG')
            portable['cover']['design'][shape+'_file']='../cover-'+shape+'.png'
            save_json(target.with_suffix('.meta.json'),{'method':'designed-promotion-cover',
                'source_sha256':item['sha256'],'dimensions':dimensions,
                'role':'article-cover-only','product_screenshot':False,
                'rights':cover_spec['design']['rights']})
    elif cover_spec.get('wide_asset') and cover_spec.get('square_asset'):
        from PIL import Image
        for shape in ('wide','square'):
            key=cover_spec[shape+'_asset']
            item=data['assets'][key]
            target=out/('cover-'+shape+'.png')
            with Image.open(item['absolute_path']) as image:
                dimensions=list(image.size)
                if image.format=='PNG':
                    shutil.copy2(item['absolute_path'],target)
                else:
                    image.save(target,format='PNG')
            save_json(target.with_suffix('.meta.json'),{'method':'source-asset','asset_id':key,
                'source_sha256':item['sha256'],'file':asset_paths[key],'dimensions':dimensions,
                'generated_artwork':False})
    else:
        from images import cover
        cover_title = cover_spec.get('title',project['title'])
        cover_summary = cover_spec.get('subtitle',project.get('summary',''))
        cover(cover_title,out/'cover-wide.png',cover_summary)
        cover(cover_title,out/'cover-square.png',cover_summary,square=True)
    tracked += ['cover-wide.png','cover-square.png','cover-wide.meta.json','cover-square.meta.json']
    if 'wechat' in articles and project['platforms']['wechat'].get('include_cover',False):
        # Keep the cover inside the copied article, independently of preview-only headers.
        cover_sha=digest(out/'cover-wide.png')
        cover_rel='assets/article-cover-'+cover_sha[:12]+'.png'
        shutil.copy2(out/'cover-wide.png',out/cover_rel)
        tracked.append(cover_rel)
        rights=(cover_spec.get('design') or {}).get('rights')
        if not rights and cover_spec.get('wide_asset'):
            rights=data['assets'][cover_spec['wide_asset']]['rights']
        asset_records.append({'id':'__article_cover','role':'cover','file':cover_rel,'sha256':cover_sha,
                              'placement':'article-start','rights':rights or {'kind':'owned'}})
        markdown=articles['wechat']['markdown']
        title=re.match(r'\s*#\s+[^\n]+\n',markdown)
        position=title.end() if title else 0
        markdown=markdown[:position]+'\n![]('+cover_rel+')\n\n'+markdown[position:].lstrip('\n')
        articles['wechat']['markdown']=markdown
        (out/'wechat.md').write_text(frontmatters['wechat']+markdown,'utf-8')
    command = [node(),ROOT/'scripts/render.mjs']
    rendered = read_json_result(run(command,input=json.dumps({'output':str(out),'title':project['title'],
                               'summary':project.get('summary',''),'articles':articles},ensure_ascii=False)))
    tracked += rendered['files']
    save_json(source/'project.json',portable)
    save_json(source/'research.json',data['research'])
    save_json(out/'assets.json',asset_records)
    credits=['# 素材署名与许可','', '素材来源与核查记录单独保存，不自动附在公众号正文末尾。', '']
    for record in asset_records:
        rights=record.get('rights',{})
        if rights.get('creator') or rights.get('license'):
            credits += ['## '+record['id'],'', '文件：'+record['file'],
                        '作者：'+rights.get('creator','未提供'), '来源：'+rights.get('source_url','未提供'),
                        '许可：'+rights.get('license','未提供')+' '+rights.get('license_url',''),
                        '处理：'+rights.get('changes','无'), '']
            if rights.get('commercial_reuse'):
                credits += ['商业使用权限：'+rights['commercial_reuse'],'']
    (out/'素材署名与许可.md').write_text('\n'.join(credits),'utf-8')
    save_json(out/'publication.json',{'title':project['title'],
              'platforms':{p:{'title':item['title'],'summary':item['summary'],
                            'summary_characters':len(item['summary']),
                            'tags':project['platforms'][p].get('tags',project.get('tags',[])),
                            'markdown':p+'.md','preview':p+'.html'} for p,item in articles.items()},
              'covers':{'wide':'cover-wide.png','square':'cover-square.png'},
              'status':'local_prepared','wechat_draft_uploaded':False,'published':False})
    tracked += ['source/project.json','source/research.json','assets.json','publication.json','素材署名与许可.md']
    report = {'status':'rendered_pending_review','rendered_at':now(),'project_sha256':data['project_sha256'],
              'content_hashes':data['hashes'],'platforms':list(articles),'articles':{k:{'title':v['title'],'summary':v['summary']} for k,v in articles.items()},
              'asset_count':len(asset_records),'code_blocks':code_blocks,'paid_apis_enabled':False,
              'artifact_hashes':hashes(out,tracked),'warnings':data['warnings'],
              'external_state':{'wechat_draft':'not_uploaded','publication':'not_published'},
              'renderer':rendered['renderer']}
    report['render_id'] = hashlib.sha256(json.dumps(report['artifact_hashes'],sort_keys=True).encode()).hexdigest()[:20]
    save_json(out/'report.json',report)
    return {'output':str(out),'render_id':report['render_id'],'status':report['status'],'platforms':report['platforms']}


def read_json_result(result):
    return json.loads(result.stdout)


def verify_clipboard(browser, output):
    """Actually paste embedded images with all source requests blocked, for both copy paths."""
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from bs4 import BeautifulSoup
    out=Path(output).resolve()
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self,*args):
            pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(out)))
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    pixel_fingerprints='''()=>[...document.querySelectorAll('#article img')].map(img=>{
        const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
        canvas.getContext('2d').drawImage(img,0,0);
        return [img.naturalWidth,img.naturalHeight,canvas.toDataURL('image/png')];})'''
    modes=[]
    try:
        for mode in ('clipboard-api','copy-event-fallback'):
            context=browser.new_context(viewport={'width':390,'height':900},permissions=['clipboard-read','clipboard-write'])
            try:
                page=context.new_page()
                page.goto(f'http://127.0.0.1:{server.server_port}/wechat.html',wait_until='load')
                expected=page.evaluate(pixel_fingerprints)
                if mode=='copy-event-fallback':
                    page.evaluate("Object.defineProperty(navigator,'clipboard',{value:undefined,configurable:true})")
                page.locator('#copy').click()
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('正文已复制')")
                clipboard=page.evaluate('''async()=>{
                    // Use a clean Navigator prototype even when testing the event fallback.
                    const clipboard=Object.getOwnPropertyDescriptor(Navigator.prototype,'clipboard').get.call(navigator);
                    const items=await clipboard.read();
                    return await(await items.find(item=>item.types.includes('text/html')).getType('text/html')).text();
                }''')
                images=BeautifulSoup(clipboard,'html.parser').select('img')
                if len(images)!=len(expected) or any(not img.get('src','').startswith('data:image/') for img in images):
                    raise ValueError('Clipboard images must contain image bytes, never local or network URLs.')
                page.close()
                context.route('**/*',lambda route:route.abort())
                target=context.new_page()
                target.set_content('<!doctype html><html><head><meta charset="utf-8"></head><body><div id="paste" contenteditable="true"></div></body></html>')
                target.locator('#paste').click()
                target.keyboard.press('Control+V')
                target.wait_for_function("count=>document.querySelectorAll('#paste img').length===count && [...document.querySelectorAll('#paste img')].every(img=>img.complete&&img.naturalWidth>0)",arg=len(expected))
                actual=target.evaluate(pixel_fingerprints)
                if actual!=expected:
                    raise ValueError('Images changed or disappeared when pasted without source access.')
                if target.locator('#paste nav, #paste script, #paste dialog, #paste template').count():
                    raise ValueError('Preview controls leaked into the pasted article.')
                result={'mode':mode,'images':len(images),'embedded_bytes':True,'source_page_closed':True,
                        'source_requests_blocked':True,'pasted_pixels_match':True,'passed':True}
                if (out/'qa').is_dir():
                    result['screenshot']='qa/pasted-'+mode+'.png'
                    target.screenshot(path=str(out/result['screenshot']),full_page=True)
                modes.append(result)
            finally:
                context.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
    return {'passed':True,'modes':modes,'scope':'Local Chromium clipboard and real paste; WeChat backend not tested.'}


def verify(output):
    from bs4 import BeautifulSoup
    from playwright.sync_api import sync_playwright
    out = Path(output).resolve()
    report = read_json(out/'report.json')
    check_artifacts(out,report['artifact_hashes'])
    checks, failures, samples = [], [], []
    clipboard_check=None
    cover_check=None
    if 'wechat' in report['platforms']:
        fragment = (out/'wechat-body.html').read_text('utf-8')
        soup = BeautifulSoup(fragment,'html.parser')
        if soup.select('script,style,iframe,link') or re.search(r'var\(--|MDTOHTMLIMGPH_|\{\{',fragment):
            failures.append('WeChat body contains unresolved styles, scripts or placeholders.')
        if any(not image.get('src','').startswith('assets/') for image in soup.select('img')):
            failures.append('WeChat body image is not part of the asset package.')
        exported_project=read_json(out/'source/project.json')
        cover_check=inspect_article_cover(out,soup,exported_project['platforms']['wechat'].get('include_cover',False))
        if not cover_check['passed']:
            failures.append('Opening cover is missing, duplicated, captioned or does not match the final cover image.')
    for platform in report['platforms']:
        soup = BeautifulSoup((out/(platform+'.html')).read_text('utf-8'),'html.parser')
        code = [item.get_text().rstrip('\n') for item in soup.select('main #article pre code')]
        if code != report['code_blocks'][platform]:
            failures.append('Code text changed while rendering '+platform)
    qa = out/'qa'
    qa.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for platform in [*report['platforms'],'index']:
                for width in ([360,390,430,1100] if platform=='wechat' else [390,1100]):
                    page = browser.new_page(viewport={'width':width,'height':900},device_scale_factor=1)
                    errors = []
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.route(re.compile(r'^https?://'),lambda route:route.abort())
                    page.goto((out/(platform+'.html')).as_uri(),wait_until='load',timeout=20000)
                    page.evaluate('document.fonts.ready')
                    result = page.evaluate('''() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
                        brokenImages:[...document.images].filter(x=>!x.complete||!x.naturalWidth).map(x=>x.getAttribute('src')),
                        badLinks:[...document.querySelectorAll('a[href]')].filter(x=>/^(javascript|data):/i.test(x.getAttribute('href'))).map(x=>x.href),
                        bodyCharacters:document.body.innerText.length,images:document.images.length})''')
                    passed = result['scrollWidth'] <= width+1 and not result['brokenImages'] and not result['badLinks'] and not errors
                    checks.append({'page':platform,'width':width,'passed':passed,**result,'page_errors':errors})
                    if not passed:
                        failures.append(f'{platform} at {width}px: overflow, missing image or browser error')
                    if width==390:
                        name=f'{platform}-390.png'
                        page.screenshot(path=str(qa/name),full_page=True)
                        samples.append('qa/'+name)
                        blocks=page.locator('#article pre, #article figure')
                        for n in range(blocks.count()):
                            block_name=f'{platform}-block-{n+1}.png'
                            blocks.nth(n).screenshot(path=str(qa/block_name))
                            samples.append('qa/'+block_name)
                        if platform=='wechat':
                            for label, fraction in (('top',0),('middle',.5),('end',1)):
                                page.evaluate('(fraction)=>window.scrollTo(0,(document.documentElement.scrollHeight-innerHeight)*fraction)',fraction)
                                page.screenshot(path=str(qa/(label+'.png')),full_page=False)
                                samples.append('qa/'+label+'.png')
                    page.close()
            if 'wechat' in report['platforms']:
                clean=BeautifulSoup((out/'wechat-body.html').read_text('utf-8'),'html.parser')
                for tag in clean.find_all(True):
                    tag.attrs.pop('class',None)
                page=browser.new_page(viewport={'width':390,'height':900},device_scale_factor=1)
                page.goto((out/'wechat.html').as_uri(),wait_until='load')
                page.set_content('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>'+str(clean)+'</body></html>',wait_until='load')
                result=page.evaluate('''()=>({scrollWidth:document.documentElement.scrollWidth,
                    brokenImages:[...document.images].filter(x=>!x.complete||!x.naturalWidth).map(x=>x.getAttribute('src')),
                    code:[...document.querySelectorAll('pre code')].map(x=>x.textContent.replace(/\\n+$/,''))})''')
                passed=result['scrollWidth']<=391 and not result['brokenImages'] and result['code']==report['code_blocks']['wechat']
                checks.append({'page':'wechat-without-classes-or-head-styles','width':390,'passed':passed,**result})
                if not passed:
                    failures.append('WeChat inlined fragment failed after removing class attributes and head styles.')
                page.screenshot(path=str(qa/'wechat-inline-only.png'),full_page=True)
                samples.append('qa/wechat-inline-only.png')
                page.close()
            if 'wechat' in report['platforms']:
                clipboard_check=verify_clipboard(browser,out)
                samples += [mode['screenshot'] for mode in clipboard_check['modes'] if mode.get('screenshot')]
        finally:
            browser.close()
    result = {'passed':not failures,'render_id':report['render_id'],'checked_at':now(),
              'artifact_hashes':report['artifact_hashes'],'checks':checks,'failures':failures,
              'screenshots':samples,'clipboard':clipboard_check,'cover_in_body':cover_check,
              'scope':'Local Chromium responsive rendering and real clipboard paste; no WeChat account or physical-device preview performed.'}
    save_json(out/'verification.json',result)
    if failures:
        raise ValueError('Browser verification failed: '+'; '.join(failures))
    return {'passed':True,'pages_checked':len(checks),'screenshots':samples}


def finalize(project_path, output):
    from project import local
    data = load(project_path)
    project, out = data['project'], Path(output).resolve()
    report = read_json(out/'report.json')
    if report['project_sha256'] != data['project_sha256'] or report['content_hashes'] != data['hashes']:
        raise ValueError('Project or drafts changed after rendering; render and verify the current version.')
    check_artifacts(out,report['artifact_hashes'])
    verification = read_json(out/'verification.json')
    if not verification.get('passed') or verification.get('render_id')!=report['render_id'] or verification.get('artifact_hashes')!=report['artifact_hashes']:
        raise ValueError('Successful verification for this exact rendering is required.')
    if 'wechat' in project['platforms']:
        clipboard=verification.get('clipboard',{})
        modes=clipboard.get('modes',[])
        if (not clipboard.get('passed') or not modes or
                any(not all(mode.get(key) for key in ('passed','embedded_bytes','source_page_closed',
                    'source_requests_blocked','pasted_pixels_match')) for mode in modes)):
            raise ValueError('Successful real clipboard paste verification is required for WeChat.')
        if project['platforms']['wechat'].get('include_cover',False):
            cover=verification.get('cover_in_body',{})
            if not cover.get('required') or not cover.get('passed'):
                raise ValueError('Successful opening-cover verification is required for WeChat.')
    review = read_json(local(data['base'],project.get('review_file','review.json')))
    if review.get('status')!='reviewed' or review.get('content_hashes')!=data['hashes']:
        raise ValueError('Full-text editorial review must match the current drafts.')
    visual = review.get('visual_review',{})
    if visual.get('render_id')!=report['render_id'] or not visual.get('screenshots') or not visual.get('notes'):
        raise ValueError('Record actual visual review of screenshots from this rendering.')
    if any(name not in verification['screenshots'] or not (out/name).is_file() for name in visual['screenshots']):
        raise ValueError('Visual review references a screenshot not produced by this verification.')
    if any(item.get('status') not in ('resolved','accepted_with_reason') for item in review.get('findings',[])):
        raise ValueError('Editorial findings still need resolution.')
    shutil.copy2(local(data['base'],project.get('review_file','review.json')),out/'source/review.json')
    lines=['# 图文交付','',project['title'],'','打开 index.html 阅读成稿和各平台预览。','']
    for platform, spec in project['platforms'].items():
        item=report['articles'][platform]
        lines += ['## '+LABELS[platform],'','标题：'+item['title'],'',
                  ('推广描述：' if platform=='wechat' else '摘要：')+item['summary'],'']
        if platform=='wechat':
            lines += ['描述字符数：'+str(len(item['summary']))+'（含标点、空格和英文字符），另见 wechat-description.txt。','']
        tags=spec.get('tags',project.get('tags',[]))
        if tags:
            lines += ['标签：'+' '.join(tags),'']
    if 'wechat' in project['platforms']:
        lines += ['## 公众号使用','', '1. 打开 wechat.html，复制公众号正文排版。',
                  '2. 粘贴到图文编辑器。剪贴板包含实际图片数据与内联排版，不依赖本地图片路径；正文保留为文字，代码可复制。',
                  '3. 选择 cover-wide.png 作为横版封面，并核对方形裁切；cover-square.png 是独立方形版本。',
                  '4. 填写上方标题和摘要，保存草稿后检查图片、表格、链接和手机预览。','',
                  'wechat-copy.html 为已内嵌图片的独立离线图文；wechat-body.html 为使用配套 assets/ 的普通正文片段。',
                  '本地检查已实际复制并粘贴到独立编辑框，阻断原页面请求后比对全部图片像素；公众号后台的图片接收与保存仍须在那里核对。','']
        if project['platforms']['wechat'].get('include_cover',False):
            lines += ['横版封面已经放在正文首段之前，复制正文会一并复制；无需再手动插入首图。','']
    lines += ['## 文件与核验','', 'assets/ 为配图；source/ 保留可重渲染的项目、稿件、研究和审稿记录。',
              'verification.json 记录真实浏览器和粘贴检查；qa/ 是预览截图。素材署名与许可.md 单独保留来源许可。',
              'assets/ 是正文与封面用图；source/originals/ 仅为内部核验原始证据，可能含未遮盖的公开示例身份，不应作为发布配图。',
              '状态：本地图文成品已准备。公众号后台草稿未上传，文章未对外发布。','']
    (out/'交付说明.md').write_text('\n'.join(lines),'utf-8')
    report.update(status='ready_local',finalized_at=now(),editorial_review={'reviewer':review.get('reviewer','codex'),
                  'file':'source/review.json','content_hashes':review['content_hashes']})
    save_json(out/'report.json',report)
    included=set(report['artifact_hashes']) | {'report.json','verification.json','source/review.json','交付说明.md'} | set(verification['screenshots'])
    archive=out.parent/(out.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for filename in sorted(included):
            z.write(out/filename,arcname=out.name+'/'+filename)
    return {'status':'ready_local','preview':str(out/'index.html'),'archive':str(archive),'files':len(included),
            'paid_apis_enabled':False,'wechat_uploaded':False,'published':False}
