import os
import re
import time
import threading
import subprocess
from flask import Flask, render_template_string
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Talkto-urs Live Voice</title></head>
<body style="background:#111;color:#fff;text-align:center;font-family:sans-serif;padding-top:50px;">
  <h2>Talkto-urs Live Voice Room</h2>
  <button id="btn" onclick="startMic()" style="padding:15px 30px;font-size:18px;background:#28a745;color:#fff;border:none;border-radius:8px;">🎤 Mic On Karein</button>
  <p id="status">Mic band hai</p>
  <script src="https://socket.io"></script>
  <script>
    const socket = io();
    async function startMic() {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext({ sampleRate: 16000 });
      const src = ctx.createMediaStreamSource(stream);
      const proc = ctx.createScriptProcessor(4096, 1, 1);
      src.connect(proc);
      proc.connect(ctx.destination);
      proc.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0);
        const pcm = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) pcm[i] = Math.max(-1, Math.min(1, input[i])) * 0x7FFF;
        socket.emit('audio', pcm.buffer);
      };
      document.getElementById('status').innerText = "✅ Aapki aawaz YouTube Live par ja rahi hai!";
      document.getElementById('btn').style.display = "none";
    }
  </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

pacat_proc = None

@socketio.on('audio')
def handle_audio(data):
    global pacat_proc
    if pacat_proc and pacat_proc.stdin:
        try:
            pacat_proc.stdin.write(data)
            pacat_proc.stdin.flush()
        except Exception:
            pass

def start_tunnel():
    try:
        cf = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", "http://localhost:5000"],
            stderr=subprocess.PIPE,
            text=True
        )
        for line in cf.stderr:
            match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
            if match:
                print("\n" + "="*50, flush=True)
                print("🎤 AAPKA VOICE LINK TAIYAR HAI:", flush=True)
                print(match.group(0), flush=True)
                print("="*50 + "\n", flush=True)
                break
    except Exception as e:
        print(f"Tunnel error: {e}", flush=True)

def start_stream():
    global pacat_proc
    subprocess.run(["pulseaudio", "-k"], stderr=subprocess.DEVNULL)
    time.sleep(1)
    subprocess.run(["pulseaudio", "-D", "--exit-idle-time=-1"])
    subprocess.run(["pactl", "load-module", "module-null-sink", "sink_name=VirtualSpeaker"])
    subprocess.run(["pactl", "set-default-sink", "VirtualSpeaker"])

    pacat_proc = subprocess.Popen(
        ["pacat", "--playback", "--device=VirtualSpeaker", "--format=s16le", "--rate=16000", "--channels=1"],
        stdin=subprocess.PIPE
    )

    threading.Thread(target=start_tunnel, daemon=True).start()

    video_file = "lovee_video.mp4"
    STREAM_KEY = os.environ.get("YOUTUBE_KEY") or "ay8r-px8b-ammh-qq0j-24qd"
    rtmp_url = f"rtmp://a.rtmp.youtube.com/live2{STREAM_KEY}"

    command = [
        "ffmpeg", "-re",
        "-stream_loop", "-1", "-i", video_file,
        "-f", "pulse", "-i", "VirtualSpeaker.monitor",
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
    socketio.run(app, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)
