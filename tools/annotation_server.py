from __future__ import annotations

import argparse
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "datasets" / "expanded_construction"
MANIFEST = DATASET / "annotation_manifest.json"
HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>施工目标标注台</title><style>
:root{font-family:Arial,"Microsoft YaHei",sans-serif;color:#203040;background:#eef3f6}*{box-sizing:border-box}body{margin:0}.bar{height:56px;background:#102a43;color:#fff;display:flex;align-items:center;gap:18px;padding:0 18px}.bar strong{font-size:16px}.bar span{color:#b8cbd8;font-size:12px}.layout{height:calc(100vh - 56px);display:grid;grid-template-columns:300px minmax(450px,1fr) 280px;gap:14px;padding:14px}.panel{background:#fff;border:1px solid #d7e1e7;border-radius:8px;overflow:hidden}.panel-head{height:48px;border-bottom:1px solid #e5ebef;padding:0 14px;display:flex;align-items:center;justify-content:space-between}.panel-head h2{font-size:14px;margin:0}.muted{color:#748492;font-size:11px}.filters{padding:12px;border-bottom:1px solid #e5ebef;display:grid;gap:8px}.input,.select,.button{height:34px;border:1px solid #cbd8e0;border-radius:5px;background:#fff;padding:0 9px;font:inherit;font-size:12px}.button{cursor:pointer}.button.primary{background:#1769e8;color:#fff;border-color:#1769e8}.button:disabled{opacity:.5;cursor:not-allowed}.list{height:calc(100% - 145px);overflow:auto;padding:8px}.item{width:100%;border:1px solid transparent;background:#fff;border-radius:5px;text-align:left;padding:8px;margin-bottom:5px;cursor:pointer}.item:hover,.item.active{background:#edf5ff;border-color:#9cc0ed}.item b,.item small{display:block}.item b{font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.item small{font-size:10px;color:#748492;margin-top:4px}.done{color:#17834e}.canvas-wrap{height:calc(100% - 48px);display:grid;place-items:center;background:#e8eef2;padding:18px;overflow:auto}.stage{position:relative;display:inline-block;max-width:100%;line-height:0}.stage img{max-width:100%;max-height:calc(100vh - 170px);display:block}.box{position:absolute;border:2px solid #1769e8;background:rgba(23,105,232,.12);cursor:pointer}.box.selected{border-color:#e5484d;background:rgba(229,72,77,.15)}.box span{position:absolute;left:-2px;top:-22px;background:#1769e8;color:#fff;font:11px Arial;padding:4px 6px;white-space:nowrap}.box.selected span{background:#e5484d}.right{padding:12px;overflow:auto}.class-list{display:grid;gap:6px}.class-btn{text-align:left;padding:8px 9px;border:1px solid #d8e2e8;border-radius:5px;background:#fff;cursor:pointer;font-size:11px}.class-btn.active{border-color:#1769e8;background:#edf5ff;color:#1769e8;font-weight:bold}.hint{background:#fff8e8;border:1px solid #f5dca5;border-radius:5px;color:#835d16;font-size:11px;line-height:1.6;padding:9px;margin-bottom:12px}.suggested{display:flex;flex-wrap:wrap;gap:5px;margin:7px 0 14px}.tag{font-size:10px;background:#eef2f5;border-radius:4px;padding:4px 6px}.box-list{display:grid;gap:6px;margin:8px 0 14px}.box-row{display:flex;align-items:center;gap:6px;border:1px solid #e0e7ec;border-radius:4px;padding:6px;font-size:10px}.box-row button{margin-left:auto;border:0;background:transparent;color:#b42318;cursor:pointer}.nav{display:flex;gap:6px;margin-top:12px}.nav .button{flex:1}.footer{position:fixed;bottom:10px;left:50%;transform:translateX(-50%);background:#102a43;color:#fff;border-radius:5px;padding:7px 12px;font-size:11px;display:none}.footer.show{display:block}@media(max-width:1000px){.layout{grid-template-columns:240px 1fr}.right{display:none}}@media(max-width:700px){.layout{display:block;height:auto}.panel{margin-bottom:12px}.list{height:260px}.canvas-wrap{height:560px}.bar span{display:none}}
</style></head><body><header class="bar"><strong>施工目标标注台</strong><span>拖拽框选目标，保存后用于 YOLO 训练</span><span id="counter"></span></header><main class="layout"><section class="panel"><div class="panel-head"><h2>图片队列</h2><span class="muted" id="list-count"></span></div><div class="filters"><input class="input" id="search" placeholder="搜索文件名/阶段"><select class="select" id="split"><option value="all">全部划分</option><option value="train">训练集</option><option value="val">验证集</option><option value="test">测试集</option></select><select class="select" id="status"><option value="all">全部标注状态</option><option value="pending">未标注</option><option value="done">已标注</option></select></div><div class="list" id="list"></div></section><section class="panel"><div class="panel-head"><h2 id="title">选择一张图片</h2><span class="muted" id="meta"></span></div><div class="canvas-wrap"><div class="stage" id="stage"><img id="image" alt=""></div></div></section><section class="panel"><div class="right"><div class="hint">候选类别只用于提示，不会自动生成标签。请只给画面中真实可见的目标画框，目标不清晰时宁可不标。</div><strong>当前类别</strong><div class="class-list" id="classes"></div><div class="muted" style="margin-top:12px">元数据候选类别</div><div class="suggested" id="suggested"></div><div class="box-list" id="boxes"></div><button class="button primary" id="save" disabled>保存当前标注</button><div class="nav"><button class="button" id="prev">上一张</button><button class="button" id="next">下一张</button></div><div class="muted" style="margin-top:12px;line-height:1.6">标注格式：YOLO normalized xywh。训练前还会执行框范围、类别编号和缺失标签检查。</div></div></section></main><div class="footer" id="toast"></div><script>
const state={items:[],filtered:[],current:null,classes:[],activeClass:0,boxes:[],drag:null,selected:-1};const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url,opt){const r=await fetch(url,opt);if(!r.ok)throw Error(await r.text());return r.headers.get('content-type')?.includes('json')?r.json():r}
function toast(s){$('toast').textContent=s;$('toast').classList.add('show');clearTimeout(toast.t);toast.t=setTimeout(()=>$('toast').classList.remove('show'),1800)}
async function load(){const d=await api('/api/manifest');state.items=d.images;state.classes=d.classes;renderClasses();filter();}
function filter(){const q=$('search').value.toLowerCase(),split=$('split').value,status=$('status').value;state.filtered=state.items.filter(x=>(split==='all'||x.split===split)&&(status==='all'||(status==='done')===x.annotated)&&(!q||[x.id,x.phase,x.source_dataset].join(' ').toLowerCase().includes(q)));$('list-count').textContent=state.filtered.length+' 张';renderList();if(!state.current&&state.filtered.length)openItem(state.filtered[0].id)}
function renderList(){$('list').innerHTML=state.filtered.map(x=>`<button class="item ${state.current?.id===x.id?'active':''}" data-id="${esc(x.id)}"><b>${esc(x.filename)}</b><small>${esc(x.source_dataset)} · ${esc(x.split)} · <span class="${x.annotated?'done':''}">${x.annotated?'已标注':'未标注'}</span></small></button>`).join('');document.querySelectorAll('.item').forEach(b=>b.onclick=()=>openItem(b.dataset.id));$('counter').textContent=`${state.filtered.findIndex(x=>x.id===state.current?.id)+1}/${state.filtered.length}`}
function renderClasses(){$('classes').innerHTML=state.classes.map((x,i)=>`<button class="class-btn ${i===state.activeClass?'active':''}" data-class="${i}">${i} · ${esc(x)}</button>`).join('');document.querySelectorAll('.class-btn').forEach(b=>b.onclick=()=>{state.activeClass=+b.dataset.class;renderClasses()})}
async function openItem(id){const item=state.items.find(x=>x.id===id);if(!item)return;state.current=item;state.selected=-1;state.boxes=(await api('/api/labels/'+encodeURIComponent(id))).boxes||[];$('title').textContent=item.filename;$('meta').textContent=`${item.source_dataset} · ${item.split} · ${item.phase||'未分阶段'}`;$('image').src='/media/'+encodeURIComponent(item.split)+'/'+encodeURIComponent(item.filename);$('image').onload=()=>draw();$('suggested').innerHTML=(item.suggested_classes||[]).map(x=>`<span class="tag">${esc(x)}</span>`).join('')||'<span class="muted">无候选提示</span>';$('save').disabled=false;renderList();draw()}
function draw(){const stage=$('stage');stage.querySelectorAll('.box').forEach(x=>x.remove());state.boxes.forEach((b,i)=>{const el=document.createElement('div');el.className='box '+(i===state.selected?'selected':'');el.style.left=(b.x*100)+'%';el.style.top=(b.y*100)+'%';el.style.width=(b.w*100)+'%';el.style.height=(b.h*100)+'%';el.innerHTML=`<span>${state.classes[b.class_id]||b.class_id}</span>`;el.onclick=e=>{e.stopPropagation();state.selected=i;draw()};stage.appendChild(el)});$('boxes').innerHTML=state.boxes.map((b,i)=>`<div class="box-row"><span>${i+1}. ${esc(state.classes[b.class_id]||b.class_id)}</span><span>${Math.round(b.w*100)}%×${Math.round(b.h*100)}%</span><button data-remove="${i}">删除</button></div>`).join('');document.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{state.boxes.splice(+b.dataset.remove,1);state.selected=-1;draw()})}
function point(e){const r=$('stage').getBoundingClientRect();return{x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))}}
$('stage').onmousedown=e=>{if(e.target!==$('image')&&e.target!==$('stage'))return;state.drag=point(e)};$('stage').onmouseup=e=>{if(!state.drag)return;const end=point(e),x=Math.min(state.drag.x,end.x),y=Math.min(state.drag.y,end.y),w=Math.abs(end.x-state.drag.x),h=Math.abs(end.y-state.drag.y);state.drag=null;if(w>.01&&h>.01){state.boxes.push({class_id:state.activeClass,x,y,w,h});state.selected=state.boxes.length-1;draw()}};
async function save(){if(!state.current)return;await api('/api/labels/'+encodeURIComponent(state.current.id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({boxes:state.boxes})});state.current.annotated=state.boxes.length>0;toast('标注已保存');filter()}
$('save').onclick=save;$('search').oninput=filter;$('split').onchange=filter;$('status').onchange=filter;$('prev').onclick=()=>{const i=state.filtered.findIndex(x=>x.id===state.current?.id);if(i>0)openItem(state.filtered[i-1].id)};$('next').onclick=()=>{const i=state.filtered.findIndex(x=>x.id===state.current?.id);if(i<state.filtered.length-1)openItem(state.filtered[i+1].id)};load().catch(e=>toast(e.message));
</script></body></html>'''


def _load_manifest() -> dict:
    if not MANIFEST.exists():
        raise FileNotFoundError("请先运行 training/prepare_expanded_dataset.py")
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for item in payload["images"]:
        item["annotated"] = (ROOT / item["label_path"]).exists() and bool(
            (ROOT / item["label_path"]).read_text(encoding="utf-8").strip()
        )
    return payload


def _item(item_id: str) -> dict:
    for item in _load_manifest()["images"]:
        if item["id"] == item_id:
            return item
    raise KeyError(item_id)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._send(200, "text/html; charset=utf-8", _render_html().encode("utf-8"))
                return
            if parsed.path == "/api/manifest":
                self._send(200, "application/json; charset=utf-8", json.dumps(_load_manifest(), ensure_ascii=False).encode("utf-8"))
                return
            match = re.fullmatch(r"/api/labels/(.+)", parsed.path)
            if match:
                item = _item(match.group(1))
                label_path = ROOT / item["label_path"]
                boxes = []
                if label_path.exists():
                    for line in label_path.read_text(encoding="utf-8").splitlines():
                        parts = line.split()
                        if len(parts) == 5:
                            class_id, cx, cy, width, height = map(float, parts)
                            boxes.append({"class_id": int(class_id), "x": cx - width / 2, "y": cy - height / 2, "w": width, "h": height})
                self._send(200, "application/json; charset=utf-8", json.dumps({"boxes": boxes}).encode("utf-8"))
                return
            match = re.fullmatch(r"/media/([^/]+)/(.+)", parsed.path)
            if match:
                item = next(x for x in _load_manifest()["images"] if x["split"] == match.group(1) and x["filename"] == match.group(2))
                path = ROOT / item["image_path"]
                self._send(200, mimetypes.guess_type(path.name)[0] or "application/octet-stream", path.read_bytes())
                return
            self._send(404, "text/plain; charset=utf-8", b"Not Found")
        except (FileNotFoundError, KeyError, ValueError):
            self._send(404, "text/plain; charset=utf-8", b"Not Found")

    def do_POST(self) -> None:
        match = re.fullmatch(r"/api/labels/(.+)", urlparse(self.path).path)
        if not match:
            self._send(404, "text/plain; charset=utf-8", b"Not Found")
            return
        try:
            item = _item(match.group(1))
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            lines = []
            for box in payload.get("boxes", []):
                class_id = int(box["class_id"])
                x, y, width, height = (float(box[key]) for key in ("x", "y", "w", "h"))
                if not 0 <= class_id < len(_load_manifest()["classes"]):
                    raise ValueError("类别编号无效")
                if width <= 0 or height <= 0 or x < 0 or y < 0 or x + width > 1 or y + height > 1:
                    raise ValueError("标注框超出图片范围")
                lines.append(f"{class_id} {x + width / 2:.6f} {y + height / 2:.6f} {width:.6f} {height:.6f}")
            label_path = ROOT / item["label_path"]
            label_path.parent.mkdir(parents=True, exist_ok=True)
            if lines:
                label_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            elif label_path.exists():
                label_path.unlink()
            self._send(200, "application/json; charset=utf-8", json.dumps({"saved": True, "box_count": len(lines)}).encode("utf-8"))
        except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as exc:
            self._send(400, "application/json; charset=utf-8", json.dumps({"detail": str(exc)}).encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        return


def _render_html() -> str:
    """Add pointer-event handling and an explicit empty-save guard to the compact UI."""
    extra_css = "<style>.stage img{user-select:none;-webkit-user-drag:none;cursor:crosshair}.box-list:empty:after{content:'尚未画框；先选择类别，再在图片上按住左键拖出矩形框';display:block;color:#748492;font-size:11px;line-height:1.6;padding:8px 0}</style>"
    extra_js = r'''<script>
