/** Local-only Markdown conversion, syntax highlighting and CSS inlining. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, '.runtime/node/package.json'));
const {Marked} = require('marked');
const {default:markedCjkFriendly} = await import(pathToFileURL(require.resolve('marked-cjk-friendly')).href);
const hljs = require('highlight.js');
const juice = require('juice');
const escape = value => String(value).replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const safeUrl = value => /^(?:https?:\/\/|mailto:|#|assets\/)/i.test(value);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = path.resolve(input.output);
const theme = fs.readFileSync(path.join(root, 'assets/article.css'), 'utf8');
const codeTheme = fs.readFileSync(require.resolve('highlight.js/styles/github.css'), 'utf8');
const labels = {blog:'博客', wechat:'微信公众号', post:'社区帖子'};
const files = [];

function markdownHtml(source) {
  const ids = new Map();
  const md = new Marked({gfm:true, breaks:false});
  const cjk = markedCjkFriendly();
  // The plugin's del hook assumes newer Marked internals despite its >=15 peer range.
  // Retain Marked 15's own GFM deletion tokenizer and use the CJK emphasis hook.
  delete cjk.tokenizer.del;
  md.use(cjk);
  md.use({renderer:{
    html({text}) { return escape(text); },
    paragraph({tokens}) {
      const content=this.parser.parseInline(tokens);
      // A figure is already a block; wrapping it in p creates empty paragraphs on paste.
      return tokens.length===1&&tokens[0].type==='image' ? content+'\n' : '<p>'+content+'</p>\n';
    },
    code({text, lang}) {
      const language = (lang || '').trim().split(/\s/)[0];
      if (/^(mermaid|plantuml|math)$/.test(language)) throw new Error('Convert diagrams/formulas to a local image asset before rendering.');
      const rendered = language && hljs.getLanguage(language) ? hljs.highlight(text,{language}).value : escape(text);
      return `<pre><code class="hljs${language?' language-'+escape(language):''}">${rendered}</code></pre>`;
    },
    link({href, title, tokens}) {
      if (!safeUrl(href)) throw new Error('Unsupported link target: '+href);
      return `<a href="${escape(href)}"${title?' title="'+escape(title)+'"':''}>${this.parser.parseInline(tokens)}</a>`;
    },
    image({href, text, title}) {
      if (!href.startsWith('assets/')) throw new Error('Article image must be a bundled asset: '+href);
      return `<figure><img src="${escape(href)}" alt="${escape(text)}"${title?' title="'+escape(title)+'"':''}/>${text?`<figcaption>${escape(text)}</figcaption>`:''}</figure>`;
    },
    heading({depth,tokens}) {
      const content=this.parser.parseInline(tokens);
      let id=content.replace(/<[^>]*>/g,'').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,'-').replace(/^-|-$/g,'') || 'section';
      const n=(ids.get(id)||0)+1; ids.set(id,n); if(n>1) id+='-'+n;
      return `<h${depth} id="${escape(id)}">${content}</h${depth}>`;
    },
    table({header,rows}) {
      const row=(cells,tag)=>'<tr>'+cells.map(cell=>`<${tag}>${this.parser.parseInline(cell.tokens)}</${tag}>`).join('')+'</tr>';
      return `<section class="table-scroll"><table><thead>${row(header,'th')}</thead><tbody>${rows.map(cells=>row(cells,'td')).join('')}</tbody></table></section>`;
    }
  }});
  const body=source.replace(/^\s*#\s+[^\n]+\n/, '');
  return md.parse(body);
}

function fragment(source) {
  const doc=`<html><head><style>${codeTheme}\n${theme}</style></head><body><section class="article" id="article">${markdownHtml(source)}</section></body></html>`;
  const inlined=juice(doc,{removeStyleTags:true,preserveMediaQueries:false,applyWidthAttributes:false,applyHeightAttributes:false});
  const match=inlined.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
  if(!match) throw new Error('Missing rendered article body.');
  return match[1];
}

const pageCss=`*{box-sizing:border-box}body{margin:0;background:#f4f5f1;color:#1d322d;font-family:"Microsoft YaHei","PingFang SC",sans-serif}main{max-width:800px;margin:30px auto;background:white;padding:40px 44px;border:1px solid #e2e6df}header h1{font-size:29px;line-height:1.5;margin:14px 0 20px}header p{font-size:15px;line-height:1.8;color:#62746b}.tools{max-width:800px;margin:18px auto;padding:0 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}.tools a{color:#236f5d;font-size:14px}button{border:0;background:#205d4b;color:white;font:14px "Microsoft YaHei",sans-serif;padding:11px 16px;border-radius:5px;cursor:pointer}.hint{font-size:12px;line-height:1.7;color:#61756b}.tag{font-size:12px;letter-spacing:2px;color:#3d7969}.hero{width:100%;height:auto;display:block;margin-bottom:24px}.links{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:16px}.links a{display:block;color:#205d4b;border-top:2px solid #205d4b;padding:16px 0;text-decoration:none}.links small{display:block;color:#62746b;line-height:1.8;margin-top:8px}footer{color:#6f8076;font-size:12px;line-height:1.8;border-top:1px solid #e2e6df;padding-top:20px;margin-top:32px}code{overflow-wrap:anywhere}@media(max-width:600px){main{margin:0;border:0;padding:28px 20px}header h1{font-size:25px}.tools{margin:12px 0}.article h2{font-size:20px!important}.links{grid-template-columns:1fr}}`;
function embeddedImages(body) {
  return body.replace(/\bsrc="(assets\/[^"<>]+)"/g, (_, relative) => {
    const file=path.resolve(out,relative);
    if(!file.startsWith(path.join(out,'assets')+path.sep)) throw new Error('Image outside the asset package.');
    const mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.gif':'image/gif'}[path.extname(file).toLowerCase()];
    if(!mime) throw new Error('Unsupported clipboard image: '+relative);
    return `src="data:${mime};base64,${fs.readFileSync(file).toString('base64')}"`;
  });
}
const copyScript=`document.getElementById('copy').addEventListener('click',async()=>{
  const el=document.getElementById('article');
  const html=document.getElementById('clipboard-article').innerHTML;
  const text=el.innerText;
  const fallback=()=>{
    const selection=window.getSelection();
    const saved=selection.rangeCount?selection.getRangeAt(0).cloneRange():null;
    const range=document.createRange();range.selectNodeContents(el);selection.removeAllRanges();selection.addRange(range);
    let supplied=false;
    const handler=event=>{if(!event.clipboardData)return;event.clipboardData.setData('text/html',html);event.clipboardData.setData('text/plain',text);event.preventDefault();supplied=true;};
    document.addEventListener('copy',handler);
    try{if(!document.execCommand('copy')||!supplied)throw new Error('copy denied');}
    finally{document.removeEventListener('copy',handler);selection.removeAllRanges();if(saved)selection.addRange(saved);}
  };
  try{
    if(navigator.clipboard&&window.ClipboardItem){
      try{await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([html],{type:'text/html'}),'text/plain':new Blob([text],{type:'text/plain'})})]);}
      catch(error){fallback();}
    }else{fallback();}
    document.getElementById('status').textContent='正文已复制，已包含 '+el.querySelectorAll('img').length+' 张图片，可直接粘贴。';
  }catch(error){document.getElementById('status').textContent='复制被浏览器阻止。请打开“离线图文”，选中正文后复制。';}
});`;
const imageCss=`#article img{cursor:zoom-in}#image-viewer{width:min(96vw,1400px);max-width:96vw;max-height:94vh;padding:12px;border:0;border-radius:5px;background:#f4f5f1}#image-viewer::backdrop{background:rgba(0,0,0,.75)}.image-actions{display:flex;gap:8px;margin-bottom:12px}.image-scroll{max-height:calc(90vh - 70px);overflow:auto}.image-scroll img{display:block;max-width:none;height:auto}`;
const imageScript=`document.querySelectorAll('#article img').forEach(original=>original.addEventListener('click',()=>{
  const viewer=document.createElement('dialog');viewer.id='image-viewer';viewer.setAttribute('aria-label','查看完整截图');
  viewer.innerHTML='<div class="image-actions"><button type="button" data-action="fit">适应窗口</button><button type="button" data-action="actual">原尺寸</button><button type="button" data-action="close">关闭</button></div><div class="image-scroll"><img alt=""></div>';
  const picture=viewer.querySelector('img');picture.src=original.src;picture.alt=original.alt;picture.style.width='100%';
  viewer.querySelector('[data-action="fit"]').addEventListener('click',()=>{picture.style.width='100%';});
  viewer.querySelector('[data-action="actual"]').addEventListener('click',()=>{picture.style.width=picture.naturalWidth+'px';});
  viewer.querySelector('[data-action="close"]').addEventListener('click',()=>viewer.close());
  viewer.addEventListener('close',()=>viewer.remove());document.body.append(viewer);viewer.showModal();
}));`;

for(const [platform, data] of Object.entries(input.articles)) {
  if(!labels[platform]) throw new Error('Unknown platform: '+platform);
  const body=fragment(data.markdown);
  let clipboard='';
  if(platform==='wechat') {
    fs.writeFileSync(path.join(out,'wechat-body.html'),body); files.push('wechat-body.html');
    const embedded=embeddedImages(body);
    clipboard='<template id="clipboard-article">'+embedded+'</template>';
    fs.writeFileSync(path.join(out,'wechat-copy.html'),'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(data.title)+'</title></head><body>'+embedded+'</body></html>');
    files.push('wechat-copy.html');
  }
  const tools=`<nav class="tools"><a href="index.html">返回交付首页</a>${platform==='wechat'?'<button id="copy" type="button">复制公众号正文排版</button><a href="wechat-copy.html" target="_blank" rel="noopener">离线图文</a><span class="hint" id="status">复制会携带实际图片，可连同正文粘贴。</span>':''}<span class="hint">点击截图可放大查看。</span></nav>`;
  const doc=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="${escape(data.summary)}"><title>${escape(data.title)}</title><style>${pageCss}\n${imageCss}</style></head><body>${tools}<main><header><div class="tag">${labels[platform]}</div><h1>${escape(data.title)}</h1>${platform==='blog'&&data.summary?`<p>${escape(data.summary)}</p>`:''}</header>${body}</main>${clipboard}<script>${imageScript}${platform==='wechat'?copyScript:''}</script></body></html>`;
  fs.writeFileSync(path.join(out,platform+'.html'),doc);files.push(platform+'.html');
}
const entries=Object.entries(input.articles).map(([platform,data])=>`<a href="${platform}.html">${labels[platform]} · 阅读成稿<small>${escape(data.title)}</small></a>`).join('');
const index=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(input.title)}</title><style>${pageCss}</style></head><body><main><img class="hero" src="cover-wide.png" alt="文章封面"><header><div class="tag">图文成品</div><h1>${escape(input.title)}</h1><p>${escape(input.summary||'')}</p></header><div class="links">${entries}</div><footer>Markdown 与配图已随包提供。微信公众号页面的复制按钮包含正文排版和实际图片；离线图文也已内嵌图片。此页面为本地成品预览。</footer></main></body></html>`;
fs.writeFileSync(path.join(out,'index.html'),index);files.push('index.html');
console.log(JSON.stringify({files,renderer:'marked + marked-cjk-friendly + highlight.js + juice',paid_apis_enabled:false}));
