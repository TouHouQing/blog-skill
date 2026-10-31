"""Article inputs and evidence checks; editorial truth remains the agent's job."""
from pathlib import Path
import re
from urllib.parse import urlparse, unquote
from runtime import digest, read_json

PLATFORMS = ('blog', 'wechat', 'post')
IMAGE = re.compile(r'!\[([^\]]*)\]\(([^\s)]+)(?:\s+"[^"]*")?\)')


def local(base, value):
    path = Path(value)
    return (path if path.is_absolute() else Path(base)/path).resolve()


def prose(text):
    text = re.sub(r'```[^\n]*\n[\s\S]*?```', '', text)
    return re.sub(r'`[^`]*`', '', text)


def load(project_path, stage='produce'):
    path = Path(project_path).resolve()
    project = read_json(path)
    base = path.parent
    for field in ('title','audience','purpose','platforms'):
        if not project.get(field):
            raise ValueError('Missing project field: '+field)
    if not isinstance(project['platforms'],dict) or set(project['platforms'])-set(PLATFORMS):
        raise ValueError('platforms must map blog/wechat/post to draft specifications.')
    if project.get('approval_status') not in ('draft','awaiting_user','approved','direct'):
        raise ValueError('Set approval_status to draft, awaiting_user, approved or direct.')
    visual_policy = project.get('visual_policy','flexible')
    if visual_policy not in ('flexible','real_ui_only'):
        raise ValueError('visual_policy must be flexible or real_ui_only.')
    if stage == 'produce' and project['approval_status'] not in ('approved','direct'):
        raise ValueError('Production is awaiting user approval; only draft preflight is permitted.')
    research = read_json(local(base, project['research_file'])) if project.get('research_file') else {}
    mode = project.get('research_mode','web')
    if mode not in ('web','provided','none'):
        raise ValueError('research_mode must be web, provided or none.')
    if stage == 'produce' and mode == 'web' and not research.get('searches'):
        raise ValueError('Web research needs actual searches and result_urls.')
    for search in research.get('searches',[]):
        if not search.get('query') or not search.get('result_urls'):
            raise ValueError('Each actual search needs query and result_urls.')
    sources = {}
    for item in research.get('sources',[]):
        if not all(item.get(k) for k in ('id','url','title','checked_at')) or item['id'] in sources:
            raise ValueError('Research sources need unique id, URL, title and checked_at.')
        parsed = urlparse(item['url'])
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username:
            raise ValueError('Invalid public source URL: '+item['id'])
        sources[item['id']] = item
    claims = {}
    for claim in research.get('claims',[]):
        if not claim.get('id') or not claim.get('text') or claim['id'] in claims:
            raise ValueError('Research claims need unique id and text.')
        if claim.get('status') not in ('verified','attributed','unverified'):
            raise ValueError('Claim status must be verified, attributed or unverified.')
        if not claim.get('source_ids') or set(claim['source_ids'])-set(sources):
            raise ValueError('Every factual claim needs resolved source_ids: '+claim['id'])
        claims[claim['id']] = claim
    if stage == 'produce' and mode == 'web' and not claims:
        raise ValueError('Web research must record the claims used in the article.')
    inventory, annotated = {}, []
    for asset in project.get('assets',[]):
        if not asset.get('id') or asset['id'] in inventory or not asset.get('path'):
            raise ValueError('Assets need unique id and path.')
        asset_path = local(base,asset['path'])
        exists = asset_path.is_file()
        if not exists and stage == 'produce':
            raise ValueError('Asset is missing: '+str(asset_path))
        if not asset.get('rights',{}).get('kind'):
            raise ValueError('Declare asset rights: '+asset['id'])
        if visual_policy == 'real_ui_only' and asset.get('role') != 'screenshot':
            raise ValueError('real_ui_only requires actual captured screenshots; generated artwork is not allowed: '+asset['id'])
        if asset.get('role') == 'screenshot' and exists:
            manifest = asset.get('capture_manifest')
            if not manifest:
                raise ValueError('A real screenshot needs its capture_manifest: '+asset['id'])
            record = read_json(local(base,manifest))
            if record.get('method') not in ('real-browser-screenshot','annotated-screenshot') or record.get('sha256') != digest(asset_path):
                raise ValueError('Screenshot lineage does not match the actual image: '+asset['id'])
            if record.get('method') == 'annotated-screenshot':
                annotated.append((asset['id'],record))
        if exists:
            from PIL import Image
            with Image.open(asset_path) as image:
                image.verify()
        inventory[asset['id']] = {**asset,'absolute_path':asset_path,'sha256':digest(asset_path) if exists else None}
    for key, record in annotated:
        source_id=record.get('source_asset_id')
        source=inventory.get(source_id)
        if not source or source_id==key or source.get('role')!='screenshot':
            raise ValueError('Annotated screenshot needs a registered raw screenshot source: '+key)
        original_record=read_json(local(base,source['capture_manifest']))
        if original_record.get('method')!='real-browser-screenshot':
            raise ValueError('Annotate the raw captured screenshot, preserving its original source: '+key)
        from annotations import validate_derivation
        validate_derivation(source['absolute_path'],inventory[key]['absolute_path'],record)
    cover_spec = project.get('cover',{})
    cover_ids = [cover_spec.get(shape+'_asset') for shape in ('wide','square')]
    cover_design={}
    if cover_spec.get('design'):
        design=cover_spec['design']
        if not isinstance(design,dict) or any(cover_ids) or not design.get('rights',{}).get('kind'):
            raise ValueError('Designed promotion covers need separate files and declared rights, without screenshot cover IDs.')
        for shape in ('wide','square'):
            if not design.get(shape+'_file'):
                raise ValueError('Designed promotion cover requires '+shape+'_file.')
            cover_path=local(base,design[shape+'_file'])
            if not cover_path.is_file():
                raise ValueError('Designed promotion cover is missing: '+str(cover_path))
            from PIL import Image
            with Image.open(cover_path) as image:
                if image.format not in ('PNG','JPEG','WEBP'):
                    raise ValueError('Designed promotion cover must be a raster image.')
                image.verify()
            cover_design[shape]={'absolute_path':cover_path,'sha256':digest(cover_path)}
    elif visual_policy == 'real_ui_only' or any(cover_ids):
        if stage == 'produce' and not all(cover_ids):
            raise ValueError('Source-image covers require both cover.wide_asset and cover.square_asset; no generated fallback is permitted.')
        if stage == 'produce' and any(key not in inventory for key in cover_ids):
            raise ValueError('Cover asset IDs must resolve to registered images.')
    drafts, warnings = {}, []
    hashes = {}
    for platform, spec in project['platforms'].items():
        if 'include_cover' in spec and not isinstance(spec['include_cover'],bool):
            raise ValueError('include_cover must be true or false: '+platform)
        draft = local(base,spec['file'])
        if not draft.is_file():
            if stage == 'draft':
                warnings.append('Draft not written yet: '+str(draft))
                continue
            raise ValueError('Draft is missing: '+str(draft))
        text = draft.read_text('utf-8-sig')
        if len(prose(text).strip()) < 80:
            raise ValueError('Draft is too short or empty: '+platform)
        if re.search(r'\[(?:TODO|待补|待填写|placeholder)\]|\{\{[^}]+\}\}',prose(text),re.I):
            raise ValueError('Unfinished prose placeholder: '+platform)
        if stage == 'produce' and re.search(r'^```(?:mermaid|plantuml|math)\s*$',text,re.M):
            raise ValueError('Convert diagram/formula source to an image before rendering: '+platform)
        used_assets = []
        for _, target in IMAGE.findall(text):
            if target.startswith('asset:'):
                key = target[6:]
                if key not in inventory:
                    raise ValueError('Unknown image asset: '+key)
                used_assets.append(key)
            else:
                raise ValueError('Register article images and reference them as asset:<id>: '+target)
        headings = re.findall(r'^#{1,6}\s+(.+)$',text,re.M)
        summary=spec.get('summary',project.get('summary',''))
        limit=spec.get('summary_max_chars')
        if limit is not None:
            if isinstance(limit,bool) or not isinstance(limit,int) or limit<=0:
                raise ValueError('summary_max_chars must be a positive integer: '+platform)
            if len(summary)>limit:
                raise ValueError(f'{platform} promotion summary exceeds {limit} characters ({len(summary)}).')
        drafts[platform] = {'path':draft,'text':text,'asset_ids':used_assets,'headings':headings,
                            'title':spec.get('title',project['title']),'summary':summary}
        hashes[platform] = digest(draft)
    mapping = project.get('evidence_map',[])
    for item in mapping:
        platform = item.get('platform')
        if platform not in project['platforms'] or not item.get('section'):
            raise ValueError('Evidence map needs an existing platform and section.')
        if set(item.get('claim_ids',[]))-set(claims) or set(item.get('asset_ids',[]))-set(inventory):
            raise ValueError('Evidence map contains unresolved claim or asset IDs.')
        if stage == 'produce' and any(claims[k]['status']=='unverified' for k in item.get('claim_ids',[])):
            raise ValueError('Unverified claim cannot support a finished paragraph.')
        if platform in drafts:
            if item['section'] not in drafts[platform]['headings']:
                raise ValueError('Evidence map section does not occur in draft: '+item['section'])
            if set(item.get('asset_ids',[]))-set(drafts[platform]['asset_ids']):
                raise ValueError('Evidence map refers to assets not actually used in the draft.')
            matches=list(re.finditer(r'^(#{1,6})\s+(.+)$',drafts[platform]['text'],re.M))
            match=next(m for m in matches if m[2]==item['section'])
            ending=next((m.start() for m in matches if m.start()>match.start() and len(m[1])<=len(match[1])),len(drafts[platform]['text']))
            section=drafts[platform]['text'][match.end():ending]
            section_assets={target[6:] for _,target in IMAGE.findall(section) if target.startswith('asset:')}
            if set(item.get('asset_ids',[]))-section_assets:
                raise ValueError('Evidence image is used outside its mapped section.')
    if stage == 'produce' and mode == 'web':
        if any(not any(x.get('platform')==p and x.get('claim_ids') for x in mapping) for p in drafts):
            raise ValueError('Each factual platform draft needs evidence_map entries.')
    return {'project':project,'base':base,'path':path,'research':research,'assets':inventory,'cover_design':cover_design,
            'drafts':drafts,'hashes':hashes,'warnings':warnings,'project_sha256':digest(path)}


def preflight(project_path, stage='produce'):
    data = load(project_path,stage)
    return {'stage':stage,'technical_inputs_ready':True,'project_sha256':data['project_sha256'],
            'content_hashes':data['hashes'],'platforms':list(data['drafts']),
            'assets':{key:{'path':str(item['absolute_path']),'sha256':item['sha256']} for key,item in data['assets'].items()},
            'warnings':data['warnings'],'editorial_quality':'Requires actual full-text review; not certified by preflight.'}
