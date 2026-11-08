"""Send a finished SurgerySaathi video + upload text to the user's Telegram.
Usage: python3 tg_send.py spec.json video.mp4   (env TG_TOKEN, TG_CHAT)
Prints JSON {ok, video, text, error}."""
import json, os, sys, uuid, urllib.request, urllib.parse, time
TOKEN = os.environ["TG_TOKEN"]; CHAT = os.environ["TG_CHAT"]
API = f"https://api.telegram.org/bot{TOKEN}/"
def post(method, fields, files=None):
    if files:
        b = uuid.uuid4().hex; body = b""
        for k, v in fields.items():
            body += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        for k, (fn, data, ct) in files.items():
            body += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\nContent-Type: {ct}\r\n\r\n".encode() + data + b"\r\n"
        body += f"--{b}--\r\n".encode()
        req = urllib.request.Request(API + method, data=body, headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    else:
        req = urllib.request.Request(API + method, data=urllib.parse.urlencode(fields).encode())
    for a in range(2):
        try: return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except Exception as e:
            err = str(e); time.sleep(3)
    return {"ok": False, "description": err}
spec = json.load(open(sys.argv[1])); y = spec["youtube"]
fn = os.path.basename(sys.argv[2])
r1 = post("sendVideo", {"chat_id": CHAT, "caption": f"🎬 New SurgerySaathi Short #{spec['num']}\n{y['title']}", "supports_streaming": "true", "width": "1080", "height": "1920"},
          {"video": (fn, open(sys.argv[2], "rb").read(), "video/mp4")})
txt = f"📋 Upload kit #{spec['num']} (YouTube app → + → Short → pick this video)\n\nTITLE:\n{y['title']}\n\nDESCRIPTION:\n{y['description']}\n\nTAGS (Studio → Show more → Tags):\n{', '.join(y['tags'])}\n\nSettings: Not made for kids · Altered/synthetic content: Yes (AI voice) · Playlist: OT Kisse"
r2 = post("sendMessage", {"chat_id": CHAT, "text": txt[:4000], "disable_web_page_preview": "true"})
print(json.dumps(dict(ok=bool(r1.get("ok") and r2.get("ok")), video=r1.get("ok"), text=r2.get("ok"), error=(r1.get("description") or "") + " " + (r2.get("description") or "")), ensure_ascii=False))
