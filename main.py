"""
Agentic chat app with Flask API, Ollama model selection,
and a 2-column tool browser with > / < selection controls.
All tools are always bound to the agent — the browser just
lets you inspect what params each tool needs.

Dual-mode execution:
  - Internal (personal key + home IP): tools execute server-side
  - External (external key): tool calls route to client via WebSocket
"""

import json
import os
import re
import threading
from typing import Sequence
from uuid import uuid4
import ollama as ollama_client
from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, stream_with_context, render_template_string, send_file, g, abort
from flask_sock import Sock

from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk, SystemMessage, ToolCall, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langchain_chroma import Chroma

import httpx

load_dotenv()

PERSONAL_API_KEY = os.environ["PERSONAL_API_KEY"]
EXTERNAL_API_KEY = os.environ["EXTERNAL_API_KEY"]
HOME_IP = os.environ.get("HOME_IP", "50.248.206.70")

from config import AGENT_PORTS, agent_url, NUM_CTX, CHROMA_DIR, EMBED_MODEL, RETRIEVAL_K, RETRIEVAL_MIN_SCORE
from tools import ALL_TOOLS, TOOL_CATEGORIES, DEFAULT_SELECTED

# ── Tool typing and selection ─────────────────────────────────────────────────

_TOOL_NAMES = {t.name for t in ALL_TOOLS}


# ── ChromaDB context retrieval ────────────────────────────────────────────────

_chroma_db = None

def _get_chroma():
    global _chroma_db
    if _chroma_db is None:
        _chroma_db = Chroma(
            persist_directory=CHROMA_DIR,
            embedding_function=OllamaEmbeddings(model=EMBED_MODEL),
        )
    return _chroma_db


def get_relevant_context(query: str, k: int = RETRIEVAL_K,
                         min_score: float = RETRIEVAL_MIN_SCORE) -> str:
    """Retrieve relevant docs from Chroma, gated by relevance score.

    Only chunks scoring above min_score are included — avoids injecting
    irrelevant context that dilutes the prompt for tool-heavy queries.
    """
    try:
        db = _get_chroma()
        scored = db.similarity_search_with_relevance_scores(query, k=k)
        if not scored:
            return ""
        chunks = []
        for doc, score in scored:
            if score < min_score:
                continue
            src = doc.metadata.get("path", "unknown")
            chunks.append(f"[{src} (score={score:.2f})]\n{doc.page_content}")
        return "\n\n---\n\n".join(chunks)
    except Exception:
        return ""


# ── Tool call fixer middleware ────────────────────────────────────────────────
# Ollama models often emit tool calls as JSON text in <tools> tags or bare JSON
# instead of using the native tool calling protocol.  This middleware intercepts
# after each model call and promotes text-based tool calls to real ToolCalls.

def _extract_tool_calls(content: str) -> list[ToolCall] | None:
    """Parse tool call JSON from <tools> tags or bare JSON in model output."""
    if not content or not content.strip():
        return None

    candidates = []

    # 1. <tools>...</tools> wrapped JSON
    for m in re.finditer(r"<tools?>(.*?)</tools?>", content, re.DOTALL):
        candidates.append(m.group(1).strip())

    # 2. Fenced JSON blocks
    for m in re.finditer(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL):
        candidates.append(m.group(1).strip())

    # 3. Any JSON object in the text that looks like a tool call
    #    Handles "Let me search...\n{...}" and similar mixed text+JSON
    for m in re.finditer(r'\{', content):
        start = m.start()
        # Try to parse JSON starting at each '{' that could be a tool call
        remainder = content[start:]
        if '"name"' not in remainder[:200]:
            continue
        try:
            obj = json.loads(remainder[:remainder.index('\n\n')] if '\n\n' in remainder else remainder)
            if isinstance(obj, dict) and "name" in obj:
                candidates.append(json.dumps(obj))
        except (json.JSONDecodeError, ValueError):
            # Try progressively finding the matching closing brace
            depth = 0
            for i, ch in enumerate(remainder):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(remainder[:i + 1])
                            if isinstance(obj, dict) and "name" in obj:
                                candidates.append(remainder[:i + 1])
                        except json.JSONDecodeError:
                            pass
                        break

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        items = parsed if isinstance(parsed, list) else [parsed]
        calls = []
        for item in items:
            if isinstance(item, dict) and item.get("name") in _TOOL_NAMES:
                calls.append(ToolCall(
                    name=item["name"],
                    args=item.get("arguments") or item.get("args") or {},
                    id=str(uuid4()),
                ))
        if calls:
            return calls

    return None


class ToolCallFixerMiddleware(AgentMiddleware):
    """Promote text-based tool calls to real ToolCall objects after model output."""

    def after_model(self, state, runtime):
        msgs = state.get("messages", [])
        if not msgs:
            return None

        last = msgs[-1]
        if not isinstance(last, AIMessage):
            return None
        if last.tool_calls:
            return None  # already has real tool calls
        if not last.content:
            return None

        parsed = _extract_tool_calls(last.content)
        if not parsed:
            return None

        # Replace the last message with one that has proper tool calls
        fixed = AIMessage(content="", tool_calls=parsed, id=last.id)
        return {"messages": [fixed]}


app = Flask(__name__)
sock = Sock(app)

# ── Auth middleware ────────────────────────────────────────────────────────────
# Routes that skip authentication (local UI, static assets)
_PUBLIC_PATHS = frozenset({"/", "/main.css", "/health"})


def _is_public_path(path: str) -> bool:
    return path in _PUBLIC_PATHS or path.startswith("/static/")


@app.before_request
def auth_middleware():
    """Authenticate API requests and set g.exec_mode."""
    if _is_public_path(request.path):
        g.exec_mode = "local"
        return

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        abort(401, description="Missing or malformed Authorization header")

    key = auth[7:]  # strip "Bearer "
    client_ip = request.headers.get("X-Real-IP") or request.remote_addr

    if key == PERSONAL_API_KEY and client_ip == HOME_IP:
        g.exec_mode = "local"
    elif key == EXTERNAL_API_KEY:
        g.exec_mode = "remote"
    else:
        abort(401, description="Invalid API key or unauthorized IP")


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="obsidian">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" type="text/css" href="main.css">
<title>Agentic Chat</title>
</head>
<body>
<canvas id="particle-canvas"></canvas>

