"""Send a 16:9 long video + thumbnail + upload kit to the owner's Telegram.
Usage: python3 tg_send_long.py spec.json video.mp4 thumb.jpg   (env TG_TOKEN, TG_CHAT). Prints JSON {ok, ...}."""
import json, os, sys, uuid, urllib.request, urllib.parse, time
API = f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/"; CHAT = os.environ["TG_CHAT"]
def post(method, fields, files=None):
    if files:
        b = uuid.uuid4().hex; body = b""
        for k, v in fields.items(): body += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        for k, (fn, data, ct) in files.items():
            body += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\nContent-Type: {ct}\r\n\r\n".encode() + data + b"\r\n"
        body += f"--{b}--\r\n".encode()
        req = urllib.request.Request(API + method, data=body, headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    else: req = urllib.request.Request(API + method, data=urllib.parse.urlencode(fields).encode())
    err = ""
    for a in range(2):
        try: return json.loads(urllib.request.urlopen(req, timeout=300).read())
        except Exception as e: err = str(e); time.sleep(3)
    return {"ok": False, "description": err}
spec = json.load(open(sys.argv[1])); y = spec["youtube"]; mp4, thumb = sys.argv[2], sys.argv[3]
r1 = post("sendVideo", {"chat_id": CHAT, "caption": f"🎬 New SurgerySaathi VIDEO (16:9, normal upload)\n{y['title']}", "supports_streaming": "true", "width": "1920", "height": "1080"},
          {"video": (os.path.basename(mp4), open(mp4, "rb").read(), "video/mp4")})
r2 = post("sendDocument", {"chat_id": CHAT, "caption": "🖼 Thumbnail (1280x720) — Studio → Details → Thumbnail → Upload"},
          {"document": (os.path.basename(thumb), open(thumb, "rb").read(), "image/jpeg")})
txt = (f"📋 Upload kit — long video (YouTube Studio → Create → Upload video, NOT as a Short)\n\nTITLE:\n{y['title']}\n\nDESCRIPTION:\n{y['description']}\n\n"
       f"TAGS (Show more → Tags):\n{', '.join(y['tags'])}\n\nSettings: Not made for kids · Altered/synthetic content: Yes (AI voice) · Category: Education · "
       f"Playlist: {spec.get('playlist', 'OT Kisse')} · End screen: add 'Subscribe' + 1 video · Chapters are already in the description.")
r3 = post("sendMessage", {"chat_id": CHAT, "text": txt[:4000], "disable_web_page_preview": "true"})
print(json.dumps(dict(ok=all(r.get("ok") for r in (r1, r2, r3)), error=" ".join(r.get("description", "") for r in (r1, r2, r3) if not r.get("ok"))), ensure_ascii=False))
