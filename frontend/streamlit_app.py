# frontend/streamlit_app.py — CAD Drawing Copilot v3.2
import json, requests, streamlit as st
import pandas as pd
from viewer import drawing_canvas

st.set_page_config(page_title="CAD Drawing Copilot", page_icon="🔧", layout="wide")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.stApp{background:linear-gradient(135deg,#0a0a14,#111827,#0f172a);color:#e2e8f0;}
[data-testid="stSidebar"]{background:#0d1117;border-right:1px solid #1e293b;}
.hdr{background:linear-gradient(135deg,rgba(99,102,241,.15),rgba(168,85,247,.08));border:1px solid rgba(99,102,241,.3);border-radius:14px;padding:1.4rem 2rem;margin-bottom:1rem;}
.hdr h1{font-size:1.75rem;font-weight:700;margin:0;background:linear-gradient(90deg,#818cf8,#c084fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.sec{font-size:.9rem;font-weight:600;color:#a5b4fc;border-bottom:1px solid rgba(99,102,241,.2);padding-bottom:.2rem;margin:.8rem 0 .4rem;}
.chat-u{background:rgba(99,102,241,.15);border-left:3px solid #6366f1;border-radius:8px;padding:.5rem .9rem;margin:.3rem 0;}
.chat-b{background:rgba(16,185,129,.1);border-left:3px solid #10b981;border-radius:8px;padding:.5rem .9rem;margin:.3rem 0;}
.stButton>button{background:linear-gradient(135deg,#6366f1,#8b5cf6)!important;color:#fff!important;border:none!important;border-radius:8px!important;font-weight:600!important;}
.stTabs [aria-selected="true"]{color:#818cf8!important;border-bottom-color:#6366f1!important;}
</style>""", unsafe_allow_html=True)

BACKEND = "http://localhost:8000"

for k,v in {"company":"LTTS","checklist_id":"","checklist_reqs":[],"doc_id":"","drawings":[],
            "active_drawing":"","drawing_data":{},"chat_history":{},"chat_msgs":{},
            "hl_bbox":None,"hl_text":"","hl_ocr_id":"","hl_nat_w":0,"hl_nat_h":0}.items():
    if k not in st.session_state: st.session_state[k]=v

def api(m,p,**kw):
    try: return getattr(requests,m)(f"{BACKEND}{p}",timeout=300,**kw)
    except requests.exceptions.ConnectionError: st.error("❌ Backend offline"); return None

def sc(s): return "#10b981" if s>=80 else ("#f59e0b" if s>=50 else "#ef4444")
def stc(s): return {"✓":"#10b981","✗":"#ef4444","NA":"#64748b"}.get(s,"#94a3b8")

def get_data(did):
    if did not in st.session_state.drawing_data:
        r=api("get",f"/drawing/{st.session_state.doc_id}/{did}")
        if r and r.status_code==200: st.session_state.drawing_data[did]=r.json()
    return st.session_state.drawing_data.get(did,{})

def do_highlight(doc_id, drawing_id, field_name="", ocr_id=""):
    """Fetch bbox coords from backend, store in session state. No image gen."""
    params={"doc_id":doc_id,"drawing_id":drawing_id}
    if ocr_id: params["ocr_id"]=ocr_id
    elif field_name: params["field_name"]=field_name
    r=api("get","/highlight",params=params)
    if r and r.status_code==200:
        d=r.json()
        st.session_state.hl_bbox   = d.get("bbox")
        st.session_state.hl_text   = d.get("text","")
        st.session_state.hl_ocr_id = d.get("id","")
        st.session_state.hl_nat_w  = d.get("nat_w",0)
        st.session_state.hl_nat_h  = d.get("nat_h",0)
        return True
    elif r:
        try: st.warning(f"No highlight: {r.json().get('detail','')}")
        except: st.warning("No coordinates found")
    return False

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Setup")
    r=api("get","/checklist/companies")
    companies=r.json()["companies"] if r else ["LTTS","Bosch","Hyundai","TVS","Ashok Leyland","Custom Company"]
    st.session_state.company=st.selectbox("🏢 Company",companies)
    st.divider()
    st.markdown("**📋 Checklist**")
    clf=st.file_uploader("PDF/Excel/CSV/DOCX",type=["pdf","xlsx","xls","csv","docx"],label_visibility="collapsed")
    if clf and st.button("📤 Upload Checklist",use_container_width=True):
        with st.spinner("Parsing…"):
            r=api("post","/checklist/upload",data={"company_name":st.session_state.company},files={"file":(clf.name,clf)})
            if r and r.status_code==200:
                d=r.json(); st.session_state.checklist_id=d["checklist_id"]
                st.session_state.checklist_reqs=d["requirements"]
                st.success(f"✅ {d['total']} requirements")
            elif r: st.error(r.json().get("detail",""))
    if st.session_state.checklist_id:
        st.caption(f"Checklist: `{st.session_state.checklist_id}` ({len(st.session_state.checklist_reqs)} req.)")
    st.divider()
    ar=api("get","/ai/status")
    if ar and ar.status_code==200:
        d=ar.json()
        if d.get("configured"): st.success(f"✅ AI: {d['deployment']}")
        else: st.warning("⚠️ AI not configured\nSet LTTS_API_KEY in backend/.env")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""<div class="hdr"><h1>🔧 CAD Drawing AI Co-Pilot</h1>
<p>Canvas Highlight Engine · OCR Coordinate DB · Engineering Rule Engine · No image regeneration</p></div>""",unsafe_allow_html=True)

# ── Upload ────────────────────────────────────────────────────────────────────
st.markdown('<div class="sec">📁 Upload Drawing</div>',unsafe_allow_html=True)
c1,c2=st.columns([3,1])
with c1:
    dfile=st.file_uploader("PDF / Image / ZIP",type=["pdf","png","jpg","jpeg","tiff","bmp","zip"],label_visibility="collapsed")
with c2:
    if dfile and dfile.name.lower().endswith((".png",".jpg",".jpeg")):
        from PIL import Image; dfile.seek(0); st.image(Image.open(dfile),use_column_width=True); dfile.seek(0)

if dfile and st.button("🚀 Process Drawing(s)",use_container_width=True):
    with st.spinner("OCR → OCR DB → AI Extract → Rule Engine → Validate…"):
        dfile.seek(0)
        r=api("post","/upload-drawing",
              data={"company_name":st.session_state.company,"checklist_id":st.session_state.checklist_id},
              files={"file":(dfile.name,dfile)})
        if r and r.status_code==200:
            d=r.json(); st.session_state.doc_id=d["doc_id"]
            st.session_state.drawings=d["drawings"]; st.session_state.drawing_data={}
            st.session_state.chat_history={}; st.session_state.chat_msgs={}
            st.session_state.hl_bbox=None
            if d["drawings"]: st.session_state.active_drawing=d["drawings"][0]["drawing_id"]
            st.success(f"✅ {d['total']} drawing(s) — Doc: `{d['doc_id']}`"); st.rerun()
        elif r: st.error(r.text[:300])

if not st.session_state.drawings: st.info("👆 Upload a drawing to begin."); st.stop()

# ── Drawing tabs ──────────────────────────────────────────────────────────────
st.markdown('<div class="sec">📐 Drawings</div>',unsafe_allow_html=True)
cols=st.columns(min(len(st.session_state.drawings),6))
for i,drw in enumerate(st.session_state.drawings):
    with cols[i%6]:
        active=drw["drawing_id"]==st.session_state.active_drawing
        if st.button(f"{'▶ ' if active else ''}{drw['display_name']}",
                     key=f"sel_{drw['drawing_id']}",use_container_width=True):
            st.session_state.active_drawing=drw["drawing_id"]
            st.session_state.hl_bbox=None; st.rerun()
        s=drw.get("validation_score",0)
        st.markdown(f'<div style="text-align:center;color:{sc(s)};font-size:1.3rem;font-weight:700">{s}%</div>',unsafe_allow_html=True)
        badge="🔵" if drw.get("drawing_type")=="assembly" else "🟢"
        st.caption(f"{badge} {drw.get('drawing_type','?').upper()}")

st.divider()
aid=st.session_state.active_drawing
asum=next((d for d in st.session_state.drawings if d["drawing_id"]==aid),{})
doc_id=st.session_state.doc_id

# Metrics
qs=asum.get("quality_score",{})
m1,m2,m3,m4,m5=st.columns(5)
m1.metric("Type",asum.get("drawing_type","?").upper())
m2.metric("OCR Elements",asum.get("ocr_count",0))
m3.metric("Compliance",f"{asum.get('validation_score',0)}%")
m4.metric("Overall Quality",f"{qs.get('overall_score',0)}%")
m5.metric("Violations",len(asum.get("rule_violations",[])))

# ── Main tabs ──────────────────────────────────────────────────────────────────
t1,t2,t3,t4,t5,t6=st.tabs(["🖼️ View & Highlight","🏗️ Engineering","✅ Validation","📊 Quality","🔍 Search","💬 Chat"])

# ═══ TAB 1: View + Canvas Highlight ══════════════════════════════════════════
with t1:
    # Field highlight buttons
    st.markdown('<div class="sec">🎯 Click field → highlights on drawing (canvas, no re-OCR)</div>',unsafe_allow_html=True)
    FIELDS=[("Drawing Number","drawing_number"),("Revision","revision"),("Scale","scale"),
            ("Material","material"),("Date","date"),("Drawn By","drawn_by"),
            ("Checked By","checked_by"),("Title","drawing_title"),("Projection","projection_method")]
    fc=st.columns(len(FIELDS))
    for i,(lbl,fn) in enumerate(FIELDS):
        with fc[i]:
            if st.button(f"📍{lbl}",key=f"hf_{fn}_{aid}",use_container_width=True):
                if do_highlight(doc_id,aid,field_name=fn): st.rerun()

    if st.session_state.hl_bbox:
        ocr_id=st.session_state.hl_ocr_id; txt=st.session_state.hl_text
        bbox=st.session_state.hl_bbox
        st.markdown(f"""<div style="background:rgba(34,197,94,.1);border:1px solid #22c55e;
            border-radius:8px;padding:.5rem 1rem;font-size:.85rem;color:#22c55e">
            🟢 <b>Highlighted:</b> {txt} &nbsp;|&nbsp; OCR ID: <code>{ocr_id}</code>
            &nbsp;|&nbsp; BBox: {bbox} &nbsp;|&nbsp; Nat: {st.session_state.hl_nat_w}×{st.session_state.hl_nat_h}
            </div>""",unsafe_allow_html=True)
        if st.button("✖ Clear Highlight",key=f"clhl_{aid}"):
            st.session_state.hl_bbox=None; st.rerun()

    # Canvas viewer
    drawing_canvas(
        doc_id=doc_id, drawing_id=aid,
        bbox=st.session_state.hl_bbox,
        nat_w=st.session_state.hl_nat_w,
        nat_h=st.session_state.hl_nat_h,
        height=680,
    )

    if asum.get("summary"):
        with st.expander("📝 Drawing Summary"):
            st.markdown(asum["summary"])

# ═══ TAB 2: Engineering Data ══════════════════════════════════════════════════
with t2:
    data=get_data(aid); eng=data.get("eng_json",{})
    if not eng: st.info("No AI data yet."); st.stop()
    tb=eng.get("title_block",{})
    if tb:
        st.markdown("**📋 Title Block**")
        rows=[]
        for k,v in tb.items():
            val=v.get("value","") if isinstance(v,dict) else str(v)
            oid=v.get("ocr_id","") if isinstance(v,dict) else ""
            rows.append({"Field":k.replace("_"," ").title(),"Value":val,"OCR ID":oid})
        df=pd.DataFrame(rows)
        st.dataframe(df,use_container_width=True,hide_index=True)
        # Clickable OCR ID highlight
        st.markdown("**Click OCR ID to highlight:**")
        oid_cols=st.columns(min(len(rows),5))
        for i,row in enumerate([r for r in rows if r["OCR ID"]]):
            with oid_cols[i%5]:
                if st.button(f"📍 {row['Field'][:12]}",key=f"ocd_{i}_{aid}"):
                    if do_highlight(doc_id,aid,ocr_id=row["OCR ID"]): st.rerun()

    mat=eng.get("material","")
    if mat:
        mv=mat.get("value",mat) if isinstance(mat,dict) else mat
        st.markdown(f"**Material:** `{mv}`")

    for field,icon,label in [("dimensions","📐","Dimensions"),("tolerances","🎯","Tolerances"),
        ("gdt_symbols","⊕","GD&T"),("surface_finish","✦","Surface Finish"),
        ("threads","🔩","Threads"),("notes","📝","Notes")]:
        items=eng.get(field,[])
        if items:
            with st.expander(f"{icon} {label} ({len(items)})"):
                for it in items: st.markdown(f"- {it}")

    st.download_button("⬇️ Engineering JSON",data=json.dumps(eng,indent=2,ensure_ascii=False),
        file_name=f"{aid}_engineering.json",mime="application/json",use_container_width=True)

# ═══ TAB 3: Validation ════════════════════════════════════════════════════════
with t3:
    data=get_data(aid); rows=data.get("validation_rows",[]); score=data.get("validation_score",0)
    st.markdown(f'<div style="text-align:center;padding:1rem"><span style="font-size:2.5rem;font-weight:700;color:{sc(score)}">{score}%</span><br><span style="color:#94a3b8">Checklist Compliance</span></div>',unsafe_allow_html=True)
    p=sum(1 for r in rows if r.get("status")=="✓")
    f_=sum(1 for r in rows if r.get("status")=="✗")
    na=sum(1 for r in rows if r.get("status")=="NA")
    c1,c2,c3=st.columns(3); c1.metric("✅ Passed",p); c2.metric("❌ Failed",f_); c3.metric("⬜ N/A",na)
    rv=data.get("rule_violations",[])
    if rv:
        with st.expander(f"⚠️ Engineering Rule Violations ({len(rv)})"):
            for v in rv: st.markdown(f"- 🔴 {v}")
    if rows:
        df=pd.DataFrame(rows)
        def cst(v): return f"color:{stc(v)};font-weight:700"
        st.dataframe(df.style.applymap(cst,subset=["status"]),use_container_width=True,hide_index=True)
        st.download_button("⬇️ Validation Report",data=json.dumps(rows,indent=2),
            file_name=f"{aid}_validation.json",mime="application/json",use_container_width=True)

# ═══ TAB 4: Quality ═══════════════════════════════════════════════════════════
with t4:
    data=get_data(aid); qs=data.get("quality_score",{})
    if not qs: st.info("No quality data."); st.stop()
    overall=qs.get("overall_score",0)
    st.markdown(f'<div style="text-align:center;padding:1.5rem"><span style="font-size:3rem;font-weight:700;color:{sc(overall)}">{overall}%</span><br><span style="color:#94a3b8">Overall Engineering Quality</span></div>',unsafe_allow_html=True)
    q1,q2,q3=st.columns(3)
    q1.metric("OCR Accuracy",f"{qs.get('ocr_accuracy',0)}%")
    q2.metric("Extraction Accuracy",f"{qs.get('extraction_accuracy',0)}%")
    q3.metric("Checklist Compliance",f"{qs.get('checklist_compliance',0)}%")
    q4,q5,q6=st.columns(3)
    q4.metric("✅ Passed",qs.get("passed",0))
    q5.metric("❌ Failed",qs.get("failed",0))
    q6.metric("⚠️ Warnings",qs.get("warnings",0))
    rv=data.get("rule_violations",[])
    if rv:
        st.markdown('<div class="sec">Rule Violations</div>',unsafe_allow_html=True)
        for v in rv: st.error(v)

# ═══ TAB 5: Search ════════════════════════════════════════════════════════════
with t5:
    st.markdown('<div class="sec">🔍 Search — this drawing only</div>',unsafe_allow_html=True)
    st.caption("Results include OCR ID and bbox — click to highlight on canvas.")
    quick=["Ø","Revision","Material","Thread","Tolerance","Drawing Number","Scale","BOM"]
    qc=st.columns(len(quick))
    for i,term in enumerate(quick):
        with qc[i]:
            if st.button(term,key=f"qt_{term}_{aid}",use_container_width=True):
                st.session_state["_sq"]=term
    sq=st.text_input("Search",placeholder="e.g. 120, Ø25, M8, bearing…",key=f"sq_{aid}")
    if "_sq" in st.session_state: sq=st.session_state.pop("_sq")
    if sq:
        with st.spinner("Searching…"):
            r=api("get",f"/search?doc_id={doc_id}&drawing_id={aid}&q={sq}")
            if r and r.status_code==200:
                res=r.json(); hits=res.get("results",[])
                st.markdown(f"**{res['total']} result(s)** in {asum.get('display_name','')}")
                if hits:
                    df=pd.DataFrame([{"OCR ID":h.get("field_id",""),"Text":h.get("text",""),
                       "Type":h.get("type",""),"BBox":str(h.get("bbox",[]))} for h in hits])
                    st.dataframe(df,use_container_width=True,hide_index=True)
                    st.markdown("**Click to highlight:**")
                    hc=st.columns(min(len(hits[:6]),6))
                    for i,h in enumerate(hits[:6]):
                        with hc[i]:
                            if h.get("bbox") and st.button(f"📍{h['text'][:15]}",key=f"shl_{i}_{aid}"):
                                oid=h.get("field_id","")
                                if do_highlight(doc_id,aid,ocr_id=oid): st.rerun()
                else: st.info(f"No results for `{sq}`.")

# ═══ TAB 6: Chat ══════════════════════════════════════════════════════════════
with t6:
    st.markdown('<div class="sec">💬 Chat — restricted to this drawing</div>',unsafe_allow_html=True)
    st.caption(f"🔒 Answering only from {asum.get('display_name','')}")
    if aid not in st.session_state.chat_history: st.session_state.chat_history[aid]=[]
    if aid not in st.session_state.chat_msgs: st.session_state.chat_msgs[aid]=[]
    examples=["What is the drawing number?","List all dimensions.","What is the material?",
              "What threads exist?","What is the revision?","Summarise this drawing."]
    with st.expander("💡 Example questions"):
        ec=st.columns(3)
        for i,q in enumerate(examples):
            with ec[i%3]:
                if st.button(q,key=f"eq_{i}_{aid}"): st.session_state["_cq"]=q
    for q,a in st.session_state.chat_history[aid]:
        st.markdown(f'<div class="chat-u">👤 {q}</div>',unsafe_allow_html=True)
        st.markdown(f'<div class="chat-b">🤖 {a}</div>',unsafe_allow_html=True)
    uq=st.chat_input(f"Ask about {asum.get('display_name','')}…")
    if not uq and "_cq" in st.session_state: uq=st.session_state.pop("_cq")
    if uq:
        with st.spinner("Thinking…"):
            r=api("post","/ai/chat-drawing",json={"doc_id":doc_id,"drawing_id":aid,
                "question":uq,"history":st.session_state.chat_msgs[aid]})
            if r and r.status_code==200:
                ans=r.json().get("answer","")
                st.session_state.chat_history[aid].append((uq,ans))
                st.session_state.chat_msgs[aid].extend([{"role":"user","content":uq},{"role":"assistant","content":ans}])
                st.rerun()
            elif r:
                try: st.error(r.json().get("detail",""))
                except: st.error(r.text[:200])
    if st.session_state.chat_history.get(aid):
        if st.button("🗑️ Clear",key=f"clr_{aid}"):
            st.session_state.chat_history[aid]=[]; st.session_state.chat_msgs[aid]=[]; st.rerun()
