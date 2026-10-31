"""Annotate real screenshots without cropping, resizing or recreating their UI."""
from datetime import datetime, timezone
import math
from pathlib import Path
from runtime import digest, save_json


def painted(source, operations):
    from PIL import ImageDraw
    image=source.convert('RGBA').copy()
    draw=ImageDraw.Draw(image)
    if not operations:
        raise ValueError('Provide at least one actual screenshot annotation.')
    for item in operations:
        kind=item.get('type')
        points=item.get('box' if kind in ('rect','redact') else 'points')
        if kind not in ('rect','arrow','redact') or not isinstance(points,list) or len(points)!=4:
            raise ValueError('Only rect, arrow and privacy-redact annotations are supported.')
        if any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in points):
            raise ValueError('Annotation coordinates must be finite numbers.')
        x0,y0,x1,y1=points
        if not (0<=x0<image.width and 0<=x1<image.width and 0<=y0<image.height and 0<=y1<image.height):
            raise ValueError('Annotation coordinates must stay inside the source screenshot.')
        stroke=item.get('width',max(3,round(min(image.size)*.007)))
        if not isinstance(stroke,int) or not 1<=stroke<=max(image.size):
            raise ValueError('Annotation stroke width is invalid.')
        if kind in ('rect','redact'):
            if x1<=x0 or y1<=y0:
                raise ValueError('Annotation box must have positive width and height.')
            draw.rectangle(points,fill='#252525' if kind=='redact' else None,
                           outline=None if kind=='redact' else '#F33E48',width=stroke)
        else:
            length=math.hypot(x1-x0,y1-y0)
            if length<1:
                raise ValueError('An arrow needs a nonzero direction.')
            ux,uy=(x1-x0)/length,(y1-y0)/length
            head=min(length*.3,stroke*4)
            base_x,base_y=x1-head*ux,y1-head*uy
            draw.line(points,fill='#F33E48',width=stroke)
            draw.polygon([(x1,y1),(base_x-head*.48*uy,base_y+head*.48*ux),
                          (base_x+head*.48*uy,base_y-head*.48*ux)],fill='#F33E48')
    return image


def annotate(input_path, output, source_asset_id, operations):
    from PIL import Image
    source_path=Path(input_path).resolve()
    target=Path(output).resolve()
    if source_path==target:
        raise ValueError('Keep the original screenshot; output must use a different path.')
    if not source_asset_id:
        raise ValueError('Record the registered raw screenshot asset ID.')
    with Image.open(source_path) as source:
        result=painted(source,operations)
    target.parent.mkdir(parents=True,exist_ok=True)
    result.save(target,format='PNG')
    record={'method':'annotated-screenshot','sha256':digest(target),
            'source_asset_id':source_asset_id,'source_sha256':digest(source_path),
            'dimensions':list(result.size),'operations':operations,
            'checked_at':datetime.now(timezone.utc).isoformat(),
            'changes':'Arrow/rectangle guidance and explicit privacy masking only; canvas size and all other pixels retained.'}
    save_json(target.with_suffix('.capture.json'),record)
    return record


def validate_derivation(source_path, target_path, record):
    from PIL import Image
    if record.get('source_sha256')!=digest(source_path):
        raise ValueError('Annotated screenshot source lineage changed.')
    with Image.open(source_path) as source, Image.open(target_path) as target:
        if source.size!=target.size or list(source.size)!=record.get('dimensions'):
            raise ValueError('Annotated screenshots must retain the full original canvas.')
        expected=painted(source,record.get('operations',[]))
        if expected.tobytes()!=target.convert('RGBA').tobytes():
            raise ValueError('Screenshot pixels changed beyond the recorded annotations.')