(function installAnnotationInteraction(){
  const stage=document.getElementById('stage'), image=document.getElementById('image'), saveButton=document.getElementById('save');
  if(!stage||!image||!saveButton)return;
  image.draggable=false;
  image.ondragstart=event=>event.preventDefault();
  const updateSaveState=()=>{saveButton.disabled=!state.current;saveButton.textContent=`保存当前标注（${state.boxes.length}个框）`};
  const redraw=window.draw;
  window.draw=function(){redraw();updateSaveState()};
  stage.onpointerdown=event=>{
    if(event.target!==image&&event.target!==stage)return;
    event.preventDefault();
    stage.setPointerCapture?.(event.pointerId);
    state.drag=point(event);
  };
  stage.onpointerup=event=>{
    if(!state.drag)return;
    event.preventDefault();
    const start=state.drag,end=point(event);state.drag=null;
    const x=Math.min(start.x,end.x),y=Math.min(start.y,end.y),w=Math.abs(end.x-start.x),h=Math.abs(end.y-start.y);
    if(w<=.01||h<=.01){toast('框太小，请按住左键拖出目标范围');return}
    state.boxes.push({class_id:state.activeClass,x,y,w,h});state.selected=state.boxes.length-1;draw();toast('已添加1个目标框，请点击保存');
  };
  saveButton.onclick=async()=>{
    if(!state.current)return;
    if(!state.boxes.length){toast('请先在图片上拖出至少一个目标框');return}
    try{await save()}catch(error){toast('保存失败：'+error.message)}
  };
  updateSaveState();
})();
</script>'''
    return HTML.replace("</head>", extra_css + "</head>").replace("</html>", extra_js + "</html>")


def main() -> None:
    global DATASET, MANIFEST
    parser = argparse.ArgumentParser(description="施工目标 YOLO 标注台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    args = parser.parse_args()
    DATASET = args.dataset if args.dataset.is_absolute() else ROOT / args.dataset
    MANIFEST = DATASET / "annotation_manifest.json"
    _load_manifest()
    print(f"标注台地址：http://{args.host}:{args.port}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
