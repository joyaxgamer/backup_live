import os
import time
import subprocess

def start_direct_challenge_live():
    # आपकी वीडियो फ़ाइल और वर्चुअल वॉइस चैट ऑडियो इनपुट
    video_file = "lovee_video.mp4"
    
    # आपका लाइव यूट्यूब स्ट्रीमिंग यूआरएल और सीक्रेट चाबी
    STREAM_URL = "rtmp://a.rtmp.youtube.com/live2"
    STREAM_KEY = "ay8r-px8b-ammh-qq0j-24qd"
    
    rtmp_url = f"{STREAM_URL}/{STREAM_KEY}"
    command = [
        "ffmpeg", "-re",
        "-stream_loop", "-1", "-i", video_file,
        "-f", "pulse", "-i", "VirtualSpeaker.monitor",
        "-vf", "scale=1280:720,format=yuv420p",
        "-c:v", "libx264", "-preset", "ultrafast", "-b:v", "1500k",
        "-maxrate", "1500k", "-bufsize", "3000k", "-pix_fmt", "yuv420p",
        "-g", "48", "-c:a", "aac", "-b:a", "96k", "-ar", "44100",
        "-map", "0:v:0", "-map", "1:a:0",
        "-f", "flv", rtmp_url
    ]
    
    print("⚡ वॉइस लाइव चैट बाईपास एक्टिव: लाइव ब्रॉडकास्ट शुरू हो रहा है...")
    
    while True:
        try:
            subprocess.run(command, check=True)
        except Exception as e:
            print(f"कनेक्शन रीसेट हुआ: {e}। 3 सेकंड में दोबारा रीस्टार्ट...")
            time.sleep(3)

if __name__ == "__main__":
    start_direct_challenge_live()