<!-- Top bar -->
<div class="topbar">
  <div class="topbar-brand">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>
    Agentic Chat
  </div>
  <select id="model-select"><option value="">Loading models...</option></select>
  <span class="topbar-status" id="status">No model selected</span>
  <div class="topbar-spacer"></div>
  <select class="theme-select" id="theme-select">
    <optgroup label="Dark">
      <option value="obsidian" selected>Obsidian</option>
      <option value="carbon">Carbon</option>
      <option value="amethyst">Amethyst</option>
    </optgroup>
    <optgroup label="Light">
      <option value="frost">Frost</option>
      <option value="sand">Sand</option>
      <option value="blossom">Blossom</option>
    </optgroup>
  </select>
</div>
<!-- Sidebar / Tool panel — single element, collapsed ↔ expanded -->
  
<div class="main">
  <div class="sidebar" id="sidebar">
    <div class="sidebar-toggle" id="sidebar-toggle" title="Toggle tools">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
    </div>
    <div class="sidebar-expanded-content">
      <div class="sidebar-header">
        <span class="sidebar-title">Tools</span>
      </div>
      <div class="sidebar-body" id="tools-modal-body"></div>
    </div>
  </div>
  <div class="messages" id="messages"></div>

  <div class="input-bar">
    <div class="selected-tools-chip" id="tools-chip">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
      <span id="tools-chip-label"></span>
      <div class="selected-tools-popup" id="tools-popup"></div>
    </div>
    <input id="chat-input" type="text" placeholder="Type a message..." autocomplete="off">
    <button class="btn btn-ghost" id="clear-btn">Clear</button>
    <button class="btn btn-primary" id="send-btn" disabled>Send</button>
    <button class="btn btn-danger" id="stop-btn">Stop</button>
  </div>
</div>

<!-- Image lightbox modal -->
<div id="lightbox" onclick="closeLightbox(event)">
  <img id="lightbox-img" src="" alt="">
  <div id="lightbox-caption"></div>
</div>

<script>
// ── Theme ──
const THEMES=['obsidian','carbon','amethyst','frost','sand','blossom'];

function setTheme(t){
  document.documentElement.setAttribute('data-theme',t);
  localStorage.setItem('agentic-theme',t);
  document.getElementById('theme-select').value=t;
}

(function(){
  const saved=localStorage.getItem('agentic-theme');
  if(saved&&THEMES.includes(saved))setTheme(saved);
})();

document.getElementById('theme-select').onchange=function(){setTheme(this.value)};

// ── Sidebar toggle ──
const sidebar=document.getElementById('sidebar');
document.getElementById('sidebar-toggle').onclick=()=>{
  sidebar.classList.toggle('expanded');
  if(sidebar.classList.contains('expanded')) expandToolModal();
};

// ── Lightbox ──
function openLightbox(src,caption){
  const lb=document.getElementById('lightbox');
  document.getElementById('lightbox-img').src=src;
  document.getElementById('lightbox-caption').textContent=caption||'';
  lb.classList.add('active');
  document.addEventListener('keydown',lightboxEsc);
}
function closeLightbox(e){
  if(e&&e.target.id==='lightbox-img')return;
  document.getElementById('lightbox').classList.remove('active');
  document.removeEventListener('keydown',lightboxEsc);
}
function lightboxEsc(e){if(e.key==='Escape')closeLightbox();}

// ── API helpers ──
const api=async(path,opts)=>{const r=await fetch('/api'+path,opts);return r.json()};
const post=(path,body)=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});

let _toolData=null; // cached API response
let _selectedNames=[];

// ── Models ──
async function loadModels(){
  const d=await api('/models');
  const sel=document.getElementById('model-select');
  sel.textContent='';
  const defOpt=document.createElement('option');
  defOpt.value='';defOpt.textContent='-- pick a model --';
  sel.appendChild(defOpt);
  (d.models||[]).forEach(m=>{
    const o=document.createElement('option');
    o.value=m;o.textContent=m;
    if(m===d.current)o.selected=true;
    sel.appendChild(o);
  });
  if(d.current){
    document.getElementById('status').textContent=d.current;
    document.getElementById('send-btn').disabled=false;
  }
}
document.getElementById('model-select').onchange=async function(){
  if(!this.value){document.getElementById('send-btn').disabled=true;return;}
  await post('/models',{model:this.value});
  document.getElementById('status').textContent=this.value;
  document.getElementById('send-btn').disabled=false;
};

// ── Tools ──
async function loadTools(){
  const d=await api('/tools');
  _toolData=d;
  _selectedNames=d.selected||[];
  updateToolsChip();
  if(sidebar.classList.contains('expanded')) expandToolModal();
}


const tools = loadTools();

const sidebar = document.getElementById('sidebar');
const sidebarHeader = sidebar.firstChild();
const sidebarTitle = sidebar.secondChild();
const toolsList = document.createElement('ul');
for (const tool in tools) {(tool) => {
  const toolItem = document.createElement('li');
  const toolToggle = document.createElement('a');
    toolToggle.onClick=async function(){
     if(_selectedNames.includes(tool)){
      _selectedNames=_selectedNames.filter(n=>{n!=tool});
      }else{
      _selectedNames.push(tool);
      }
    }
    if (sidebar.classList.includes('expanded'){
        toolToggle.innerHTML=tool.name; 
    } else {
        const toolIcon = document.createElement('img');
        img.alt='ico'
        img.src=tool;
        toolToggle.appendChild(toolIcon);
    }
    toolItem.appendChild(toolToggle);
    toolsList.appendChild(toolItem);
}

sidebar.appendChild(toolsList);
sidebarHeader.addEventListener('click', toggleSidebar);



}}

// ── Tool panel (rendered inside sidebar) ──

