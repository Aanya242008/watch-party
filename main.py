import asyncio
import inspect
import re
import time

import socketio
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
web = FastAPI()
# FIX 1: wrap FastAPI *inside* the Socket.IO ASGI app instead of mounting it at /socket.io.
# The old mount stripped the path, so the socket never connected (no sync, no votes, no chat).
app = socketio.ASGIApp(sio, other_asgi_app=web)

DEFAULT_VIDEO = "aqz-KE-bpKQ"  # Big Buck Bunny (embeddable)
VID_RE = re.compile(r"^[\w-]{11}$")
PRIVATE = {"choices", "cids", "host"}  # never sent to browsers
rooms = {}
calls = {}     # room -> set of sids currently in the video call
sid_room = {}  # sid -> room, so we can clean up on disconnect
MAX_CALL = 6   # mesh WebRTC gets heavy beyond ~6 people


def get_room(name):
    return rooms.setdefault(
        name, {"video": DEFAULT_VIDEO, "time": 0, "playing": False, "at": time.time(), "votes": [0, 0, 0], "choices": {}, "host": None, "open": False, "cids": {}, "queue": []}
    )


def snapshot(r):
    s = {k: v for k, v in r.items() if k not in PRIVATE}
    if s["playing"]:
        s["time"] += time.time() - s["at"]
    return s


def state_for(name, sid):
    r = get_room(name)
    cid = r["cids"].get(sid)
    s = snapshot(r)
    s["mine"] = r["choices"].get(cid) if cid else None
    s["isHost"] = cid is not None and cid == r["host"]
    return s


def can_control(r, sid):
    return r["open"] or (r["host"] is not None and r["cids"].get(sid) == r["host"])


async def push_perms(name, r):
    for sid, cid in list(r["cids"].items()):
        await sio.emit("perms", {"isHost": cid == r["host"], "open": r["open"]}, to=sid)


async def play_video(name, r, vid):
    r.update(video=vid, time=0, playing=True, at=time.time())
    await sio.emit("sync_video", {"videoId": vid}, room=name)
    await sio.emit("queue", r["queue"], room=name)


async def promote_later(name, old_host):
    await asyncio.sleep(15)  # grace period, e.g. the host just refreshed the page
    r = rooms.get(name)
    if not r or r["host"] != old_host or old_host in r["cids"].values():
        return
    if not r["cids"]:
        rooms.pop(name, None)  # empty room: free the memory
        calls.pop(name, None)
        return
    r["host"] = next(iter(r["cids"].values()))
    await push_perms(name, r)


def room_of(data):
    return str(data.get("room", "lobby"))[:40]


HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WatchParty</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Fraunces:opsz,wght@9..144,600;9..144,800&display=swap" rel="stylesheet">
<style>
:root{--ink:#12081a;--velvet:#2b1527;--panel:#1d0e1c;--line:#5c2c3e;--gold:#f5c26b;--cream:#f3e9d8;--muted:#b79bab;--live:#ff6b5e}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;font-family:'DM Sans',sans-serif;color:var(--cream);
 background:radial-gradient(ellipse 55% 45% at 50% -8%,rgba(255,220,150,.38),transparent 70%),linear-gradient(#12081a,#07030c);
 padding:22px clamp(46px,9vw,140px)}
body::before,body::after{content:"";position:fixed;top:0;bottom:0;width:clamp(34px,8vw,130px);z-index:0;pointer-events:none;
 background:repeating-linear-gradient(90deg,#4a0814 0,#8e1426 16px,#5c0b19 30px,#35050e 40px)}
body::before{left:0;box-shadow:10px 0 36px rgba(0,0,0,.75)}
body::after{right:0;box-shadow:-10px 0 36px rgba(0,0,0,.75)}
@media(max-width:700px){body{padding:14px 24px}body::before,body::after{width:14px}}
.wrap{position:relative;z-index:1;max-width:1240px;margin:0 auto}
header{position:relative;display:flex;justify-content:space-between;align-items:center;margin-bottom:26px;gap:12px;flex-wrap:wrap;padding:16px 22px;background:#1a0b17;border:2px solid var(--gold);border-radius:12px;box-shadow:0 0 28px rgba(245,194,107,.3)}
header::before,header::after{content:"";position:absolute;left:12px;right:12px;height:8px;background:radial-gradient(circle,#ffeaa8 0 2.5px,transparent 3.5px) 0 0/20px 8px repeat-x;filter:drop-shadow(0 0 4px #f5c26b);animation:bulbs 1.8s ease-in-out infinite alternate}
header::before{top:-5px}
header::after{bottom:-5px;animation-delay:.9s}
@keyframes bulbs{to{opacity:.4}}
@media(prefers-reduced-motion:reduce){header::before,header::after{animation:none}}
h1{font-family:'Fraunces',serif;font-weight:800;font-size:30px;margin:0;letter-spacing:-.5px;color:var(--gold);text-shadow:0 0 16px rgba(245,194,107,.55)}
.screen{position:relative;padding:0 30px;background:#0a0a0a;border-radius:10px;box-shadow:0 0 90px rgba(255,214,140,.22),0 20px 40px rgba(0,0,0,.6)}
.screen .stage{border-radius:4px;box-shadow:none}
.screen::before,.screen::after{content:"";position:absolute;top:6px;bottom:6px;width:14px;background:linear-gradient(180deg,#d9ccb0 0 12px,transparent 12px 30px) 0 0/14px 30px repeat-y;border-radius:2px;opacity:.85}
.screen::before{left:8px}
.screen::after{right:8px}
.opt.mine{border-color:var(--gold)}
.controls h3{font-family:'Fraunces',serif;font-size:15px;margin:4px 0 0}
#queue{display:flex;flex-direction:column;gap:8px}
.qi{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.qi img{width:96px;aspect-ratio:16/9;object-fit:cover;border-radius:6px;background:#000}
.qi span{flex:1;min-width:120px;font-size:13px;color:var(--muted);word-break:break-all}
.qi button{padding:6px 10px;font-size:13px}
.empty{color:var(--muted);font-size:13px}
button:disabled{opacity:.45;cursor:not-allowed}
.ticket{border:1.5px dashed var(--gold);color:var(--gold);padding:6px 16px;border-radius:8px;font-weight:700;font-size:14px}
.grid{display:grid;grid-template-columns:1fr 360px;gap:18px}
@media(max-width:960px){.grid{grid-template-columns:1fr}}
.stage{aspect-ratio:16/9;background:#000;border-radius:14px;overflow:hidden;box-shadow:0 0 80px rgba(245,194,107,.18),0 20px 40px rgba(0,0,0,.5)}
.stage iframe{width:100%;height:100%;border:0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px}
.controls{margin-top:16px;padding:16px;display:flex;flex-direction:column;gap:12px}
.row{display:flex;gap:10px;flex-wrap:wrap}
input,select{flex:1;min-width:0;background:var(--velvet);color:var(--cream);border:1px solid var(--line);padding:11px 14px;border-radius:10px;font:inherit;font-size:14px}
input:focus,select:focus,button:focus-visible{outline:2px solid var(--gold);outline-offset:1px}
button{background:var(--gold);color:#2a1d05;border:0;padding:11px 18px;border-radius:10px;font:inherit;font-weight:700;cursor:pointer}
button.ghost{background:transparent;color:var(--cream);border:1px solid var(--line)}
button:hover{filter:brightness(1.08)}
.emoji{display:flex;gap:8px}
.emoji button{background:var(--velvet);border:1px solid var(--line);font-size:20px;padding:8px 14px}
#status{font-size:13px;color:var(--muted);min-height:18px}
#status.err{color:var(--live)}
.side{display:flex;flex-direction:column;gap:18px}
.chat{display:flex;flex-direction:column;height:380px}
.card h2{font-family:'Fraunces',serif;font-size:16px;margin:0;padding:14px 16px;border-bottom:1px solid var(--line)}
#msgs{flex:1;overflow-y:auto;padding:12px 16px;display:flex;flex-direction:column;gap:8px}
.msg{font-size:14px;line-height:1.4;word-break:break-word}
.msg b{color:var(--gold)}
.msg.sys{color:var(--muted);font-style:italic}
.send{display:flex;gap:8px;padding:12px;border-top:1px solid var(--line)}
.poll{padding-bottom:14px}
.poll p{margin:12px 16px 8px;font-weight:700}
.opt{position:relative;display:block;width:calc(100% - 32px);margin:6px 16px;text-align:left;background:var(--velvet);color:var(--cream);border:1px solid var(--line);overflow:hidden}
.opt i{position:absolute;inset:0 auto 0 0;background:rgba(245,194,107,.25);width:0;transition:width .3s}
.opt span{position:relative;display:flex;justify-content:space-between}
.call{padding-bottom:4px}
.tiles{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;padding:0 12px 12px}
.tiles video{width:100%;aspect-ratio:4/3;object-fit:cover;background:#000;border-radius:10px}
.callbar{display:flex;gap:8px;padding:12px;flex-wrap:wrap}
.callbar button{flex:1;padding:9px 10px;font-size:13px}
#float{position:fixed;left:20px;bottom:20px;pointer-events:none;z-index:9}
.fe{position:absolute;font-size:30px;animation:up 2s ease-out forwards}
@keyframes up{to{transform:translateY(-320px) scale(1.4);opacity:0}}
@media(prefers-reduced-motion:reduce){.fe{animation-duration:.01s}}
</style>
</head>
<body>
<div class="wrap">
 <header><h1>WatchParty</h1><div class="row" style="align-items:center"><input id="nameIn" maxlength="20" placeholder="Your name" aria-label="Your name" style="width:150px;flex:none"><div class="ticket" id="roomBadge">Room</div><button class="ghost" onclick="copyInvite()" style="padding:7px 14px">Copy invite link</button></div></header>
 <div class="grid">
  <div>
   <div class="screen"><div class="stage"><div id="player"></div></div></div>
   <div class="card controls">
    <div class="row">
     <input id="url" placeholder="Paste a YouTube link (video or live stream)">
     <button id="loadBtn" onclick="loadUrl()">Load now</button><button class="ghost" onclick="addQueue()">Add to queue</button>
    </div>
    <div class="row">
     <select id="preset" onchange="loadPreset()">
      <option value="">Pick a video</option>
      <option value="aqz-KE-bpKQ">Big Buck Bunny</option>
      <option value="eRsGyueVLvQ">Sintel</option>
      <option value="R6MlUcmOul8">Tears of Steel</option>
      <option value="jfKfPfyJRdk">Lofi Girl (live stream)</option>
     </select>
     <button class="ghost" onclick="socket.emit('request_state',{room,cid})">Sync with room</button>
    </div>
    <div class="emoji" id="emoji"></div>
    <div id="status"></div>
    <div class="row" style="align-items:center"><span id="role" style="flex:1;font-size:13px;color:var(--muted)"></span><button class="ghost" id="openBtn" onclick="toggleOpen()" hidden style="padding:6px 12px;font-size:13px"></button></div>
    <h3>Up next</h3>
    <div id="queue"></div>
   </div>
  </div>
  <div class="side">
   <div class="card call">
    <h2>Video call</h2>
    <div class="callbar">
     <button id="joinBtn" onclick="joinCall()">Join video call</button>
     <button class="ghost" id="micBtn" onclick="toggleTrack('audio')" hidden>Mute</button>
     <button class="ghost" id="camBtn" onclick="toggleTrack('video')" hidden>Camera off</button>
     <button class="ghost" id="leaveBtn" onclick="leaveCall()" hidden>Leave</button>
    </div>
    <div class="tiles" id="tiles"></div>
   </div>
   <div class="card chat">
    <h2>Room chat</h2>
    <div id="msgs"><div class="msg sys">Share this page's link to invite friends to this room.</div></div>
    <div class="send"><input id="chatIn" placeholder="Say something"><button onclick="sendChat()">Send</button></div>
   </div>
   <div class="card poll">
    <h2>What should we watch next?</h2>
    <div id="opts"></div>
   </div>
  </div>
 </div>
</div>
<div id="float"></div>

<script>
const socket = io();  // default path /socket.io now works
let roomParam = new URLSearchParams(location.search).get('room');
if (!roomParam) { roomParam = Math.random().toString(36).slice(2, 8); history.replaceState(null, '', '?room=' + roomParam); }
const room = roomParam.trim();
let me = 'Guest' + Math.floor(Math.random() * 900 + 100);
const OPTIONS = ['Action blockbuster', 'Sci-fi adventure', 'Comedy or animation'];
document.getElementById('roomBadge').textContent = 'Room: ' + room;

const $ = id => document.getElementById(id);
function say(t, err) { const s = $('status'); s.textContent = t; s.className = err ? 'err' : ''; }

// ---------- Username ----------
try { const saved = localStorage.getItem('wp_name'); if (saved) me = saved; } catch {}
$('nameIn').value = me;
$('nameIn').addEventListener('change', () => {
  const n = $('nameIn').value.trim().slice(0, 20);
  if (n) me = n;
  $('nameIn').value = me;
  try { localStorage.setItem('wp_name', me); } catch {}
});

// ---------- YouTube ----------
let player, ready = false, remote = false, remoteTimer, pending = null;
const tag = document.createElement('script');
tag.src = 'https://www.youtube.com/iframe_api';
document.head.appendChild(tag);

function onYouTubeIframeAPIReady() {
  player = new YT.Player('player', {
    width: '100%', height: '100%', videoId: 'aqz-KE-bpKQ',
    playerVars: { playsinline: 1, rel: 0, origin: location.origin },
    events: {
      onReady: () => { ready = true; if (pending) applyState(pending); socket.emit('request_state', { room, cid }); },
      onStateChange,
      onError: e => say('YouTube refused to play this video here (error ' + e.data + '). The owner may have blocked embedding. Try another video.', true)
    }
  });
}

function lock(ms = 1200) {
  remote = true; clearTimeout(remoteTimer);
  remoteTimer = setTimeout(() => remote = false, ms);
}
function isLive() { try { return !!player.getVideoData().isLive; } catch { return false; } }
function curId() { try { return player.getVideoData().video_id; } catch { return null; } }

function onStateChange(e) {
  if (e.data === YT.PlayerState.ENDED && canControl() && !remote) { socket.emit('video_ended', { room, videoId: curId() }); return; }
  if (remote) return;
  const live = isLive();
  if (e.data === YT.PlayerState.PLAYING) socket.emit('media_state', { room, action: 'play', time: live ? 0 : player.getCurrentTime() });
  else if (e.data === YT.PlayerState.PAUSED) socket.emit('media_state', { room, action: 'pause', time: live ? 0 : player.getCurrentTime() });
}

function applyState(s) {
  if (!ready) { pending = s; return; }
  lock(1800);
  if (s.video && s.video !== curId()) {
    player.loadVideoById({ videoId: s.video, startSeconds: s.time || 0 });
    if (!s.playing) setTimeout(() => player.pauseVideo(), 600);
    return;
  }
  if (!isLive() && Math.abs(player.getCurrentTime() - s.time) > 1.5) player.seekTo(s.time, true);
  s.playing ? player.playVideo() : player.pauseVideo();
}

function extractId(u) {
  const m = u.match(/(?:youtu\\.be\\/|youtube\\.com\\/(?:watch\\?(?:.*&)?v=|embed\\/|live\\/|shorts\\/|v\\/))([\\w-]{11})/);
  return m ? m[1] : (/^[\\w-]{11}$/.test(u) ? u : null);
}
function startVideo(id) {
  if (!canControl()) { say('Only the host can start a video. Use Add to queue instead.', true); return; }
  lock(1800);
  player.loadVideoById(id);
  socket.emit('video_change', { room, videoId: id });
  say('');
}
function loadUrl() {
  const id = extractId($('url').value.trim());
  id ? startVideo(id) : say('That does not look like a YouTube link.', true);
}
function loadPreset() { const v = $('preset').value; if (v && canControl()) startVideo(v); }

// ---------- Socket events ----------
let cid = '';
try { cid = sessionStorage.getItem('wp_cid') || ''; } catch {}
if (!cid) { cid = Math.random().toString(36).slice(2, 12); try { sessionStorage.setItem('wp_cid', cid); } catch {} }
socket.on('connect', () => socket.emit('join_room', { room, cid }));
socket.on('state', s => { applyState(s); myVote = s.mine ?? null; renderPoll(s.votes); lastQueue = s.queue || []; applyPerms(s); });
socket.on('sync_media', d => {
  if (!ready) return;
  lock();
  if (!isLive() && Math.abs(player.getCurrentTime() - d.time) > 1) player.seekTo(d.time, true);
  d.action === 'play' ? player.playVideo() : player.pauseVideo();
});
socket.on('sync_video', d => { if (ready) { lock(1800); player.loadVideoById(d.videoId); } });

// ---------- Chat (uses textContent, so no HTML injection) ----------
function addMsg(user, text) {
  const d = document.createElement('div'); d.className = 'msg';
  const b = document.createElement('b'); b.textContent = user + ': ';
  d.append(b, document.createTextNode(text));
  $('msgs').appendChild(d); $('msgs').scrollTop = $('msgs').scrollHeight;
}
function sendChat() {
  const t = $('chatIn').value.trim();
  if (t) { socket.emit('chat_message', { room, user: me, text: t.slice(0, 300) }); $('chatIn').value = ''; }
}
$('chatIn').addEventListener('keydown', e => { if (e.key === 'Enter') sendChat(); });
socket.on('receive_chat', d => addMsg(d.user, d.text));

// ---------- Video call (WebRTC mesh, signalling over Socket.IO) ----------
const ICE = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] };
let localStream = null;
const peers = {};

function addTile(id, stream, muted) {
  let v = document.getElementById('t-' + id);
  if (!v) {
    v = document.createElement('video'); v.id = 't-' + id;
    v.autoplay = true; v.playsInline = true;
    $('tiles').appendChild(v);
  }
  v.muted = !!muted; v.srcObject = stream;
}
function dropTile(id) { const v = document.getElementById('t-' + id); if (v) v.remove(); }

function closePeer(id) {
  const pc = peers[id]; delete peers[id];
  if (pc) pc.close();
  dropTile(id);
}
function makePeer(id) {
  const pc = new RTCPeerConnection(ICE);
  peers[id] = pc;
  localStream.getTracks().forEach(t => pc.addTrack(t, localStream));
  pc.onicecandidate = e => e.candidate && socket.emit('rtc_signal', { to: id, data: { candidate: e.candidate } });
  pc.ontrack = e => addTile(id, e.streams[0], false);
  pc.onconnectionstatechange = () => { if (pc.connectionState === 'failed') closePeer(id); };
  return pc;
}

async function joinCall() {
  try {
    localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: { echoCancellation: true, noiseSuppression: true } });
  } catch (e) {
    say('Could not open camera or mic (' + e.message + '). Camera access needs localhost or https.', true);
    return;
  }
  addTile('me', localStream, true);
  $('joinBtn').hidden = true;
  ['micBtn', 'camBtn', 'leaveBtn'].forEach(i => $(i).hidden = false);
  socket.emit('rtc_join', { room });
}

function toggleTrack(kind) {
  const t = localStream && localStream.getTracks().find(x => x.kind === kind);
  if (!t) return;
  t.enabled = !t.enabled;
  if (kind === 'audio') $('micBtn').textContent = t.enabled ? 'Mute' : 'Unmute';
  else $('camBtn').textContent = t.enabled ? 'Camera off' : 'Camera on';
}

function leaveCall() {
  socket.emit('rtc_leave', { room });
  Object.keys(peers).forEach(closePeer);
  if (localStream) localStream.getTracks().forEach(t => t.stop());
  localStream = null; dropTile('me');
  $('joinBtn').hidden = false;
  ['micBtn', 'camBtn', 'leaveBtn'].forEach(i => $(i).hidden = true);
  $('micBtn').textContent = 'Mute'; $('camBtn').textContent = 'Camera off';
}

// The person who joins sends offers to everyone already in the call.
socket.on('rtc_peers', async d => {
  for (const id of d.peers) {
    const pc = makePeer(id);
    await pc.setLocalDescription(await pc.createOffer());
    socket.emit('rtc_signal', { to: id, data: { sdp: pc.localDescription } });
  }
});
socket.on('rtc_signal', async d => {
  if (!localStream) return;
  const pc = peers[d.from] || makePeer(d.from);
  if (d.data.sdp) {
    await pc.setRemoteDescription(d.data.sdp);
    if (d.data.sdp.type === 'offer') {
      await pc.setLocalDescription(await pc.createAnswer());
      socket.emit('rtc_signal', { to: d.from, data: { sdp: pc.localDescription } });
    }
  } else if (d.data.candidate) {
    try { await pc.addIceCandidate(d.data.candidate); } catch {}
  }
});
socket.on('rtc_left', d => closePeer(d.sid));
socket.on('rtc_full', () => { say('The call is full (max 6 people).', true); leaveCall(); });

// ---------- Host controls, queue, invite link ----------
let isHost = false, openCtl = false, lastQueue = [];
const canControl = () => isHost || openCtl;

function applyPerms(p) {
  isHost = !!p.isHost; openCtl = !!p.open;
  $('loadBtn').disabled = !canControl();
  $('role').textContent = isHost ? 'You are the host.'
    : openCtl ? 'The host lets everyone control the player.'
    : 'The host controls the player. You can still add videos to the queue.';
  $('openBtn').hidden = !isHost;
  $('openBtn').textContent = openCtl ? 'Lock controls to me' : 'Let everyone control';
  renderQueue(lastQueue);
}
function toggleOpen() { socket.emit('set_open', { room, open: !openCtl }); }

function renderQueue(q) {
  lastQueue = q || [];
  const box = $('queue'); box.innerHTML = '';
  if (!lastQueue.length) {
    const d = document.createElement('div'); d.className = 'empty';
    d.textContent = 'Nothing queued. Paste a link or pick a video, then choose Add to queue.';
    box.appendChild(d); return;
  }
  lastQueue.forEach((id, i) => {
    const row = document.createElement('div'); row.className = 'qi';
    const img = document.createElement('img'); img.src = 'https://i.ytimg.com/vi/' + id + '/mqdefault.jpg'; img.alt = '';
    const t = document.createElement('span'); t.textContent = (i === 0 ? 'Plays next: ' : '#' + (i + 1) + ': ') + 'youtu.be/' + id;
    row.append(img, t);
    if (canControl()) {
      const p = document.createElement('button'); p.className = 'ghost'; p.textContent = 'Play now';
      p.onclick = () => socket.emit('queue_play', { room, index: i });
      const x = document.createElement('button'); x.className = 'ghost'; x.textContent = 'Remove';
      x.onclick = () => socket.emit('queue_remove', { room, index: i });
      row.append(p, x);
    }
    box.appendChild(row);
  });
}
function addQueue() {
  const id = extractId($('url').value.trim()) || $('preset').value;
  if (!id) { say('Paste a YouTube link or pick a video first.', true); return; }
  socket.emit('queue_add', { room, videoId: id });
  $('url').value = ''; $('preset').value = ''; say('Added to the queue.');
}
function copyInvite() {
  const url = location.href;
  (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(
    () => say('Invite link copied.'), () => prompt('Copy this link:', url));
}
socket.on('perms', applyPerms);
socket.on('queue', renderQueue);
applyPerms({ isHost: false, open: false });

// ---------- Reactions ----------
['❤️', '🔥', '😂', '👏', '🍿'].forEach(e => {
  const b = document.createElement('button'); b.textContent = e;
  b.onclick = () => socket.emit('send_reaction', { room, emoji: e });
  $('emoji').appendChild(b);
});
socket.on('show_reaction', d => {
  const el = document.createElement('div'); el.className = 'fe'; el.textContent = d.emoji;
  el.style.left = Math.random() * 200 + 'px'; $('float').appendChild(el);
  setTimeout(() => el.remove(), 2000);
});

// ---------- Poll ----------
let myVote = null;
function renderPoll(votes) {
  const total = votes.reduce((a, b) => a + b, 0) || 1;
  $('opts').innerHTML = '';
  OPTIONS.forEach((label, i) => {
    const b = document.createElement('button'); b.className = 'opt';
    b.classList.toggle('mine', myVote === i);
    b.onclick = () => { myVote = (myVote === i) ? null : i; socket.emit('submit_vote', { room, index: i, cid }); };
    b.innerHTML = '<i style="width:' + (votes[i] / total * 100) + '%"></i><span><em style="font-style:normal"></em><b>' + votes[i] + '</b></span>';
    b.querySelector('em').textContent = (myVote === i ? '✓ ' : '') + label;
    $('opts').appendChild(b);
  });
}
renderPoll([0, 0, 0]);
socket.on('update_poll', renderPoll);
</script>
</body>
</html>
"""


@web.get("/", response_class=HTMLResponse)
async def home():
    return HTML


@sio.event
async def join_room(sid, data):
    name = room_of(data)
    sid_room[sid] = name
    r = get_room(name)
    cid = str(data.get("cid") or sid)[:40]
    r["cids"][sid] = cid
    if r["host"] is None:
        r["host"] = cid  # first person in the room is the host
    # FIX 2: in newer python-socketio versions enter_room is a coroutine; handle both.
    res = sio.enter_room(sid, name)
    if inspect.isawaitable(res):
        await res
    # FIX 3: late joiners get the room's current video/time/poll.
    await sio.emit("state", state_for(name, sid), to=sid)
    await push_perms(name, r)


@sio.event
async def request_state(sid, data):
    await sio.emit("state", state_for(room_of(data), sid), to=sid)


@sio.event
async def media_state(sid, data):
    name = room_of(data)
    r = get_room(name)
    if not can_control(r, sid):
        await sio.emit("state", state_for(name, sid), to=sid)  # snap them back to the room
        return
    r.update(playing=data.get("action") == "play", time=float(data.get("time", 0)), at=time.time())
    await sio.emit("sync_media", data, room=name, skip_sid=sid)


@sio.event
async def video_change(sid, data):
    name = room_of(data)
    r = get_room(name)
    vid = str(data.get("videoId", ""))
    if not can_control(r, sid) or not VID_RE.match(vid):
        await sio.emit("state", state_for(name, sid), to=sid)
        return
    r.update(video=vid, time=0, playing=True, at=time.time())
    await sio.emit("sync_video", {"videoId": vid}, room=name, skip_sid=sid)


@sio.event
async def chat_message(sid, data):
    msg = {"user": str(data.get("user", "Guest"))[:20] or "Guest", "text": str(data.get("text", ""))[:300]}
    await sio.emit("receive_chat", msg, room=room_of(data))


@sio.event
async def send_reaction(sid, data):
    await sio.emit("show_reaction", data, room=room_of(data))


@sio.event
async def submit_vote(sid, data):
    name = room_of(data)
    r = get_room(name)
    idx = data.get("index")
    voter = str(data.get("cid", sid))[:40]
    if isinstance(idx, int) and 0 <= idx < 3:
        prev = r["choices"].get(voter)
        if prev is not None:
            r["votes"][prev] -= 1
        if prev == idx:  # clicking your own choice again removes your vote
            del r["choices"][voter]
        else:
            r["choices"][voter] = idx
            r["votes"][idx] += 1
    await sio.emit("update_poll", r["votes"], room=name)


# ---------- Host controls and queue ----------
@sio.event
async def set_open(sid, data):
    name = room_of(data)
    r = get_room(name)
    if r["host"] is not None and r["cids"].get(sid) == r["host"]:
        r["open"] = bool(data.get("open"))
        await push_perms(name, r)


@sio.event
async def queue_add(sid, data):
    name = room_of(data)
    r = get_room(name)
    vid = str(data.get("videoId", ""))
    if VID_RE.match(vid) and len(r["queue"]) < 20:
        r["queue"].append(vid)
        await sio.emit("queue", r["queue"], room=name)


@sio.event
async def queue_remove(sid, data):
    name = room_of(data)
    r = get_room(name)
    i = data.get("index")
    if can_control(r, sid) and isinstance(i, int) and 0 <= i < len(r["queue"]):
        r["queue"].pop(i)
        await sio.emit("queue", r["queue"], room=name)


@sio.event
async def queue_play(sid, data):
    name = room_of(data)
    r = get_room(name)
    i = data.get("index")
    if can_control(r, sid) and isinstance(i, int) and 0 <= i < len(r["queue"]):
        await play_video(name, r, r["queue"].pop(i))


@sio.event
async def video_ended(sid, data):
    name = room_of(data)
    r = get_room(name)
    if not can_control(r, sid) or data.get("videoId") != r["video"]:
        return  # only count the current video ending, so duplicate reports are ignored
    if r["queue"]:
        await play_video(name, r, r["queue"].pop(0))
    else:
        r.update(playing=False, at=time.time())


# ---------- Video call signalling ----------
@sio.event
async def rtc_join(sid, data):
    name = room_of(data)
    members = calls.setdefault(name, set())
    if sid not in members and len(members) >= MAX_CALL:
        await sio.emit("rtc_full", {}, to=sid)
        return
    others = [s for s in members if s != sid]
    members.add(sid)
    await sio.emit("rtc_peers", {"peers": others}, to=sid)


@sio.event
async def rtc_signal(sid, data):
    members = calls.get(sid_room.get(sid), set())
    target = data.get("to")
    if sid in members and target in members:  # only relay between people in the same call
        await sio.emit("rtc_signal", {"from": sid, "data": data.get("data")}, to=target)


async def leave_call(sid, name):
    members = calls.get(name)
    if members and sid in members:
        members.discard(sid)
        await sio.emit("rtc_left", {"sid": sid}, room=name)


@sio.event
async def rtc_leave(sid, data):
    await leave_call(sid, room_of(data))


@sio.event
async def disconnect(sid, *args):
    name = sid_room.pop(sid, None)
    if name:
        await leave_call(sid, name)
        r = rooms.get(name)
        if r:
            cid = r["cids"].pop(sid, None)
            if cid is not None and cid == r["host"]:
                asyncio.create_task(promote_later(name, cid))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)