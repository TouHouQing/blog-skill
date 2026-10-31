"""Original local covers and explanatory diagrams, not product screenshots."""
from pathlib import Path
from runtime import digest, font_path, save_json


def lines(draw, text, font, width):
    result, line = [], ''
    for ch in str(text):
        if ch == '\n' or (line and draw.textlength(line+ch, font=font) > width):
            result.append(line)
            line = '' if ch == '\n' else ch
        else:
            line += ch
    if line:
        result.append(line)
    return result


def cover(title, output, summary='', square=False):
    from PIL import Image, ImageDraw, ImageFont
    size = (1080, 1080) if square else (1200, 510)
    image = Image.new('RGB', size, '#f3f1e8')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 19, size[1]), fill='#236b58')
    left, top, width = 82, (185 if square else 92), size[0]-164
    font = None
    for fs in range(74 if square else 66, 27, -2):
        font = ImageFont.truetype(font_path(True), fs)
        wrapped = lines(draw, title, font, width)
        if len(wrapped) <= (5 if square else 3):
            break
    draw.text((left, top-61), 'AI / TECH  ·  实用方法', font=ImageFont.truetype(font_path(), 23), fill='#36705f')
    for index, text in enumerate(wrapped):
        draw.text((left, top+index*(font.size+20)), text, font=font, fill='#193b32')
    y = top+len(wrapped)*(font.size+20)+26
    small = ImageFont.truetype(font_path(), 27 if square else 22)
    for text in lines(draw, summary, small, width)[:3 if square else 2]:
        draw.text((left, y), text, font=small, fill='#52665b')
        y += small.size+12
    draw.line((left, size[1]-47, size[0]-left, size[1]-47), fill='#b7c7b9', width=2)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    save_json(path.with_suffix('.meta.json'), {'kind': 'original_generated_cover', 'sha256': digest(path),
              'size': list(size), 'title': title, 'paid_api_cost': 0})
    return str(path)


def diagram(title, steps, output):
    from PIL import Image, ImageDraw, ImageFont
    if not 2 <= len(steps) <= 8:
        raise ValueError('Use 2–8 steps for a readable diagram.')
    width, height = 1080, 240+len(steps)*270
    image = Image.new('RGB', (width, height), '#f7f8f2')
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(font_path(True), 56)
    heading = ImageFont.truetype(font_path(True), 48)
    body = ImageFont.truetype(font_path(), 42)
    y = 53
    for line in lines(draw, title, title_font, 940):
        draw.text((70, y), line, font=title_font, fill='#193b32')
        y += 65
    y = max(190, y+35)
    for i, item in enumerate(steps):
        name, _, detail = item.partition('|')
        draw.rounded_rectangle((65,y,1015,y+210), radius=14, fill='white', outline='#cfdbcd', width=2)
        draw.text((90,y+25), f'{i+1:02}', font=heading, fill='#36705f')
        draw.text((174,y+23), name, font=heading, fill='#193b32')
        for n, line in enumerate(lines(draw, detail, body, 795)[:2]):
            draw.text((174,y+92+n*52), line, font=body, fill='#58675d')
        if i < len(steps)-1:
            draw.line((540,y+220,540,y+253), fill='#87a493', width=4)
            draw.polygon([(530,y+247),(550,y+247),(540,y+259)], fill='#87a493')
        y += 270
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    save_json(path.with_suffix('.meta.json'), {'kind': 'original_explanatory_diagram', 'sha256': digest(path),
              'title': title, 'steps': steps, 'paid_api_cost': 0})
    return str(path)
