import os
import time
import threading
import subprocess
from flask import Flask, request, render_template_string, jsonify
from pyngrok import conf, installer

app = Flask(__name__)

PIPE_PATH = "/tmp/live_audio.pcm"
TEXT_PATH = "/tmp/active_speaker.txt"

if not os.path.exists(PIPE_PATH):
    os.mkfifo(PIPE_PATH)

with open(TEXT_PATH, "w") as f:
    f.write("Talkto-urs Live Voice")

ADMIN_PASS = "7860"
room_locked = False
mute_all_members = False
muted_users = set()
active_users = {}

MEMBER_HTML = """
<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Talkto-urs Voice</title></head>
<body style="background:#111;color:#fff;text-align:center;font-family:sans-serif;padding-top:40px;">
  <h2>Talkto-urs Live Voice Room</h2>
  <div id="joinBox">
    <input id="uname" placeholder="Apna Naam Likhein..." style="padding:12px;font-size:16px;border-radius:8px;border:none;width:70%;max-width:280px;"><br><br>
    <button onclick="startMic()" style="padding:15px 30px;font-size:18px;background:#28a745;color:#fff;border:none;border-radius:10px;">Join and Mic On</button>
  </div>
  <p id="status" style="margin-top:20px;font-size:16px;color:#0f0;"></p>
  <script>
    async function startMic() {
      const name = document.getElementById('uname').value.trim();
      if (!name) { alert("Pehle apna naam likhein!"); return; }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioCtx({ sampleRate: 16000 });
        await ctx.resume();
        const src = ctx.createMediaStreamSource(stream);
        const proc = ctx.createScriptProcessor(2048, 1, 1);
        src.connect(proc);
        proc.connect(ctx.destination);
        let chunks = [];
        proc.onaudioprocess = (e) => {
          const input = e.inputBuffer.getChannelData(0);
          const pcm = new Int16Array(input.length);
          for (let i = 0; i < input.length; i++) {
            let s = Math.max(-1, Math.min(1, input[i]));
            pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          }
          chunks.push(pcm);
        };
        setInterval(async () => {
          if (chunks.length === 0) return;
          const total = chunks.reduce((acc, c) => acc + c.length, 0);
          const merged = new Int16Array(total);
          let offset = 0;
          for (const c of chunks) { merged.set(c, offset); offset += c.length; }
          chunks = [];
          try {
            const res = await fetch('/audio?user=' + encodeURIComponent(name), {
              method: 'POST',
              headers: { 'ngrok-skip-browser-warning': 'true' },
              body: merged.buffer
            });
            document.getElementById('status').innerText = await res.text();
          } catch (e) {}
        }, 150);
        document.getElementById('joinBox').style.display = "none";
        document.getElementById('status').innerText = "Connected! Aapka naam live screen par dikh raha hai.";
      } catch (err) {
        document.getElementById('status').innerText = "Error: " + err.message;
      }
    }
  </script>
</body>
</html>
"""

ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Admin Control</title></head>
<body style="background:#181818;color:#fff;font-family:sans-serif;padding:20px;text-align:center;">
  <h2>Talkto-urs Admin Panel</h2>
  <div id="loginBox">
    <input id="pass" type="password" placeholder="Admin Password (7860)" style="padding:10px;font-size:16px;">
    <button onclick="login()" style="padding:10px 20px;font-size:16px;background:#007bff;color:#fff;border:none;">Login</button>
  </div>
  <div id="panel" style="display:none;">
    <button onclick="cmd('toggle_lock')" id="lockBtn" style="padding:12px 20px;margin:5px;font-size:16px;border-radius:8px;border:none;">Room Lock</button>
    <button onclick="cmd('toggle_mute_all')" id="muteAllBtn" style="padding:12px 20px;margin:5px;font-size:16px;border-radius:8px;border:none;">Mute All</button>
    <h3>Active Members:</h3>
    <div id="userList"></div>
  </div>
  <script>
    let pwd = "";
    function login() { pwd = document.getElementById('pass').value; refresh(); }
    async function cmd(action, target="") {
      await fetch(`/admin_api?pass=${pwd}&action=${action}&target=${encodeURIComponent(target)}`);
      refresh();
    }
    async function refresh() {
      const res = await fetch(`/admin_api?pass=${pwd}&action=status`);
      if (res.status !== 200) { alert("Galat Password!"); return; }
      const data = await res.json();
      document.getElementById('loginBox').style.display = "none";
      document.getElementById('panel').style.display = "block";
      document.getElementById('lockBtn').innerText = data.locked ? "Unlock Room" : "Lock Room";
      document.getElementById('lockBtn').style.background = data.locked ? "#dc3545" : "#28a745";
      document.getElementById('muteAllBtn').innerText = data.mute_all ? "Unmute All" : "Mute All";
      document.getElementById('muteAllBtn').style.background = data.mute_all ? "#dc3545" : "#ffc107";
      let html = "";
      for (const u of data.users) {
        const isMuted = data.muted.includes(u);
        html += `<div style="background:#252525;padding:10px;margin:8px auto;max-width:350px;border-radius:8px;display:flex;justify-content:space-between;align-items:center;">
          <span><b>${u}</b></span>
          <button onclick="cmd('toggle_user', '${u}')" style="padding:6px 12px;background:${isMuted ? '#dc3545' : '#28a745'};color:#fff;border:none;border-radius:5px;">
            ${isMuted ? 'Unmute' : 'Mute'}
          </button>
        </div>`;
      }
      document.getElementById('userList').innerHTML = html || "<p>Abhi koi member nahi hai</p>";
    }
    setInterval(() => { if (pwd) refresh(); }, 3000);
  </script>
