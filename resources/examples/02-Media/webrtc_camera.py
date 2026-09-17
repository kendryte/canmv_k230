# WebRTC camera example for CanMV K230.
# Open the URL printed after the network is connected.

from media.vencoder import *
from media.sensor import *
from media.media import *
import _thread
import os
import select
import socket
import sys
import time
import ubinascii
import uctypes
import webrtc
from libs.Network import connect_network, get_devices, get_interface

NETWORK_TYPE = "default"  # Reuse a connected interface; or "lan", "wifi_sta", "wifi_ap".
WLAN_DEVICE = "auto"  # "auto", "usb", "sdio", or "spi"
WIFI_SSID = "Test"
WIFI_PASSWORD = "12345678"
NETWORK_TIMEOUT = 15
HTTP_PORT = 8080
ACCESS_TOKEN = ""  # Set a nonempty value to require tokenized page/API URLs.
MAX_CLIENTS = webrtc.MAX_PEERS
NEGOTIATION_TIMEOUT_MS = 30000
HTTP_REQUEST_TIMEOUT_MS = 2000
HTTP_MAX_CONNECTIONS = 8
HTTP_MAX_HEADER_BYTES = 16384
HTTP_MAX_BODY_BYTES = 16384
WIDTH = 1280
HEIGHT = 720
VIDEO_CODEC = "h264"  # "h264" or "h265"
BIT_RATE = 512  # Kbit/s
AUDIO_CODEC = webrtc.CODEC_NONE

