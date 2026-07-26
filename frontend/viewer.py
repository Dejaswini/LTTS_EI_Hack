# frontend/viewer.py — canvas-based drawing viewer with highlight overlay
import json, streamlit.components.v1 as components

BACKEND = "http://localhost:8000"

def drawing_canvas(doc_id: str, drawing_id: str, bbox: list = None,
                   nat_w: int = 0, nat_h: int = 0, height: int = 650):
    """
    Renders the drawing image with an HTML5 canvas highlight overlay.
    bbox = [x1,y1,x2,y2] in original image coordinates.
    nat_w/nat_h = original image dimensions (for scaling).
    No image regeneration — canvas draws rectangle on top of <img>.
    """
    img_url  = f"{BACKEND}/image/{doc_id}/{drawing_id}"
    bbox_js  = json.dumps(bbox) if bbox else "null"
    nat_js   = json.dumps({"w": nat_w, "h": nat_h})

    html = f"""
<!DOCTYPE html><html><head>
<style>
 body{{margin:0;background:#0a0a14;}}
 #wrap{{position:relative;display:inline-block;width:100%;}}
 #dwg{{width:100%;display:block;border-radius:8px;}}
 #cv{{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;}}
 #dbg{{font-family:monospace;font-size:11px;color:#64748b;padding:4px 8px;background:#0d1117;border-radius:0 0 6px 6px;}}
</style></head><body>
<div id="wrap">
  <img id="dwg" src="{img_url}" onload="onLoad()" onerror="this.alt='Image not available'"/>
  <canvas id="cv"></canvas>
</div>
<div id="dbg" id="log">Loading…</div>
<script>
var BBOX  = {bbox_js};
var NAT   = {nat_js};
function log(msg){{ document.getElementById('dbg').innerText = msg; }}
function onLoad(){{
  var img = document.getElementById('dwg');
  var cv  = document.getElementById('cv');
  var dw  = img.offsetWidth,  dh  = img.offsetHeight;
  var nw  = NAT.w || img.naturalWidth;
  var nh  = NAT.h || img.naturalHeight;
  cv.width  = dw;
  cv.height = dh;
  if(!BBOX){{ log('OCR DB ready — click a field to highlight'); return; }}
  var sx = dw / nw, sy = dh / nh;
  var x1=BBOX[0]*sx, y1=BBOX[1]*sy;
  var rw=(BBOX[2]-BBOX[0])*sx, rh=(BBOX[3]-BBOX[1])*sy;
  var ctx = cv.getContext('2d');
  ctx.clearRect(0,0,dw,dh);
  ctx.fillStyle='rgba(34,197,94,0.18)';
  ctx.fillRect(x1,y1,rw,rh);
  ctx.strokeStyle='#22c55e';
  ctx.lineWidth=3;
  ctx.strokeRect(x1,y1,rw,rh);
  // Corner ticks
  var t=Math.min(18,rw/4,rh/4);
  ctx.lineWidth=4;
  [[x1,y1,1,1],[x1+rw,y1,-1,1],[x1,y1+rh,1,-1],[x1+rw,y1+rh,-1,-1]].forEach(function(c){{
    ctx.beginPath(); ctx.moveTo(c[0],c[1]); ctx.lineTo(c[0]+c[2]*t,c[1]); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(c[0],c[1]); ctx.lineTo(c[0],c[1]+c[3]*t); ctx.stroke();
  }});
  // Scroll to region
  var absY = img.getBoundingClientRect().top + window.scrollY + y1;
  window.scrollTo({{top: absY - 100, behavior:'smooth'}});
  log('OCR coords: '+JSON.stringify(BBOX)+
      ' | Scale: '+sx.toFixed(3)+'x'+sy.toFixed(3)+
      ' | Display: ['+Math.round(x1)+','+Math.round(y1)+','+Math.round(x1+rw)+','+Math.round(y1+rh)+']'+
      ' | Nat: '+nw+'x'+nh+' | Disp: '+dw+'x'+dh);
}}
</script></body></html>"""
    components.html(html, height=height, scrolling=True)
