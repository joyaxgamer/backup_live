import os
import time
import subprocess

def start_direct_challenge_live():
    video_file = "lovee_video.mp4"
    STREAM_URL = "rtmp://a.rtmp.youtube.com/live2"
    STREAM_KEY = os.environ.get("YOUTUBE_KEY") or "ay8r-px8b-ammh-qq0j-24qd"
    rtmp_url = f"{STREAM_URL}/{STREAM_KEY}"

    # 1. PulseAudio को साफ करके VirtualSpeaker बनाना
    subprocess.run(["pulseaudio", "-k"], stderr=subprocess.DEVNULL)
    time.sleep(1)
    subprocess.run(["pulseaudio", "-D", "--exit-idle-time=-1"])
    subprocess.run([
        "pactl", "load-module", "module-null-sink",
        "sink_name=VirtualSpeaker",
        "sink_properties=device.description=VirtualSpeaker"
    ])
    subprocess.run(["pactl", "set-default-sink", "VirtualSpeaker"])

    env = os.environ.copy()
    env["PULSE_SINK"] = "VirtualSpeaker"
    env["PULSE_SOURCE"] = "VirtualSpeaker.monitor"
    env["DISPLAY"] = ":99"

    # 2. Virtual Screen और Chrome चालू करना
    subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1280x720x24"], env=env)
    time.sleep(3)

    vdo_url = "https://vdo.ninja"
    subprocess.Popen([
        "google-chrome",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--user-data-dir=/tmp/chrome_vdo",
        "--autoplay-policy=no-user-gesture-required",
        "--use-fake-device-for-media-stream",
        "--alsa-output-device=pulse",
        "--window-size=1280,720",
        vdo_url
    ], env=env)

    time.sleep(12)
    # अनम्यूट करने के लिए क्लिक
    subprocess.run(["xdotool", "mousemove", "640", "360", "click", "1"], env=env)
    time.sleep(2)
    subprocess.run(["xdotool", "key", "m"], env=env)
    time.sleep(2)

    # 3. FFmpeg से Video + Voice YouTube पर भेजना
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

    print("⚡ Live Stream + Voice Active!")
    while True:
        try:
            subprocess.run(command, env=env, check=True)
        except Exception as e:
            print(f"Restarting stream: {e}")
            time.sleep(3)

if __name__ == "__main__":
    start_direct_challenge_live()