PAGE = b"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CanMV WebRTC</title><style>
*{box-sizing:border-box}body{margin:0;background:#111;color:#eee;font:14px sans-serif;height:100vh;display:flex;flex-direction:column}
header{height:52px;flex:0 0 52px;display:flex;align-items:center;gap:12px;padding:0 14px;background:#242424;border-bottom:1px solid #383838}
header strong{margin-right:auto;white-space:nowrap}button{min-width:88px;height:34px;border:0;border-radius:5px;padding:0 14px;background:#1683ff;color:white;cursor:pointer}
button:disabled{cursor:wait;opacity:.6}#state{color:#aaa;white-space:nowrap}#state.connecting{color:#f2c75c}#state.connected{color:#67d68b}#state.failed{color:#ff7777}
.details{display:grid;grid-template-columns:repeat(8,minmax(90px,1fr));gap:1px;flex:0 0 auto;background:#383838;border-bottom:1px solid #383838}
.metric{min-width:0;padding:7px 10px;background:#1b1b1b}.metric span{display:block;margin-bottom:3px;color:#888;font-size:10px;line-height:12px;text-transform:uppercase;letter-spacing:.06em}.metric strong{display:block;overflow:hidden;color:#ddd;font-size:12px;font-weight:500;line-height:16px;white-space:nowrap;text-overflow:ellipsis}
.viewer{position:relative;flex:1;min-height:0;background:#000}
video{display:block;width:100%;height:100%;object-fit:contain}.stage{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;background:rgba(0,0,0,.72);opacity:0;visibility:hidden;transition:opacity .18s}
.stage.show{opacity:1;visibility:visible}.viewer.playing .stage{opacity:0;visibility:hidden}.spinner{width:30px;height:30px;margin-bottom:16px;border:3px solid #555;border-top-color:#2f9bff;border-radius:50%;animation:spin .8s linear infinite}
.stage.error .spinner{display:none}.stage-title{font-size:18px;line-height:24px}.stage-detail{max-width:430px;margin-top:7px;color:#aaa;line-height:20px;text-align:center}
@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:720px){.details{display:flex;overflow-x:auto}.metric{flex:0 0 104px}}@media(max-width:480px){header{gap:8px;padding:0 10px}header strong{font-size:13px}button{min-width:76px;padding:0 10px}#state{font-size:12px}}
</style></head><body><header><strong>CanMV WebRTC</strong><span id="state" aria-live="polite">Ready</span><button id="connect">Connect</button></header>
<section class="details" aria-label="Connection details"><div class="metric"><span>Offer</span><strong id="metric-offer">--</strong></div><div class="metric"><span>Negotiation</span><strong id="metric-sdp">--</strong></div><div class="metric"><span>ICE gathering</span><strong id="metric-ice">--</strong></div><div class="metric"><span>Secure link</span><strong id="metric-link">--</strong></div><div class="metric"><span>First frame</span><strong id="metric-frame">--</strong></div><div class="metric"><span>Video</span><strong id="metric-video">--</strong></div><div class="metric"><span>Receive</span><strong id="metric-receive">--</strong></div><div class="metric"><span>Network path</span><strong id="metric-path">--</strong></div></section>
<main class="viewer"><video id="video" autoplay playsinline muted></video><div id="stage" class="stage" role="status" aria-live="polite"><div class="spinner"></div><div id="stage-title" class="stage-title"></div><div id="stage-detail" class="stage-detail"></div></div></main><script>
let pc=null,attempt=0,mediaAttempt=0,streamingAttempt=0,elapsedTimer=null,retryTimer=null,statsTimer=null,startedAt=0,lastStats=null;
const accessToken=new URLSearchParams(location.search).get('token')||'';
function api(path){return accessToken?path+(path.includes('?')?'&':'?')+'token='+encodeURIComponent(accessToken):path}
const state=document.querySelector('#state'),button=document.querySelector('#connect'),video=document.querySelector('#video'),viewer=document.querySelector('.viewer'),stage=document.querySelector('#stage'),stageTitle=document.querySelector('#stage-title'),stageDetail=document.querySelector('#stage-detail');
const metricOffer=document.querySelector('#metric-offer'),metricSdp=document.querySelector('#metric-sdp'),metricIce=document.querySelector('#metric-ice'),metricLink=document.querySelector('#metric-link'),metricFrame=document.querySelector('#metric-frame'),metricVideo=document.querySelector('#metric-video'),metricReceive=document.querySelector('#metric-receive'),metricPath=document.querySelector('#metric-path');
function formatDuration(ms){return ms<1000?Math.round(ms)+' ms':(ms/1000).toFixed(2)+' s'}
function setState(text,kind){state.textContent=text;state.className=kind||''}
function resetDetails(){for(const item of [metricOffer,metricSdp,metricIce,metricLink,metricFrame,metricVideo,metricReceive,metricPath])item.textContent='--';metricReceive.removeAttribute('title');lastStats=null}
function waitCandidate(p){return new Promise(resolve=>{let timer;
const done=()=>{p.removeEventListener('icecandidate',onCandidate);p.removeEventListener('icegatheringstatechange',onState);clearTimeout(timer);resolve()};
const onCandidate=e=>{if(!e.candidate&&p.iceGatheringState==='complete')done()};
const onState=()=>{if(p.iceGatheringState==='complete')done()};
if(p.iceGatheringState==='complete'){resolve();return}
p.addEventListener('icecandidate',onCandidate);p.addEventListener('icegatheringstatechange',onState);timer=setTimeout(done,3000)})}
function clearTimers(){clearInterval(elapsedTimer);clearTimeout(retryTimer);elapsedTimer=null;retryTimer=null}
function stopStats(){clearInterval(statsTimer);statsTimer=null;lastStats=null}
async function updateStats(p,id){if(id!==attempt||p!==pc)return;try{const reports=await p.getStats();if(id!==attempt||p!==pc)return;let inbound=null,pair=null,selectedPairId=null;
reports.forEach(r=>{if(r.type==='inbound-rtp'&&!r.isRemote&&(r.kind==='video'||r.mediaType==='video'))inbound=r;if(r.type==='transport'&&r.selectedCandidatePairId)selectedPairId=r.selectedCandidatePairId});
if(selectedPairId)pair=reports.get(selectedPairId);if(!pair)reports.forEach(r=>{if(!pair&&r.type==='candidate-pair'&&r.state==='succeeded'&&r.nominated)pair=r});
if(inbound){const now=performance.now(),current={time:now,bytes:inbound.bytesReceived||0,frames:inbound.framesDecoded||0};let rate='';
if(lastStats&&now>lastStats.time){const seconds=(now-lastStats.time)/1000,kbps=(current.bytes-lastStats.bytes)*8/seconds/1000,fps=(current.frames-lastStats.frames)/seconds;rate=Math.max(0,kbps).toFixed(0)+' Kbit/s / '+Math.max(0,fps).toFixed(0)+' fps'}else if(inbound.framesPerSecond!==undefined)rate=Math.round(inbound.framesPerSecond)+' fps';
metricReceive.textContent=rate||'Receiving';metricReceive.title='Packets received: '+(inbound.packetsReceived||0)+', lost: '+(inbound.packetsLost||0);let codec=inbound.codecId?reports.get(inbound.codecId):null,codecName=codec&&codec.mimeType?codec.mimeType.replace('video/',''):'Video',size=video.videoWidth&&video.videoHeight?video.videoWidth+'x'+video.videoHeight:'';metricVideo.textContent=codecName+(size?' / '+size:'');lastStats=current}
if(pair){const local=reports.get(pair.localCandidateId),remote=reports.get(pair.remoteCandidateId),left=local&&local.candidateType?local.candidateType:'local',right=remote&&remote.candidateType?remote.candidateType:'remote',rtt=pair.currentRoundTripTime!==undefined?' / '+Math.round(pair.currentRoundTripTime*1000)+' ms':'';metricPath.textContent=left+' -> '+right+rtt}}catch(e){}}
function startStats(p,id){stopStats();updateStats(p,id);statsTimer=setInterval(()=>updateStats(p,id),1000)}
function showStep(title,detail,id){if(id!==undefined&&(id!==attempt||streamingAttempt===id||viewer.classList.contains('playing')))return;stage.className='stage show';stageTitle.textContent=title;stageDetail.textContent=detail}
function beginWait(){clearTimers();resetDetails();startedAt=performance.now();button.disabled=true;button.textContent='Connecting';setState('Connecting 0.0 s','connecting');showStep('Preparing camera','Requesting the encoded video stream from the board.');
elapsedTimer=setInterval(()=>{setState('Connecting '+((performance.now()-startedAt)/1000).toFixed(1)+' s','connecting')},250);
retryTimer=setTimeout(()=>{button.disabled=false;button.textContent='Retry';stageDetail.textContent='Still connecting. Network negotiation can take longer on a busy Wi-Fi link.'},15000)}
function connected(p,id){if(id!==attempt||p!==pc)return;streamingAttempt=id;clearTimers();setState('Connected in '+metricFrame.textContent,'connected');button.disabled=false;button.textContent='Reconnect';stage.className='stage';startStats(p,id)}
function failed(id,detail){if(id!==attempt)return;mediaAttempt=0;clearTimers();stopStats();viewer.classList.remove('playing');setState('Failed','failed');button.disabled=false;button.textContent='Retry';stage.className='stage show error';stageTitle.textContent='Connection failed';stageDetail.textContent=detail}
function releaseSession(p){if(!p||!p.sessionId)return Promise.resolve();const id=p.sessionId;p.sessionId='';return fetch(api('/disconnect?session='+encodeURIComponent(id)),{method:'POST',keepalive:true}).catch(()=>{})}
function closePeer(){stopStats();if(!pc)return Promise.resolve();const releasing=releaseSession(pc);pc.ontrack=null;pc.oniceconnectionstatechange=null;pc.onconnectionstatechange=null;pc.close();pc=null;return releasing}
window.addEventListener('pagehide',()=>{if(pc&&pc.sessionId)navigator.sendBeacon(api('/disconnect?session='+encodeURIComponent(pc.sessionId)),'')});
video.addEventListener('playing',()=>{const id=mediaAttempt,p=pc;if(!p||!video.srcObject||id!==attempt)return;viewer.classList.add('playing');if(metricFrame.textContent==='--')metricFrame.textContent=formatDuration(performance.now()-startedAt);connected(p,id)});
button.onclick=async()=>{const id=++attempt;streamingAttempt=0;mediaAttempt=0;const releasing=closePeer();video.srcObject=null;viewer.classList.remove('playing');beginWait();const peer=new RTCPeerConnection({iceServers:[]});pc=peer;
peer.ontrack=e=>{if(id!==attempt||peer!==pc)return;let stream=e.streams&&e.streams.length?e.streams[0]:(video.srcObject||new MediaStream());if(stream.getTracks().indexOf(e.track)<0)stream.addTrack(e.track);mediaAttempt=id;video.srcObject=stream;showStep('Starting video','The video track is ready. Waiting for the first frame to play.',id)};
peer.oniceconnectionstatechange=()=>{if(id!==attempt||peer!==pc)return;const s=peer.iceConnectionState;if(streamingAttempt===id&&(s==='connected'||s==='completed')){setState('Connected in '+metricFrame.textContent,'connected');return}if(streamingAttempt===id&&s==='checking')return;
if(s==='checking')showStep('Connecting secure stream','Checking the local network path to the camera.',id);
else if(s==='connected'||s==='completed')showStep('Connecting secure stream','The ICE path is ready. Waiting for the secure connection.',id);
else if(s==='disconnected'){setState('Reconnecting','connecting');showStep('Reconnecting','The network path was interrupted. Waiting for it to recover.',id)}
else if(s==='failed')failed(id,'The browser could not reach the camera. Check the network and try again.')};
peer.onconnectionstatechange=()=>{if(id!==attempt||peer!==pc)return;const s=peer.connectionState;if(s==='connected'){if(metricLink.textContent==='--')metricLink.textContent=formatDuration(performance.now()-startedAt);if(streamingAttempt!==id)showStep('Starting video','The secure link is ready. Waiting for the first encoded frame.',id)}else if(s==='failed')failed(id,'The secure connection failed. Try H.264 if this browser does not support H.265.')};
try{await releasing;if(id!==attempt||peer!==pc)return;showStep('Preparing camera','Requesting a WebRTC offer from the board.',id);let phase=performance.now(),response=await fetch(api('/offer'));if(!response.ok)throw new Error();peer.sessionId=response.headers.get('X-WebRTC-Session');if(!peer.sessionId)throw new Error();if(id!==attempt||peer!==pc){releaseSession(peer);return}let offer=await response.text();if(id!==attempt||peer!==pc){releaseSession(peer);return}metricOffer.textContent=formatDuration(performance.now()-phase);
showStep('Negotiating video','Selecting a compatible video codec.',id);phase=performance.now();await peer.setRemoteDescription({type:'offer',sdp:offer});if(id!==attempt||peer!==pc)return;let answer=await peer.createAnswer();if(id!==attempt||peer!==pc)return;metricSdp.textContent=formatDuration(performance.now()-phase);
phase=performance.now();let candidate=waitCandidate(peer);showStep('Finding network path','Gathering the browser network address.',id);await peer.setLocalDescription(answer);if(id!==attempt||peer!==pc)return;await candidate;if(id!==attempt||peer!==pc)return;metricIce.textContent=formatDuration(performance.now()-phase);
showStep('Connecting secure stream','Sending the browser response to the camera.',id);response=await fetch(api('/answer?session='+encodeURIComponent(peer.sessionId)),{method:'POST',body:peer.localDescription.sdp});if(id!==attempt||peer!==pc)return;if(!response.ok)throw new Error();
showStep('Starting video','Connection details are ready. Waiting for the first encoded frame.',id)}catch(e){releaseSession(peer);if(id===attempt&&peer===pc&&streamingAttempt!==id)failed(id,'Unable to complete negotiation. Try H.264 if this browser does not support H.265.')}};</script></body></html>"""


def send_all(sock, data):
    offset = 0
    while offset < len(data):
        sent = sock.send(data[offset:])
        if sent <= 0:
            raise OSError("socket send failed")
        offset += sent


def send_response(client, status, content_type, body, session_id=None):
    session_header = "X-WebRTC-Session: %s\r\n" % session_id if session_id else ""
    header = ("HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
              "Cache-Control: no-store, no-cache, must-revalidate\r\nPragma: no-cache\r\nExpires: 0\r\n"
              "X-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\n"
              "Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; "
              "style-src 'self' 'unsafe-inline'; media-src 'self' blob:; connect-src 'self'; "
              "frame-ancestors 'none'\r\n%sConnection: close\r\n\r\n" %
              (status, content_type, len(body), session_header)).encode()
    send_all(client, header)
    send_all(client, body)


def parse_request(data):
    split = data.find(b"\r\n\r\n")
    if split < 0:
        return False if len(data) >= HTTP_MAX_HEADER_BYTES else None
    try:
        header = data[:split].decode()
    except UnicodeError:
        return False
    body = data[split + 4:]
    lines = header.split("\r\n")
    request_line = lines[0].split(" ", 2)
    if len(request_line) != 3:
        return False
    method, path, _ = request_line
    content_length = 0
    for line in lines[1:]:
        if line.lower().startswith("content-length:"):
            try:
                content_length = int(line.split(":", 1)[1].strip())
            except ValueError:
                return False
            break
    if content_length < 0 or content_length > HTTP_MAX_BODY_BYTES:
        return False
    if len(body) < content_length:
        return None
    return method, path, body[:content_length]


def replace_mdns_candidates(sdp, client_ip):
    lines = sdp.split("\r\n")
    for index in range(len(lines)):
        if not lines[index].startswith("a=candidate:"):
            continue
        fields = lines[index].split(" ")
        if len(fields) > 4 and fields[4].endswith(".local"):
            fields[4] = client_ip
            lines[index] = " ".join(fields)
    return "\r\n".join(lines)


def random_hex(byte_count=16):
    return ubinascii.hexlify(webrtc.random_bytes(byte_count)).decode()


def parse_request_target(path):
    route, _, query = path.partition("?")
    params = {}
    for item in query.split("&"):
        if not item:
            continue
        key, separator, value = item.partition("=")
        if separator and key not in params:
            params[key] = value
    return route, params


def local_interfaces():
    devices = get_devices()
    interfaces = []
    for kind in ("lan", "wifi_sta", "wifi_ap"):
        try:
            nic = get_interface(kind, wlan_device=WLAN_DEVICE)
            name = nic.netdev_name()
            if name not in devices:
                continue
            config = nic.ifconfig()
            if config and config[0] not in (None, "", "0.0.0.0"):
                if not any(ip == config[0] for _, ip in interfaces):
                    interfaces.append((name, config[0]))
        except (OSError, RuntimeError):
            continue
    return interfaces


class SignalingServer:
    def __init__(self, video_codec):
        self.video_codec = video_codec
        self.sessions = {}
        self.access_token = ACCESS_TOKEN
        self.lock = _thread.allocate_lock()
        self.done = _thread.allocate_lock()
        self.stopping = False
        self.started = False
        self.listeners = {}
        self.clients = {}
        self.poll = select.poll()

    def start(self):
        try:
            for name, ip in local_interfaces():
                listener = socket.socket()
                try:
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    listener.bind((ip, HTTP_PORT))
                    listener.listen(MAX_CLIENTS)
                    listener.setblocking(False)
                    self.poll.register(listener, select.POLLIN)
                except OSError as error:
                    listener.close()
                    print("HTTP bind failed for %s (%s): %s" % (name, ip, error))
                    continue
                self.listeners[listener] = ip
                if self.access_token:
                    print("WebRTC camera: http://%s:%d/?token=%s (%s)" %
                          (ip, HTTP_PORT, self.access_token, name))
                else:
                    print("WebRTC camera: http://%s:%d/ (%s)" %
                          (ip, HTTP_PORT, name))
            if not self.listeners:
                raise RuntimeError("No local HTTP listener available")
            self.done.acquire()
            try:
                _thread.start_new_thread(self.serve, ())
            except BaseException:
                self.done.release()
                raise
            self.started = True
        except BaseException:
            self.close()
            raise

    def drop(self, session_id):
        # Caller owns self.lock; native close waits for that peer's worker.
        self.sessions.pop(session_id)["peer"].close()

    def close_client(self, client):
        try:
            self.poll.unregister(client)
        except OSError:
            pass
        self.clients.pop(client, None)
        client.close()

    def accept_client(self, listener):
        try:
            client, address = listener.accept()
        except OSError:
            return
        if len(self.clients) >= HTTP_MAX_CONNECTIONS:
            client.close()
            return
        client.setblocking(False)
        self.clients[client] = {
            "address": address[0],
            "local": self.listeners[listener],
            "data": b"",
            "deadline": time.ticks_add(time.ticks_ms(), HTTP_REQUEST_TIMEOUT_MS),
        }
        events = select.POLLIN
        if hasattr(select, "POLLERR"):
            events |= select.POLLERR
        if hasattr(select, "POLLHUP"):
            events |= select.POLLHUP
        self.poll.register(client, events)

    def service_client(self, client):
        connection = self.clients.get(client)
        if connection is None:
            return
        try:
            chunk = client.recv(2048)
        except OSError:
            return
        if not chunk:
            self.close_client(client)
            return
        connection["data"] += chunk
        connection["deadline"] = time.ticks_add(time.ticks_ms(), HTTP_REQUEST_TIMEOUT_MS)
        request = parse_request(connection["data"])
        if request is None:
            return
        try:
            client.settimeout(2)
            if request is False:
                send_response(client, "400 Bad Request", "text/plain", b"Bad Request")
            else:
                response = self.handle(*request, connection["address"], connection["local"])
                send_response(client, *response)
        except OSError as error:
            if not error.args or error.args[0] not in (32, 104):
                sys.print_exception(error)
        except BaseException as error:
            sys.print_exception(error)
            try:
                send_response(client, "500 Internal Server Error", "text/plain", b"Signaling failed")
            except OSError:
                pass
        finally:
            self.close_client(client)

    def reap(self):
        now = time.ticks_ms()
        for session_id, session in list(self.sessions.items()):
            state = session["peer"].state()
            if state in (webrtc.STATE_CLOSED, webrtc.STATE_FAILED, webrtc.STATE_DISCONNECTED):
                self.drop(session_id)
            elif state != webrtc.STATE_COMPLETED and time.ticks_diff(now, session["activity"]) > NEGOTIATION_TIMEOUT_MS:
                self.drop(session_id)

    def handle(self, method, path, body, client_ip, local_ip):
        route, params = parse_request_target(path)
        if self.access_token and params.get("token") != self.access_token:
            return "403 Forbidden", "text/plain", b"Forbidden", None
        if method == "OPTIONS":
            return "204 No Content", "text/plain", b"", None
        if method == "GET" and route == "/":
            return "200 OK", "text/html", PAGE, None
        if method == "GET" and route == "/offer":
            with self.lock:
                self.reap()
                if len(self.sessions) >= MAX_CLIENTS:
                    return "503 Service Unavailable", "text/plain", b"Maximum clients reached", None
                session_id = random_hex()
                while session_id in self.sessions:
                    session_id = random_hex()

            peer = webrtc.PeerConnection(video_codec=self.video_codec,
                                         audio_codec=AUDIO_CODEC, local_ip=local_ip)
            try:
                offer = peer.create_offer().encode()
                with self.lock:
                    self.sessions[session_id] = {"peer": peer, "client": client_ip,
                        "local": local_ip, "activity": time.ticks_ms(), "ready": False}
            except BaseException:
                peer.close()
                raise
            print("Session %s: %s -> %s" % (session_id, local_ip, client_ip))
            return "200 OK", "application/sdp", offer, session_id

        with self.lock:
            self.reap()
            if method != "POST" or route not in ("/answer", "/disconnect"):
                return "404 Not Found", "text/plain", b"Not Found", None
            session_id = params.get("session")
            if not session_id or len(session_id) != 32:
                return "400 Bad Request", "text/plain", b"Missing session ID", None
            session = self.sessions.get(session_id)
            if session is None:
                return "404 Not Found", "text/plain", b"Session not found", None
            if session["client"] != client_ip or session["local"] != local_ip:
                return "403 Forbidden", "text/plain", b"Session client mismatch", None
            if route == "/disconnect":
                self.drop(session_id)
            else:
                if not body:
                    return "400 Bad Request", "text/plain", b"Missing SDP", None
                answer = replace_mdns_candidates(body.decode(), client_ip)
                session["peer"].set_remote_description(answer)
                if session["peer"].state() == webrtc.STATE_FAILED:
                    self.drop(session_id)
                    return "400 Bad Request", "text/plain", b"Invalid SDP answer", None
                session["activity"] = time.ticks_ms()
            return "200 OK", "text/plain", b"OK", None

    def serve(self):
        try:
            while not self.stopping:
                with self.lock:
                    self.reap()
                for item, event in self.poll.poll(50):
                    if self.stopping:
                        break
                    if item in self.listeners:
                        if event & select.POLLIN:
                            self.accept_client(item)
                    elif item in self.clients:
                        if event & select.POLLIN:
                            self.service_client(item)
                        elif event:
                            self.close_client(item)
                now = time.ticks_ms()
                for client, connection in list(self.clients.items()):
                    if time.ticks_diff(now, connection["deadline"]) >= 0:
                        self.close_client(client)
        finally:
            self.stopping = True
            for client in list(self.clients):
                self.close_client(client)
            self.done.release()

    def need_keyframe(self):
        with self.lock:
            needed = False
            for session in self.sessions.values():
                if session["peer"].is_connected() and not session["ready"]:
                    session["ready"] = True
                    needed = True
            return needed

    def send_video(self, data, timestamp):
        with self.lock:
            for session in self.sessions.values():
                if session["peer"].is_connected():
                    session["peer"].send_video(data, timestamp)

    def close(self):
        self.stopping = True
        if self.started:
            self.done.acquire()
            self.done.release()
            self.started = False
        for listener in self.listeners:
            self.poll.unregister(listener)
            listener.close()
        self.listeners.clear()
        with self.lock:
            for session_id in list(self.sessions):
                self.drop(session_id)


def run():
    width = ALIGN_UP(WIDTH, 16)
    sensor = None
    encoder = None
    link = None
    server = None

    netif, ip = connect_network(
        NETWORK_TYPE,
        ssid=WIFI_SSID,
        password=WIFI_PASSWORD,
        wlan_device=WLAN_DEVICE,
        timeout=NETWORK_TIMEOUT,
        set_default=False,
    )
    try:
        if VIDEO_CODEC == "h265":
            peer_video_codec = webrtc.CODEC_H265
            payload_type = Encoder.PAYLOAD_TYPE_H265
            profile = Encoder.H265_PROFILE_MAIN
        elif VIDEO_CODEC == "h264":
            peer_video_codec = webrtc.CODEC_H264
            payload_type = Encoder.PAYLOAD_TYPE_H264
            profile = Encoder.H264_PROFILE_MAIN
        else:
            raise ValueError("VIDEO_CODEC must be 'h265' or 'h264'")

        server = SignalingServer(peer_video_codec)
        sensor = Sensor()
        sensor.reset()
        sensor.set_framesize(width=width, height=HEIGHT, alignment=12)
        sensor.set_pixformat(Sensor.YUV420SP)

        encoder = Encoder()
        encoder.SetOutBufs(8, width, HEIGHT)
        attributes = ChnAttrStr(payload_type, profile, width, HEIGHT,
                                bit_rate=BIT_RATE)
        encoder.Create(attributes)
        link = MediaManager.link(sensor.bind_info()["src"],
                                 (VIDEO_ENCODE_MOD_ID, VENC_DEV_ID, encoder.chn))
        encoder.Start()
        sensor.run()
        server.start()

        stream = StreamData()
        parameter_sets = None
        while True:
            os.exitpoint()
            if server.stopping:
                raise RuntimeError("Signaling server stopped")
            if server.need_keyframe():
                # Do not wait for the next periodic keyframe after ICE/DTLS completes.
                encoder.RequestIDR()
            if encoder.GetStream(stream, timeout=100) != 0:
                continue
            try:
                for index in range(stream.pack_cnt):
                    data = uctypes.bytearray_at(stream.data[index], stream.data_size[index])
                    stream_type = stream.stream_type[index]
                    timestamp = stream.pts[index]
                    if stream_type == encoder.STREAM_TYPE_HEADER:
                        parameter_sets = bytes(data)
                    else:
                        if stream_type == encoder.STREAM_TYPE_I and parameter_sets:
                            server.send_video(parameter_sets, timestamp)
                        server.send_video(data, timestamp)
            finally:
                encoder.ReleaseStream(stream)
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.close()
        if sensor is not None:
            sensor.stop()
        if link is not None:
            link.destroy()
        if encoder is not None and encoder.chn >= 0:
            encoder.Stop()
            encoder.Destroy()


if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    run()