function expandToolModal(){
  if(!_toolData)return;
  const body=document.getElementById('tools-modal-body');
  if(!body)return;
  body.textContent='';
  (_toolData.categories||[]).forEach(cat=>{
    const group=document.createElement('div');
    group.className='cat-group';

    // Header
    const header=document.createElement('div');
    header.className='cat-header';

    const chevron=document.createElementNS('http://www.w3.org/2000/svg','svg');
    chevron.setAttribute('viewBox','0 0 24 24');
    chevron.setAttribute('fill','none');
    chevron.setAttribute('stroke','currentColor');
    chevron.setAttribute('stroke-width','2');
    chevron.classList.add('cat-chevron');
    const poly=document.createElementNS('http://www.w3.org/2000/svg','polyline');
    poly.setAttribute('points','9 18 15 12 9 6');
    chevron.appendChild(poly);

    const cb=document.createElement('input');
    cb.type='checkbox';
    cb.className='cat-checkbox';
    cb.checked=cat.all_selected;
    if(cat.some_selected&&!cat.all_selected){
      cb.indeterminate=true;
      cb.classList.add('indeterminate');
    }
    cb.onclick=async(e)=>{
      e.stopPropagation();
      await post('/tools/toggle_category',{category:cat.name});
      loadTools();
    };

    const name=document.createElement('span');
    name.className='cat-name';
    name.textContent=cat.name;

    const count=document.createElement('span');
    count.className='cat-count';
    count.textContent=cat.selected_count+'/'+cat.count;

    header.appendChild(chevron);
    header.appendChild(cb);
    header.appendChild(name);
    header.appendChild(count);
    header.onclick=(e)=>{
      if(e.target===cb)return;
      group.classList.toggle('open');
    };

    // Tools list
    const toolsDiv=document.createElement('div');
    toolsDiv.className='cat-tools';
    cat.tools.forEach(t=>{
      const row=document.createElement('div');
      row.className='cat-tool-item';
      const tcb=document.createElement('input');
      tcb.type='checkbox';
      tcb.checked=t.selected;
      tcb.onclick=async()=>{
        await post('/tools/toggle',{tool:t.name});
        loadTools();
      };
      const tname=document.createElement('span');
      tname.className='cat-tool-name';
      tname.textContent=t.name;
      const tdesc=document.createElement('span');
      tdesc.className='cat-tool-desc';
      tdesc.textContent=t.description;
      tdesc.title=t.description;
      row.appendChild(tcb);
      row.appendChild(tname);
      row.appendChild(tdesc);
      toolsDiv.appendChild(row);
    });

    group.appendChild(header);
    group.appendChild(toolsDiv);
    body.appendChild(group);
  });
}

// ── Selected tools chip (next to input) ──
function updateToolsChip(){
  const chip=document.getElementById('tools-chip');
  const label=document.getElementById('tools-chip-label');
  const popup=document.getElementById('tools-popup');
  const n=_selectedNames.length;
  if(n===0){
    chip.classList.remove('visible');
    return;
  }
  chip.classList.add('visible');
  label.textContent=n+' tool'+(n===1?'':'s');
  popup.textContent='';
  _selectedNames.forEach(name=>{
    const row=document.createElement('div');
    row.className='selected-tools-popup-item';
    const nameEl=document.createElement('span');
    nameEl.className='stool-name';
    nameEl.textContent=name;
    const rm=document.createElement('span');
    rm.className='stool-remove';
    rm.textContent='\u00d7';
    rm.onclick=async(e)=>{
      e.stopPropagation();
      await post('/tools/toggle',{tool:name});
      loadTools();
    };
    row.appendChild(nameEl);
    row.appendChild(rm);
    popup.appendChild(row);
  });
}


// ── "No tools" warning on send ──
const _noToolsDismissed=localStorage.getItem('agentic-no-tools-dismissed')==='1';

function showNoToolsWarning(){
  if(_noToolsDismissed)return;
  const existing=document.getElementById('no-tools-warning');
  if(existing)existing.remove();
  const bar=document.createElement('div');
  bar.id='no-tools-warning';
  bar.className='no-tools-warning';
  bar.textContent='No tools included with this chat. To make the most of your experience, choose some tools. ';
  const cb=document.createElement('input');
  cb.type='checkbox';
  cb.onchange=()=>{
    localStorage.setItem('agentic-no-tools-dismissed','1');
    bar.remove();
  };
  const lbl=document.createElement('label');
  lbl.appendChild(cb);
  lbl.appendChild(document.createTextNode("Don't show again"));
  bar.appendChild(lbl);
  setTimeout(()=>{if(bar.parentNode)bar.remove();},4500);
}

// ── Chat ──
function renderContent(el,text){
  const parts=text.split(/(!\[[^\]]*\]\([^)]+\))/g);
  while(el.firstChild)el.removeChild(el.firstChild);
  parts.forEach(p=>{
    const imgMatch=p.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if(imgMatch&&imgMatch[2].startsWith('/static/images/')){
      const img=document.createElement('img');
      img.alt=imgMatch[1];img.src=imgMatch[2];
      img.className='chat-image';
      el.appendChild(img);
    }else if(p){
      el.appendChild(document.createTextNode(p));
    }
  });
}

function addMsg(role,text){
  const div=document.createElement('div');
  div.className='msg '+role;
  if(role==='assistant'){renderContent(div,text);}
  else{div.textContent=text;}
  const msgs=document.getElementById('messages');
  msgs.appendChild(div);
  msgs.scrollTop=msgs.scrollHeight;
  return div;
}

function addImageMsg(src,filename,sizeKb){
  const div=document.createElement('div');
  div.className='msg assistant img-msg';
  const thumb=document.createElement('img');
  thumb.src=src;thumb.alt=filename||'image';
  thumb.className='chat-thumb';
  thumb.onclick=()=>openLightbox(src,filename+(sizeKb?' ('+sizeKb+' KB)':''));
  div.appendChild(thumb);
  if(filename){
    const cap=document.createElement('div');
    cap.className='img-caption';
    cap.textContent=filename+(sizeKb?' — '+sizeKb+' KB':'');
    div.appendChild(cap);
  }
  const msgs=document.getElementById('messages');
  msgs.appendChild(div);
  msgs.scrollTop=msgs.scrollHeight;
}

let activeStreams=0;
function updateStopBtn(){document.getElementById('stop-btn').style.display=activeStreams>0?'':'none';}

function createThinkingIndicator(){
  const div=document.createElement('div');
  div.className='thinking-indicator';
  const header=document.createElement('div');
  header.className='thinking-header';
  const dots=document.createElement('div');
  dots.className='thinking-dots';
  for(let i=0;i<3;i++){dots.appendChild(document.createElement('span'));}
  const label=document.createElement('span');
  label.className='thinking-label';
  label.textContent='working';
  const timerEl=document.createElement('span');
  timerEl.className='thinking-timer';
  timerEl.textContent='0s';
  header.appendChild(dots);
  header.appendChild(label);
  header.appendChild(timerEl);
  const preview=document.createElement('div');
  preview.className='thinking-preview';
  div.appendChild(header);
  div.appendChild(preview);
  const msgs=document.getElementById('messages');
  msgs.appendChild(div);
  msgs.scrollTop=msgs.scrollHeight;
  const t0=Date.now();
  const timer=setInterval(()=>{timerEl.textContent=((Date.now()-t0)/1000|0)+'s';},1000);
  return {el:div,timer,previewBuf:'',
    update(text,type){
      if(type==='tool_call'){
        label.textContent='calling tool';
        preview.textContent=text;
      }else if(type==='tool_result'){
        label.textContent='got result';
        preview.textContent=text.slice(0,120);
      }else if(type==='token'){
        label.textContent='thinking';
        this.previewBuf+=text;
        if(this.previewBuf.length>200)this.previewBuf=this.previewBuf.slice(-200);
        preview.textContent=this.previewBuf.slice(-120);
      }
      msgs.scrollTop=msgs.scrollHeight;
    },
    remove(){clearInterval(timer);div.remove();}
  };
}

