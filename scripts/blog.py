"""Chinese article production helpers. Codex researches, writes and reviews."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
from runtime import ROOT, emit, node, read_json, run, save_json


def doctor():
    modules = {name:importlib.util.find_spec(name) is not None for name in ('PIL','bs4','playwright','yaml')}
    errors = []
    try:
        executable = node()
        version = run([executable,'--version']).stdout.strip()
        for name in ('marked','marked-cjk-friendly','highlight.js','juice'):
            if not (ROOT/'.runtime/node/node_modules'/name).is_dir():
                errors.append('Missing local Node dependency: '+name)
    except Exception as error:
        executable, version = None, None
        errors.append(str(error))
    browser_ready = False
    if modules['playwright']:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
            browser_ready = True
        except Exception as error:
            errors.append('Browser: '+str(error)[:300])
    return {'ready':all(modules.values()) and not errors and browser_ready,'python':sys.executable,
            'node':executable,'node_version':version,'modules':modules,'browser_ready':browser_ready,
            'errors':errors,'paid_apis_enabled':False,'requires_video_tools':False,
            'requires_other_skills':False,'publication_integrations':'No account access or posting is implemented by these local helpers.'}


def initialize(workspace, title, platforms):
    root=Path(workspace).resolve()
    if (root/'project.json').exists():
        raise ValueError('Project already exists; choose a new task directory.')
    requested=list(dict.fromkeys(x.strip() for x in platforms.split(',') if x.strip()))
    if not requested or set(requested)-{'blog','wechat','post'}:
        raise ValueError('Choose blog,wechat,post.')
    (root/'drafts').mkdir(parents=True,exist_ok=True)
    (root/'assets').mkdir(exist_ok=True)
    save_json(root/'brief.json',{'title':title,'audience':'中文读者','purpose':'','platforms':requested})
    save_json(root/'research.json',{'searches':[],'sources':[],'claims':[]})
    platform_specs={name:{'file':'drafts/'+name+'.md'} for name in requested}
    if 'wechat' in platform_specs:
        platform_specs['wechat'].update(include_cover=True,summary_max_chars=120)
    save_json(root/'project.json',{'title':title,'summary':'','audience':'中文读者','purpose':'',
              'approval_status':'draft','research_mode':'web','research_file':'research.json','review_file':'review.json',
              'platforms':platform_specs,'assets':[],'evidence_map':[]})
    return {'workspace':str(root),'project':str(root/'project.json'),'status':'initialized_for_agent_authoring'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor')
    p=sub.add_parser('init');p.add_argument('--workspace',required=True);p.add_argument('--title',required=True);p.add_argument('--platforms',default='wechat')
    p=sub.add_parser('discover');p.add_argument('--output',required=True);p.add_argument('--hours',type=int,default=72);p.add_argument('--limit',type=int,default=20);p.add_argument('--feeds');p.add_argument('--keywords',help='Regex topic filter; default AI, * accepts all feed topics.');p.add_argument('--hotlists',default='')
    for name in ('fetch','capture'):
        p=sub.add_parser(name);p.add_argument('--url',required=True);p.add_argument('--output',required=True)
        if name=='capture':p.add_argument('--selector');p.add_argument('--wait-selector');p.add_argument('--clip-height',type=int);p.add_argument('--width',type=int,default=1280);p.add_argument('--height',type=int,default=850);p.add_argument('--full-page',action='store_true',help='Capture the entire page or selected element without height clipping.')
    p=sub.add_parser('cover');p.add_argument('--title',required=True);p.add_argument('--summary',default='');p.add_argument('--output',required=True);p.add_argument('--square',action='store_true')
    p=sub.add_parser('diagram');p.add_argument('--title',required=True);p.add_argument('--step',action='append',required=True,help='Repeat: label|explanation');p.add_argument('--output',required=True)
    p=sub.add_parser('annotate');p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--source-asset',required=True);p.add_argument('--operations',required=True,help='JSON file containing rect, arrow or privacy-redact operations in image-pixel coordinates.')
    p=sub.add_parser('preflight');p.add_argument('--project',required=True);p.add_argument('--stage',choices=['draft','produce'],default='produce');p.add_argument('--output')
    p=sub.add_parser('review-hashes');p.add_argument('--project',required=True)
    for name in ('render','finalize'):
        p=sub.add_parser(name);p.add_argument('--project',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('verify');p.add_argument('--output',required=True)
    p=sub.add_parser('feedback');p.add_argument('--workspace',required=True);p.add_argument('--before',required=True);p.add_argument('--after',required=True);p.add_argument('--note',required=True);p.add_argument('--source',choices=['user','editorial'],default='editorial')
    p=sub.add_parser('brief');p.add_argument('--workspace',required=True);p.add_argument('--limit',type=int,default=5)
    p=sub.add_parser('metrics');p.add_argument('--workspace',required=True);p.add_argument('--file',required=True)
    args=parser.parse_args()
    if args.command=='doctor':
        data=doctor();emit('doctor',**data);return 0 if data['ready'] else 2
    if args.command=='init':data=initialize(args.workspace,args.title,args.platforms)
    elif args.command=='discover':
        from collect import collect
        result=collect(args.output,args.hours,args.limit,args.feeds,args.hotlists,keywords=args.keywords)
        data={'candidates':len(result['candidates']),'source_errors':result['source_errors'],'output':args.output}
    elif args.command in ('fetch','capture'):
        from sources import fetch,capture
        data=fetch(args.url,args.output) if args.command=='fetch' else capture(args.url,args.output,args.selector,args.width,args.height,args.wait_selector,args.clip_height,args.full_page)
    elif args.command in ('cover','diagram'):
        from images import cover,diagram
        path=cover(args.title,args.output,args.summary,args.square) if args.command=='cover' else diagram(args.title,args.step,args.output)
        data={'path':path}
    elif args.command=='annotate':
        from annotations import annotate
        data=annotate(args.input,args.output,args.source_asset,read_json(args.operations))
    elif args.command=='preflight':
        from project import preflight
        data=preflight(args.project,args.stage)
        if args.output:save_json(args.output,data)
    elif args.command=='review-hashes':
        from project import load
        data={'content_hashes':load(args.project,'draft')['hashes']}
    elif args.command in ('render','verify','finalize'):
        from production import render,verify,finalize
        data={'render':lambda:render(args.project,args.output),'verify':lambda:verify(args.output),'finalize':lambda:finalize(args.project,args.output)}[args.command]()
    elif args.command in ('feedback','brief','metrics'):
        from state import feedback,brief,metrics
        if args.command=='feedback':data=feedback(args.workspace,args.before,args.after,args.note,args.source)
        elif args.command=='brief':data=brief(args.workspace,args.limit)
        else:data=metrics(args.workspace,args.file)
    emit(args.command,**data)
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        emit('error',message=str(error))
        raise SystemExit(1)
