"""Local evidence-backed feedback and metrics; no platform account integration."""
from datetime import datetime, timezone
import difflib
import hashlib
from pathlib import Path
from runtime import digest, read_json, save_json


def feedback(workspace, before, after, note, source='editorial'):
    root = Path(workspace).resolve()
    if source not in ('user','editorial'):
        raise ValueError('Feedback source must be user or editorial.')
    left, right = Path(before).read_text('utf-8-sig'), Path(after).read_text('utf-8-sig')
    if left == right:
        raise ValueError('Feedback needs an actual textual change.')
    stamp = datetime.now(timezone.utc).isoformat()
    key = hashlib.sha256((left+right+stamp).encode()).hexdigest()[:16]
    folder = root/'feedback'/key
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'before.md').write_text(left,'utf-8')
    (folder/'after.md').write_text(right,'utf-8')
    difference = ''.join(difflib.unified_diff(left.splitlines(True),right.splitlines(True),fromfile='before',tofile='after'))
    (folder/'change.diff').write_text(difference,'utf-8')
    record = {'id':key,'recorded_at':stamp,'source':source,'note':note,
              'before_sha256':digest(folder/'before.md'),'after_sha256':digest(folder/'after.md'),
              'files':{'before':f'feedback/{key}/before.md','after':f'feedback/{key}/after.md','diff':f'feedback/{key}/change.diff'},
              'automatic_profile_update':False}
    save_json(folder/'record.json',record)
    return record


def brief(workspace, limit=5):
    root = Path(workspace).resolve()
    rows = [read_json(p) for p in (root/'feedback').glob('*/record.json')]
    rows.sort(key=lambda x:x['recorded_at'],reverse=True)
    profile = read_json(root/'profile.json') if (root/'profile.json').is_file() else {}
    observations=[read_json(p) for p in (root/'metrics').glob('*.json')]
    observations.sort(key=lambda x:x['observed_at'],reverse=True)
    return {'workspace':str(root),'profile':profile,'feedback':rows[:max(1,min(limit,20))],
            'performance_observations':observations[:max(1,min(limit,20))],
            'comparison_rule':'Compare only observations with the same platform and window_hours; preserve evidence and uncertainty.',
            'note':'Feedback is contextual evidence. Do not promote every edit into a universal writing rule.'}


def metrics(workspace, file):
    root = Path(workspace).resolve()
    item = read_json(file)
    for key in ('article_id','platform','observed_at','window_hours','evidence'):
        if not item.get(key):
            raise ValueError('Metrics require '+key)
    if item['platform'] not in ('blog','wechat','post') or float(item['window_hours'])<=0:
        raise ValueError('Use a supported platform and a positive observation window.')
    datetime.fromisoformat(item['observed_at'].replace('Z','+00:00'))
    counts = item.get('counts',{})
    if not counts or any(isinstance(value,bool) or not isinstance(value,(int,float)) or value<0 for value in counts.values()):
        raise ValueError('Counts must be real supplied nonnegative numbers.')
    folder=root/'metrics'
    folder.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256(__import__('json').dumps(item,sort_keys=True).encode()).hexdigest()[:16]
    save_json(folder/(key+'.json'),item)
    peers=[read_json(p) for p in folder.glob('*.json')]
    peers=[row for row in peers if row['platform']==item['platform'] and float(row['window_hours'])==float(item['window_hours'])]
    return {'recorded':key,'comparable_observations':len(peers),'platform':item['platform'],
            'observations':[{key:row[key] for key in ('article_id','observed_at','counts','evidence')} for row in peers[-10:]],
            'window_hours':item['window_hours'],'note':'Observations do not establish which writing choice caused an outcome.'}
