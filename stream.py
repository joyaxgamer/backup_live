import os
import time
import threading
import subprocess
from flask import Flask, request, render_template_string
from pyngrok import conf, installer

app = Flask(__name__)

PIPE_PATH = "/tmp/live_audio.pcm"
if not os.path.exists(PIPE_PATH):
    os.mkfifo(PIPE_PATH)

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Talkto-urs Live Voice</title></head>
<body style="background:#111;color:#fff;text-align:center;font-family:sans-serif;padding-top:50px;">
  <h2>Talkto-urs Live Voice Room</h2>
  <button id="btn" onclick="startMic()" style="padding:18px 35px;font-size:20px;background:#28a745;color:#fff;border:none;border-radius:10px;">🎤 Mic On Karein</button>
  <p id="status" style="margin-top:20px;font-size:16px;">Mic band hai</p>
  <script>
    async function startMic() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioCtx({ sampleRate: 16000 });
        await ctx.resume();
        const src = ctx.createMediaStreamSource(stream);
        const proc = ctx.createScriptProcessor(4096, 1, 1);
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

        setInterval(() => {
          if (chunks.length === 0) return;
          const total = chunks.reduce((acc, c) => acc + c.length, 0);
          const merged = new Int16Array(total);
          let offset = 0;
          for (const c of chunks) { merged.set(c, offset); offset += c.length; }
          chunks = [];
          fetch('/audio', {
            method: 'POST',
            headers: { 'ngrok-skip-browser-warning': 'true' },
            body: merged.buffer
          }).catch(() => {});
        }, 250);

        document.getElementById('status').innerText = "✅ Aapki aawaz seedha YouTube par ja rahi hai!";
        document.getElementById('btn').style.display = "none";
      } catch (err) {
        document.getElementById('status').innerText = "❌ Error: " + err.message;
      }
    }
  </script>
</body>
</html>
"""

latest_audio = b""
audio_lock = threading.Lock()

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/audio', methods=['POST'])
def receive_audio():
    global latest_audio
    data = request.get_data()
    if data:
        with audio_lock:
            latest_audio += data
    return "OK", 200

def pipe_feeder():
    global latest_audio
    silence = b"\x00" * 8000
    with open(PIPE_PATH, "wb", buffering=0) as f:
        while True:
            time.sleep(0.25)
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
        print(f"✅ STARTING PERMANENT LINK: https://{STATIC_DOMAIN}", flush=True)
        proc = subprocess.Popen([ngrok_path, "http", f"--url={STATIC_DOMAIN}", "5000"])
        proc.wait()
        print("Ngrok reconnecting in 3s...", flush=True)
        time.sleep(3)

def start_stream():
    threading.Thread(target=pipe_feeder, daemon=True).start()
    threading.Thread(target=start_ngrok_permanent, daemon=True).start()

    video_file = "lovee_video.mp4"
    rtmp_url = "".join(["rtmp:", "//", "a.rtmp.", "youtube", ".com/live2/", "ay8r-px8b-ammh-qq0j-24qd"])

    command = [
        "ffmpeg", "-re",
        "-stream_loop", "-1", "-i", video_file,
        "-f", "s16le", "-ar", "16000", "-ac", "1", "-i", PIPE_PATH,
        "-vf", "scale=1280:720,format=yuv420p",
        "-c:v", "libx264", "-preset", "ultrafast", "-b:v", "1500k",
        "-maxrate", "1500k", "-bufsize", "3000k", "-pix_fmt", "yuv420p",
        "-g", "48", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-map", "0:v:0", "-map", "1:a:0",
        "-f", "flv", rtmp_url
    ]
    while True:
        subprocess.run(command)
        time.sleep(3)

if __name__ == "__main__":
    threading.Thread(target=start_stream, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, threaded=True)