async function sendMessage(){
  const input=document.getElementById('chat-input');
  const msg=input.value.trim();
  if(!msg)return;
  if(_selectedNames.length===0)showNoToolsWarning();
  input.value='';
  addMsg('user',msg);
  activeStreams++;
  updateStopBtn();
  const thinking=createThinkingIndicator();
  let tokenBuf='';
  try{
    const resp=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg})});
    if(!resp.ok){
      const err=await resp.json().catch(()=>({}));
      addMsg('error',err.error||'HTTP '+resp.status);
      thinking.remove();
      return;
    }
    if(resp.body&&resp.body.getReader){
      const reader=resp.body.getReader();
      const decoder=new TextDecoder();
      let lineBuf='';
      while(true){
        const{done,value}=await reader.read();
        if(done)break;
        lineBuf+=decoder.decode(value,{stream:true});
        const lines=lineBuf.split('\n');
        lineBuf=lines.pop();
        for(const line of lines){
          if(!line.trim())continue;
          try{
            const ev=JSON.parse(line);
            if(ev.token){
              tokenBuf+=ev.token;
              thinking.update(ev.token,'token');
            }else if(ev.tool_call){
              thinking.update(ev.tool_call.tool+': '+ev.tool_call.input,'tool_call');
            }else if(ev.image){
              addImageMsg(ev.image.src,ev.image.filename,ev.image.size_kb);
            }else if(ev.tool_result){
              thinking.update(ev.tool_result.output,'tool_result');
            }else if(ev.error){
              addMsg('error',ev.error);
            }
          }catch(pe){console.warn('parse error',pe,line)}
        }
      }
    }else{
      const text=await resp.text();
      const lines=text.trim().split('\n');
      for(const line of lines){
        if(!line.trim())continue;
        try{
          const ev=JSON.parse(line);
          if(ev.token){
            tokenBuf+=ev.token;
            thinking.update(ev.token,'token');
          }else if(ev.image){
            addImageMsg(ev.image.src,ev.image.filename,ev.image.size_kb);
          }else if(ev.tool_call){
            thinking.update(ev.tool_call.tool+': '+ev.tool_call.input,'tool_call');
          }else if(ev.error){
            addMsg('error',ev.error);
          }
        }catch(pe){}
      }
    }
    thinking.remove();
    if(tokenBuf){
      const assistantDiv=addMsg('assistant','');
      renderContent(assistantDiv,tokenBuf);
    }else{
      addMsg('assistant','(no response)');
    }
  }catch(e){
    thinking.remove();
    addMsg('error','Network error: '+e.message);
    console.error(e);
  }
  activeStreams=Math.max(0,activeStreams-1);
  updateStopBtn();
}

document.getElementById('stop-btn').onclick=async()=>{await fetch('/api/chat/cancel',{method:'POST'})};
document.getElementById('send-btn').onclick=sendMessage;
document.getElementById('chat-input').onkeydown=e=>{if(e.key==='Enter'&&!document.getElementById('send-btn').disabled)sendMessage()};
document.getElementById('clear-btn').onclick=async()=>{
  await fetch('/api/history',{method:'DELETE'});
  document.getElementById('messages').textContent='';
};

// ── Particle system ──
(function(){
  const PALETTES={
    obsidian:  ['#2a4a8a','#4060b0','#6080d0','#3050a0','#1a3070'],
    carbon:    ['#20a060','#30c080','#50e0a0','#18804a','#40d890'],
    amethyst:  ['#7030b0','#9050d0','#b070f0','#6020a0','#a060e0'],
    frost:     ['#3050c0','#4060e0','#5080ff','#2040a0','#6090ff'],
    sand:      ['#b08020','#c89830','#dab050','#a07018','#d0a040'],
    blossom:   ['#c02060','#d84080','#f060a0','#a01848','#e85098']
  };

  const canvas=document.getElementById('particle-canvas');
  const ctx=canvas.getContext('2d');
  let W,H,particles=[];
  const COUNT=80;

  function resize(){
    W=canvas.width=window.innerWidth;
    H=canvas.height=window.innerHeight;
  }
  window.addEventListener('resize',resize);
  resize();

  function getTheme(){
    return document.documentElement.getAttribute('data-theme')||'obsidian';
  }

  function hexToRgb(hex){
    const n=parseInt(hex.slice(1),16);
    return [(n>>16)&255,(n>>8)&255,n&255];
  }

  const FIELD=3; // 3x viewport height loop

  function spawn(i,scatter){
    const pal=PALETTES[getTheme()]||PALETTES.obsidian;
    const color=pal[Math.floor(Math.random()*pal.length)];
    const rgb=hexToRgb(color);
    const r=Math.random()*1.2+0.3;
    particles[i]={
      x:Math.random()*W,
      y:scatter?Math.random()*H*FIELD:-(Math.random()*H*0.5),
      r:r,
      dx:(Math.random()-0.5)*0.06,
      dy:Math.random()*0.12+0.04,
      opacity:Math.random()*0.3+0.08,
      rgb:rgb
    };
  }

  for(let i=0;i<COUNT;i++) spawn(i,true);

  // Re-color particles on theme change
  const obs=new MutationObserver(()=>{
    const pal=PALETTES[getTheme()]||PALETTES.obsidian;
    particles.forEach(p=>{
      const c=pal[Math.floor(Math.random()*pal.length)];
      p.rgb=hexToRgb(c);
    });
  });
  obs.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});

  function draw(){
    ctx.clearRect(0,0,W,H);
    const totalH=H*FIELD;
    for(let i=0;i<COUNT;i++){
      const p=particles[i];
      p.x+=p.dx;
      p.y+=p.dy;

      // Continuous loop: wrap around the full 3x field
      if(p.y>totalH) p.y-=totalH;

      // Only draw if within visible viewport
      if(p.y>H+p.r*2) continue;

      const [r,g,b]=p.rgb;
      const glowR=p.r*2.5;

      // Soft sphere — solid core with gentle edge falloff
      const grad=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,glowR);
      grad.addColorStop(0,'rgba('+r+','+g+','+b+','+p.opacity+')');
      grad.addColorStop(0.5,'rgba('+r+','+g+','+b+','+(p.opacity*0.5)+')');
      grad.addColorStop(1,'rgba('+r+','+g+','+b+',0)');

      ctx.beginPath();
      ctx.arc(p.x,p.y,glowR,0,Math.PI*2);
      ctx.fillStyle=grad;
      ctx.fill();

      // Wrap horizontal
      if(p.x<-10)p.x=W+10;
      if(p.x>W+10)p.x=-10;
    }
    requestAnimationFrame(draw);
  }
  draw();
})();