</body>
</html>
"""

latest_audio = b""
audio_lock = threading.Lock()

def update_overlay_loop():
    last_text = ""
    while True:
        now = time.time()
        speaking = [u for u, t in active_users.items() if (now - t < 3) and (u not in muted_users) and not mute_all_members]
        if speaking:
            clean_names = ["".join(c for c in name if c.isalnum() or c in " _-") for name in speaking]
            new_text = "Live On Mic: " + ", ".join(clean_names)
        else:
            new_text = "Join Voice Chat - Link in Chat"
        if new_text != last_text:
            try:
                tmp_file = TEXT_PATH + ".tmp"
                with open(tmp_file, "w") as f:
                    f.write(new_text)
                os.replace(tmp_file, TEXT_PATH)
                last_text = new_text
            except Exception:
                pass
        time.sleep(1)

@app.route('/')
def index():
    return render_template_string(MEMBER_HTML)

@app.route('/admin')
def admin_page():
    return render_template_string(ADMIN_HTML)

@app.route('/admin_api')
def admin_api():
    global room_locked, mute_all_members
    if request.args.get('pass') != ADMIN_PASS:
        return "Unauthorized", 403
    action = request.args.get('action')
    target = request.args.get('target', '')
    if action == 'toggle_lock':
        room_locked = not room_locked
    elif action == 'toggle_mute_all':
        mute_all_members = not mute_all_members
    elif action == 'toggle_user' and target:
        if target in muted_users:
            muted_users.remove(target)
        else:
            muted_users.add(target)
    now = time.time()
    online = [u for u, t in active_users.items() if now - t < 5]
    return jsonify({"locked": room_locked, "mute_all": mute_all_members, "users": online, "muted": list(muted_users)})

@app.route('/audio', methods=['POST'])
def receive_audio():
    global latest_audio
    user = request.args.get('user', 'Guest')
    now = time.time()
    if room_locked and (user not in active_users or now - active_users[user] > 10):
        return "Room abhi lock hai.", 200
    active_users[user] = now
    if mute_all_members or user in muted_users:
        return "Admin ne aapko Mute kar rakha hai.", 200
    data = request.get_data()
    if data:
        with audio_lock:
            latest_audio += data
    return "Aapki aawaz aur naam YouTube Live par chal raha hai!", 200

def pipe_feeder():
    global latest_audio
    silence = b"\x00" * 4800
    with open(PIPE_PATH, "wb", buffering=0) as f:
        while True:
            time.sleep(0.15)
            with audio_lock:
                if latest_audio:
                    chunk = latest_audio
                    latest_audio = b""
                else:
                    chunk = silence
            try:
                f.write(chunk)
            except Exception:
                pass

def start_ngrok_permanent():
    NGROK_TOKEN = "3M5KV9BBuu4ZkRy1NS5e6btY8L8_7z1YQbBW31GLmL8zmarCj"
    STATIC_DOMAIN = "outboard-aftermath-dice.ngrok-free.dev"
    ngrok_path = conf.get_default().ngrok_path
    if not os.path.exists(ngrok_path):
        installer.install_ngrok(ngrok_path)
    subprocess.run([ngrok_path, "config", "add-authtoken", NGROK_TOKEN])
    while True:
        proc = subprocess.Popen([ngrok_path, "http", f"--url={STATIC_DOMAIN}", "5000"])
        proc.wait()
        time.sleep(3)

def start_stream():
    threading.Thread(target=pipe_feeder, daemon=True).start()
    threading.Thread(target=start_ngrok_permanent, daemon=True).start()
    threading.Thread(target=update_overlay_loop, daemon=True).start()
    video_file = "lovee_video.mp4"
    rtmp_url = "".join(["rtmp:", "//", "a.rtmp.", "youtube", ".com/live2/", "rey7-p2b6-wa5t-87xv-2cs1"])
    vf_filter = f"scale=1280:720,format=yuv420p,drawtext=textfile={TEXT_PATH}:reload=1:fontcolor=white:fontsize=30:box=1:boxcolor=black@0.7:boxborderw=12:x=(w-text_w)/2:y=h-70"
    command = [
        "ffmpeg", "-re", "-stream_loop", "-1", "-i", video_file,
        "-f", "s16le", "-ar", "16000", "-ac", "1", "-i", PIPE_PATH,
        "-vf", vf_filter, "-c:v", "libx264", "-preset", "ultrafast", "-b:v", "1500k",
        "-maxrate", "1500k", "-bufsize", "1000k", "-pix_fmt", "yuv420p",
        "-g", "48", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-map", "0:v:0", "-map", "1:a:0", "-f", "flv", rtmp_url
    ]
    while True:
        subprocess.run(command)
        time.sleep(3)

if __name__ == "__main__":
    threading.Thread(target=start_stream, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, threaded=True)