// ── Init ──
loadModels();loadTools();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


@app.route("/main.css")
def serve_css():
    resp = send_file("main.css", mimetype="text/css")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.route("/static/images/<path:filename>")
def serve_image(filename):
    """Serve downloaded images from static/images/."""
    return send_file(f"static/images/{filename}")


# ── State ────────────────────────────────────────────────────────────────────
_cancel_event = threading.Event()

_checkpointer = MemorySaver()

_state = {
    "model": "huihui_ai/qwen2.5-coder-abliterate:14b",
    "thread_id": str(uuid4()),
    "system_prompt": (
        "You are a helpful assistant with access to tools. "
        "When a task requires a tool, CALL IT IMMEDIATELY. "
        "Never describe what you plan to do — just do it. "
        "Say what tool you're calling in one short sentence, then call it. "
        "Present results formatted for humans, not raw JSON. "
        "If no tool is needed, respond naturally and concisely. "
        "Only use parameter values the user provided or that you can "
        "confidently derive from context — never guess or fabricate "
        "values for paths, URLs, IDs, or names the user hasn't given you.\n\n"
        "TORRENT FILTERING RULES — apply these when presenting or downloading search results:\n"
        "- Prefer results with high seeders (50+) from known trackers/indexers.\n"
        "- LANGUAGE: Unless the user asks for another language, only select English releases. "
        "Reject files tagged FRENCH, TRUEFRENCH, MULTI (unless English is confirmed), "
        "GERMAN, SPANISH, ITA, LATINO, DUBBED, VO, VFF, VFQ, or other non-English language tags. "
        "Look for ENG, English, or no language tag (scene releases default to English).\n"
        "- QUALITY TAGS: Prefer scene/p2p naming: Title.Year.Source.Codec-GROUP. "
        "Good sources: BluRay, BDRip, WEB-DL, WEBRip, HDTV, REMUX. "
        "Good codecs: x264, x265, HEVC, AV1, AAC, FLAC, DTS. "
        "Avoid: CAM, TS, TELESYNC, HDCAM, SCR, DVDSCR (these are low quality).\n"
        "- RED FLAGS: Skip files that are suspiciously small for their claimed quality "
        "(e.g. a 200MB '4K BluRay'), have .exe or .zip extensions, "
        "have zero or very few seeders with inflated file counts, "
        "or have generic/spammy filenames.\n"
        "- When presenting results, briefly note why you recommend or skip each one. "
        "If all results look bad, say so instead of recommending a poor choice."
    ),
    "history": [],          # list of {"role": ..., "content": ...}
    "selected_tools": set(),  # set of tool names — user selects via modal
}


def _tool_meta(t) -> dict:
    """Extract name, description, and parameter info from a LangChain tool."""
    schema = t.args_schema.model_json_schema() if t.args_schema else {}
    props = schema.get("properties", {})
    required = schema.get("required", [])
    params = {}
    for pname, pinfo in props.items():
        params[pname] = {
            "type": pinfo.get("type", "string"),
            "description": pinfo.get("description", ""),
            "required": pname in required,
        }
        if "default" in pinfo:
            params[pname]["default"] = pinfo["default"]
    return {
        "name": t.name,
        "description": t.description.split("\n")[0] if t.description else "",
        "params": params,
    }


# ── Models ───────────────────────────────────────────────────────────────────

def _is_abliterated(name: str) -> bool:
    """Return True if the model name indicates an abliterated variant."""
    return "ablit" in name.lower()


@app.route("/api/models", methods=["GET"])
def list_models():
    """List locally available abliterated Ollama models only."""
    try:
        models = ollama_client.list()
        names = [m.model for m in models.models if _is_abliterated(m.model)]
        return jsonify({"models": names, "current": _state["model"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/models", methods=["POST"])
def select_model():
    """Select an abliterated Ollama model.  Body: {"model": "name"}"""
    data = request.get_json(force=True)
    model = data.get("model")
    if not model:
        return jsonify({"error": "model required"}), 400
    if not _is_abliterated(model):
        return jsonify({"error": "only abliterated models are allowed"}), 400
    _state["model"] = model
    _state["history"] = []
    _state["thread_id"] = str(uuid4())  # fresh checkpointer memory for new model
    return jsonify({"model": model})


# ── Tools (category-based) ────────────────────────────────────────────────────

# Flat lookup: tool name -> meta dict
TOOL_META = {t.name: _tool_meta(t) for t in ALL_TOOLS}

# Category structure for the API
CATEGORY_ORDER = list(TOOL_CATEGORIES.keys())


def _get_selected_tools() -> Sequence[BaseTool]:
    """Return the BaseTool objects for currently selected tool names."""
    sel = _state["selected_tools"]
    return [t for t in ALL_TOOLS if t.name in sel]


@app.route("/api/tools", methods=["GET"])
def get_tools():
    """Return categories with tools and their selection state."""
    sel = _state["selected_tools"]
    categories = []
    for cat_name in CATEGORY_ORDER:
        cat_tools = TOOL_CATEGORIES[cat_name]
        tools = []
        for t in cat_tools:
            meta = TOOL_META[t.name]
            tools.append({**meta, "selected": t.name in sel})
        all_selected = all(t.name in sel for t in cat_tools)
        some_selected = any(t.name in sel for t in cat_tools)
        categories.append({
            "name": cat_name,
            "tools": tools,
            "all_selected": all_selected,
            "some_selected": some_selected,
            "count": len(cat_tools),
            "selected_count": sum(1 for t in cat_tools if t.name in sel),
        })
    # Also return flat list of selected tool names for the chip
    selected_names = [t.name for t in ALL_TOOLS if t.name in sel]
    return jsonify({"categories": categories, "selected": selected_names})


@app.route("/api/tools/toggle", methods=["POST"])
def toggle_tool():
    """Toggle a single tool on/off.  Body: {"tool": "read_file"}"""
    data = request.get_json(force=True)
    name = data.get("tool", "")
    if name not in TOOL_META:
        return jsonify({"error": f"unknown tool: {name}"}), 400
    if name in _state["selected_tools"]:
        _state["selected_tools"].discard(name)
    else:
        _state["selected_tools"].add(name)
    return get_tools()


@app.route("/api/tools/toggle_category", methods=["POST"])
def toggle_category():
    """Toggle all tools in a category.  Body: {"category": "Filesystem"}"""
    data = request.get_json(force=True)
    cat_name = data.get("category", "")
    if cat_name not in TOOL_CATEGORIES:
        return jsonify({"error": f"unknown category: {cat_name}"}), 400
    cat_tools = TOOL_CATEGORIES[cat_name]
    cat_names = {t.name for t in cat_tools}
    # If all selected, deselect all; otherwise select all
    if cat_names.issubset(_state["selected_tools"]):
        _state["selected_tools"] -= cat_names
    else:
        _state["selected_tools"] |= cat_names
    return get_tools()


# ── System prompt ────────────────────────────────────────────────────────────

@app.route("/api/system", methods=["GET"])
def get_system():
    return jsonify({"system_prompt": _state["system_prompt"]})


@app.route("/api/system", methods=["POST"])
def set_system():
    data = request.get_json(force=True)
    _state["system_prompt"] = data.get("system_prompt", _state["system_prompt"])
    return jsonify({"system_prompt": _state["system_prompt"]})

# ── Chat ─────────────────────────────────────────────────────────────────────

def _build_agent():
    """Build a LangGraph agent with tools and Chroma context."""
    if not _state["model"]:
        raise ValueError("No model selected. POST /api/models first.")

    llm = ChatOllama(
        model=_state["model"],
        temperature=0,
        num_ctx=NUM_CTX,
        base_url="http://localhost:11434",
    )

    tools = _get_selected_tools()

    agent = create_agent(
        model=llm,
        tools=tools or None,
        system_prompt=_state["system_prompt"],
        middleware=[ToolCallFixerMiddleware()] if tools else [],
        checkpointer=_checkpointer,
    )
    return agent


def _agent_config() -> dict:
    """Return the config dict with thread_id for the checkpointer."""
    return {"configurable": {"thread_id": _state["thread_id"]}}


# ── /api/chat (non-streaming) ─────────────────────────────
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"error": "message required"}), 400
    if not _state["model"]:
        return jsonify({"error": "No model selected. POST /api/models first."}), 400

    _state["history"].append({"role": "user", "content": user_msg})

    try:
        agent = _build_agent()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    config = _agent_config()

    try:
        context = get_relevant_context(user_msg)
        enriched = f"[Context]\n{context}\n\n[User]\n{user_msg}" if context else user_msg

        result = agent.invoke(
            {"messages": [HumanMessage(content=enriched)]},
            config,
        )

        response = next(
            (m.content for m in reversed(result.get("messages", []))
             if isinstance(m, AIMessage) and m.content),
            ""
        )
        _state["history"].append({"role": "assistant", "content": response})
        return jsonify({"response": response})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── /api/chat/stream (streaming) ─────────────────────────
@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    data = request.get_json(force=True)
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"error": "message required"}), 400
    if not _state["model"]:
        return jsonify({"error": "No model selected. POST /api/models first."}), 400

    _state["history"].append({"role": "user", "content": user_msg})
    _cancel_event.clear()

    try:
        agent = _build_agent()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    config = _agent_config()

    def generate():
        full_response = ""
        pending_tool_calls = {}

        try:
            context = get_relevant_context(user_msg)
            enriched = f"[Context]\n{context}\n\n[User]\n{user_msg}" if context else user_msg

            for chunk, metadata in agent.stream(
                {"messages": [HumanMessage(content=enriched)]},
                config,
                stream_mode="messages",
            ):
                if _cancel_event.is_set():
                    yield json.dumps({"error": "Cancelled by user"}) + "\n"
                    return

                if isinstance(chunk, AIMessageChunk):
                    if chunk.content:
                        full_response += chunk.content
                        yield json.dumps({"token": chunk.content}) + "\n"
                    for tc in (chunk.tool_call_chunks or []):
                        tc_id = tc.get("id") or tc.get("index", "")
                        if tc_id not in pending_tool_calls:
                            pending_tool_calls[tc_id] = {"name": tc.get("name", ""), "args": ""}
                        if tc.get("name"):
                            pending_tool_calls[tc_id]["name"] = tc["name"]
                        if tc.get("args"):
                            pending_tool_calls[tc_id]["args"] += tc["args"]

                elif isinstance(chunk, AIMessage) and chunk.tool_calls:
                    for call in chunk.tool_calls:
                        yield json.dumps({"tool_call": {
                            "tool": call.get("name", ""),
                            "input": str(call.get("args", "")),
                        }}) + "\n"

                elif isinstance(chunk, ToolMessage):
                    tool_name = getattr(chunk, "name", "")
                    raw = str(chunk.content)
                    yield json.dumps({"tool_result": {"tool": tool_name, "output": raw[:500]}}) + "\n"
                    if tool_name == "download_image":
                        try:
                            img_data = json.loads(raw)
                            if img_data.get("status") == "ok":
                                yield json.dumps({"image": {
                                    "src": img_data["local_path"],
                                    "filename": img_data.get("filename", ""),
                                    "size_kb": img_data.get("size_kb", 0),
                                }}) + "\n"
                        except (json.JSONDecodeError, KeyError):
                            pass

        except Exception as e:
            yield json.dumps({"error": str(e)}) + "\n"
            return

        for tc_id, tc_info in pending_tool_calls.items():
            if tc_info["name"]:
                yield json.dumps({"tool_call": {"tool": tc_info["name"], "input": tc_info["args"]}}) + "\n"

        _state["history"].append({"role": "assistant", "content": full_response})

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
    
@app.route("/api/chat/cancel", methods=["POST"])
def chat_cancel():
    """Signal the running agent stream to stop."""
    _cancel_event.set()
    return jsonify({"cancelled": True})


# ── WebSocket endpoint for remote tool execution ─────────────────────────────
# Remote clients connect here. The server runs the LLM, but tool calls are
# sent to the client for local execution. Protocol (NDJSON over WebSocket):
#
#   Client → Server:  {"message": "read my file /tmp/foo.py"}
#   Server → Client:  {"token": "Let me "}
#   Server → Client:  {"token": "read that file."}
#   Server → Client:  {"tool_call": {"id": "...", "tool": "read_file", "params": {"path": "/tmp/foo.py"}}}
#   Client → Server:  {"tool_result": {"id": "...", "output": "contents..."}}
#   Server → Client:  {"token": "Here's what I found..."}
#   Server → Client:  {"done": true}

@sock.route("/api/chat/ws")
def chat_ws(ws):
    """WebSocket endpoint for remote-mode chat with client-side tool execution."""
    # Auth check — flask-sock bypasses before_request, so check manually
    # The first message must be a JSON auth + chat payload
    try:
        raw = ws.receive(timeout=30)
        if raw is None:
            ws.close()
            return
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        ws.send(json.dumps({"error": "Invalid JSON"}))
        ws.close()
        return

    # Authenticate
    key = data.get("api_key", "")
    if key != EXTERNAL_API_KEY:
        ws.send(json.dumps({"error": "Unauthorized"}))
        ws.close()
        return

    user_msg = data.get("message", "").strip()
    if not user_msg:
        ws.send(json.dumps({"error": "message required"}))
        ws.close()
        return

    if not _state["model"]:
        ws.send(json.dumps({"error": "No model selected"}))
        ws.close()
        return

    # Build LLM with tools bound (but we execute the tool loop manually)
    llm = ChatOllama(
        model=_state["model"],
        temperature=0,
        num_ctx=NUM_CTX,
        base_url="http://localhost:11434",
    )
    tools = _get_selected_tools()
    if tools:
        llm = llm.bind_tools(tools)

    context = get_relevant_context(user_msg)
    enriched = f"[Context]\n{context}\n\n[User]\n{user_msg}" if context else user_msg

    messages = [
        SystemMessage(content=_state["system_prompt"]),
        HumanMessage(content=enriched),
    ]

    MAX_TOOL_ROUNDS = 10

    try:
        for _round in range(MAX_TOOL_ROUNDS):
            # Stream the LLM response
            full_content = ""
            tool_calls_acc = []

            for chunk in llm.stream(messages):
                if isinstance(chunk, AIMessageChunk):
                    if chunk.content:
                        full_content += chunk.content
                        ws.send(json.dumps({"token": chunk.content}))
                    # Accumulate tool call chunks
                    for tc in (chunk.tool_call_chunks or []):
                        tc_id = tc.get("id") or tc.get("index", "")
                        # Find or create accumulator for this tool call
                        existing = next((t for t in tool_calls_acc if t["id"] == tc_id), None)
                        if existing is None:
                            existing = {"id": tc_id, "name": tc.get("name", ""), "args": ""}
                            tool_calls_acc.append(existing)
                        if tc.get("name"):
                            existing["name"] = tc["name"]
                        if tc.get("args"):
                            existing["args"] += tc["args"]

            # Also check for complete tool_calls on the accumulated message
            # Build the AI message for history
            parsed_tool_calls = []
            for tc_info in tool_calls_acc:
                if tc_info["name"]:
                    try:
                        args = json.loads(tc_info["args"]) if tc_info["args"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    parsed_tool_calls.append(ToolCall(
                        name=tc_info["name"],
                        args=args,
                        id=tc_info["id"] or str(uuid4()),
                    ))

            # If no tool calls from native protocol, try text-based extraction
            if not parsed_tool_calls and full_content:
                extracted = _extract_tool_calls(full_content)
                if extracted:
                    parsed_tool_calls = extracted
                    full_content = ""  # tool call was in text, not real content

            ai_msg = AIMessage(
                content=full_content,
                tool_calls=parsed_tool_calls,
            )
            messages.append(ai_msg)

            if not parsed_tool_calls:
                # No tool calls — final response, we're done
                break

            # Send tool calls to client, collect results
            tool_results = []
            for tc in parsed_tool_calls:
                ws.send(json.dumps({
                    "tool_call": {
                        "id": tc["id"],
                        "tool": tc["name"],
                        "params": tc["args"],
                    }
                }))

                # Wait for client to send back the result
                try:
                    result_raw = ws.receive(timeout=120)
                    if result_raw is None:
                        tool_results.append(ToolMessage(
                            content="Error: client disconnected",
                            tool_call_id=tc["id"],
                            name=tc["name"],
                        ))
                        continue
                    result_data = json.loads(result_raw)
                    output = result_data.get("tool_result", {}).get("output", "")
                    tool_results.append(ToolMessage(
                        content=str(output),
                        tool_call_id=tc["id"],
                        name=tc["name"],
                    ))
                except Exception as e:
                    tool_results.append(ToolMessage(
                        content=f"Error receiving tool result: {e}",
                        tool_call_id=tc["id"],
                        name=tc["name"],
                    ))

            messages.extend(tool_results)
            # Loop continues — LLM will see tool results and may call more tools

        ws.send(json.dumps({"done": True}))

    except Exception as e:
        try:
            ws.send(json.dumps({"error": str(e)}))
        except Exception:
            pass

    try:
        ws.close()
    except Exception:
        pass


# ── Agent proxy endpoints ────────────────────────────────────────────────────

@app.route("/api/agent/<agent_name>/call", methods=["POST"])
def call_agent(agent_name: str):
    """Proxy a tool call to a specific agent.

    Body: {"tool": "tool_name", "params": {...}}
    """
    if agent_name not in AGENT_PORTS:
        return jsonify({"error": f"Unknown agent: {agent_name}"}), 404

    data = request.get_json(force=True)
    tool_name = data.get("tool", "")
    params = data.get("params", {})

    try:
        url = agent_url(agent_name)
        resp = httpx.post(
            f"{url}/call",
            json={"tool": tool_name, "params": params},
            timeout=60.0,
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/agents", methods=["GET"])
def list_agents():
    """List all available agents and their status."""
    agents = {}
    for name, port in AGENT_PORTS.items():
        try:
            resp = httpx.get(
                f"http://127.0.0.1:{port}/health",
                timeout=2.0,
            )
            resp.raise_for_status()
            data = resp.json()
            agents[name] = {"port": port, "status": "up", "tools": data.get("tools", [])}
        except Exception:
            agents[name] = {"port": port, "status": "down"}
    return jsonify(agents)


@app.route("/api/history", methods=["GET"])
def get_history():
    return jsonify({"history": _state["history"]})


@app.route("/api/history", methods=["DELETE"])
def clear_history():
    _state["history"] = []
    _state["thread_id"] = str(uuid4())  # new thread = fresh checkpointer memory
    return jsonify({"cleared": True})


# ── CLI tool browser (for terminal use) ─────────────────────────────────────

def cli_tool_browser():
    """Interactive 2-column tool browser for the terminal."""
    selected_idx = set()

    while True:
        available = [(i, [get_tools()]) for i in range(len( [get_tools()])) if i not in selected_idx]
        selected = [(i, [get_tools()]) for i in sorted(selected_idx)]

        # Render 2 columns
        col_w = 38
        print("\n" + "=" * (col_w * 2 + 7))
        print(f"{'AVAILABLE':<{col_w}}  | >  | {'SELECTED':<{col_w}}")
        print("-" * (col_w * 2 + 7))

        max_rows = max(len(available), len(selected), 1)
        for row in range(max_rows):
            left = f"  {available[row][0]:>2}. {available[row][1]['name']}" if row < len(available) else ""
            right = f"  {selected[row][0]:>2}. {selected[row][1]['name']}" if row < len(selected) else ""
            print(f"{left:<{col_w}}  |    | {right:<{col_w}}")

        print("-" * (col_w * 2 + 7))
        print("Commands:  > N  (select)   < N  (deselect)   ? N  (inspect)   q  (done)")
        cmd = input("> ").strip()

        if cmd.lower() == "q":
            break
        elif cmd.startswith(">"):
            try:
                idx = int(cmd[1:].strip())
                if 0 <= idx < len([get_tools()]):
                    selected_idx.add(idx)
                    meta = [get_tools()]
                    print(f"\n  + {meta['name']}: {meta['description']}")
                    if meta["params"]:
                        print("    Params required from user:")
                        for pn, pi in meta["params"].items():
                            req = "*" if pi["required"] else ""
                            default = f" (default: {pi.get('default', '')})" if "default" in pi else ""
                            print(f"      {req}{pn} ({pi['type']}){default}: {pi['description']}")
            except ValueError:
                print("  Usage: > N")
        elif cmd.startswith("<"):
            try:
                idx = int(cmd[1:].strip())
                selected_idx.discard(idx)
            except ValueError:
                print("  Usage: < N")
        elif cmd.startswith("?"):
            try:
                idx = int(cmd[1:].strip())
                TOOL_REGISTRY = get_tools()
                if 0 <= idx < len(TOOL_REGISTRY):
                    meta = TOOL_REGISTRY[idx]
                    print(f"\n  {meta['name']}: {meta['description']}")
                    for pn, pi in meta["params"].items():
                        req = "*" if pi["required"] else ""
                        default = f" (default: {pi.get('default', '')})" if "default" in pi else ""
                        print(f"    {req}{pn} ({pi['type']}){default}: {pi['description']}")
            except ValueError:
                print("  Usage: ? N")

    _state["selected_tools"] = sorted(selected_idx)
    # print(f"\nSelected {len(selected_idx)} tools (all {len(ALL_TOOLS)} are still bound to agent).")


def cli_model_picker():
    """Interactive model picker for the terminal (abliterated models only)."""
    try:
        models = ollama_client.list()
        names = [m.model for m in models.models if _is_abliterated(m.model)]
    except Exception as e:
        print(f"Error listing models: {e}")
        return

    if not names:
        print("\nNo abliterated models found locally. Pull one with: ollama pull huihui_ai/qwen2.5-coder-abliterate:14b")
        return

    print("\nAvailable abliterated Ollama models:")
    for i, name in enumerate(names):
        marker = " *" if name == _state["model"] else ""
        print(f"  {i:>2}. {name}{marker}")

    choice = input("\nSelect model number (or Enter to keep current): ").strip()
    if choice.isdigit() and 0 <= int(choice) < len(names):
        _state["model"] = names[int(choice)]
        print(f"Model set to: {_state['model']}")


def cli_chat():
    """Interactive chat loop for the terminal."""
    if not _state["model"]:
        print("No model selected. Pick one first.")
        cli_model_picker()
        if not _state["model"]:
            return

    # print(f"\nChat with {_state['model']} ({len(ALL_TOOLS)} tools bound)")
    print("Type 'quit' to exit, 'clear' to reset history.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "clear":
            _state["history"] = []
            _state["thread_id"] = str(uuid4())
            print("  (history cleared)")
            continue

        agent = _build_agent()
        config = _agent_config()
        _state["history"].append({"role": "user", "content": user_input})

        print("Agent: ", end="", flush=True)
        try:
            result = agent.invoke(
                {"messages": [HumanMessage(content=user_input)]},
                config,
            )
            output_msgs = result.get("messages", [])
            response = ""
            for msg in reversed(output_msgs):
                if isinstance(msg, AIMessage) and msg.content:
                    response = msg.content
                    break
            _state["history"].append({"role": "assistant", "content": response})
            print(response)
        except Exception as e:
            print(f"\n  [Error: {e}]")


def main():
    import sys

    if "--serve" in sys.argv:
        port = 5000
        for arg in sys.argv:
            if arg.startswith("--port="):
                port = int(arg.split("=")[1])
        print(f"Starting Flask API on http://localhost:{port}")
        app.run(host="0.0.0.0", port=port, debug=False)
    else:
        # Interactive CLI mode
        print("=== Agentic Chat (LangChain + Ollama) ===")
        while True:
            print("\n  1. Pick model")
            print("  2. Browse tools")
            print("  3. Chat")
            print("  4. Set system prompt")
            print("  5. Start API server")
            print("  q. Quit")
            choice = input("\n> ").strip()

            if choice == "1":
                cli_model_picker()
            elif choice == "2":
                cli_tool_browser()
            elif choice == "3":
                cli_chat()
            elif choice == "4":
                prompt = input("System prompt: ").strip()
                if prompt:
                    _state["system_prompt"] = prompt
                    print("  Updated.")
            elif choice == "5":
                app.run(host="0.0.0.0", port=5000, debug=False)
            elif choice.lower() == "q":
                break


if __name__ == "__main__":
    main()
