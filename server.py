from http.server import HTTPServer, BaseHTTPRequestHandler
import json, urllib.request, urllib.error, ssl, os, time, hmac, hashlib, base64

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
KLING_ACCESS_KEY  = os.environ.get("KLING_ACCESS_KEY",  "").strip()
KLING_SECRET_KEY  = os.environ.get("KLING_SECRET_KEY",  "").strip()
IMGBB_API_KEY     = os.environ.get("IMGBB_API_KEY",     "").strip()
PORT = int(os.environ.get("PORT", 8000))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def kling_token():
    now = int(time.time())
    h = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).rstrip(b'=').decode()
    p = base64.urlsafe_b64encode(json.dumps({"iss":KLING_ACCESS_KEY,"exp":now+1800,"nbf":now-5}).encode()).rstrip(b'=').decode()
    msg = f"{h}.{p}"
    sig = base64.urlsafe_b64encode(hmac.new(KLING_SECRET_KEY.encode(), msg.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
    return f"{msg}.{sig}"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a): pass

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST,GET,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200); self.cors(); self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.serve_file(os.path.join(BASE_DIR, "index.html"), "text/html; charset=utf-8")
        elif self.path == "/health":
            self.json({"status":"ok","anthropic":bool(ANTHROPIC_API_KEY),"kling":bool(KLING_ACCESS_KEY),"imgbb":bool(IMGBB_API_KEY)})
        elif self.path.startswith("/api/video/status/"):
            self.video_status(self.path.split("/")[-1])
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)

        if self.path == "/api/upload":
            try: self.json(self.upload_img(body, self.headers))
            except Exception as e: self.json({"error": str(e)}, 500)
            return

        try: data = json.loads(body)
        except: self.json({"error":"bad json"}, 400); return

        if self.path == "/api/script":
            try:
                key = data.get("antKey","").strip() or ANTHROPIC_API_KEY
                if not key: self.json({"error":"no anthropic key"},401); return
                self.json({"script": self.gen_script(data, key)})
            except urllib.error.HTTPError as e:
                self.json({"error": f"Anthropic {e.code}: {e.read().decode()}"}, 500)
            except Exception as e:
                self.json({"error": str(e)}, 500)

        elif self.path == "/api/video":
            try: self.json(self.submit_video(data))
            except Exception as e: self.json({"error": str(e)}, 500)
        else:
            self.send_response(404); self.end_headers()

    def upload_img(self, body, headers):
        import urllib.parse
        ct = headers.get("Content-Type","")
        boundary = None
        for part in ct.split(";"):
            p = part.strip()
            if p.startswith("boundary="):
                boundary = p[9:].strip('"')
        if not boundary:
            raise Exception("no boundary")
        sep = ("--" + boundary).encode()
        parts = body.split(sep)
        img_data = None
        for part in parts:
            if b"filename" in part:
                idx = part.find(b"\r\n\r\n")
                if idx != -1:
                    img_data = part[idx+4:].rstrip(b"\r\n--")
                    break
        if not img_data:
            raise Exception("no image")
        b64 = base64.b64encode(img_data).decode()
        post = urllib.parse.urlencode({"key": IMGBB_API_KEY, "image": b64}).encode()
        ctx = ssl.create_default_context()
        req = urllib.request.Request("https://api.imgbb.com/1/upload", data=post,
              headers={"Content-Type":"application/x-www-form-urlencoded"}, method="POST")
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            res = json.loads(r.read())
        if res.get("success"):
            return {"url": res["data"]["url"]}
        raise Exception("imgbb failed")

    def gen_script(self, data, api_key):
        dm = {"gulf":"اللهجة الخليجية السعودية الأصيلة","moroccan":"الدارجة المغربية العامية","egyptian":"اللهجة المصرية العامية","iraqi":"اللهجة العراقية العامية"}
        tm = {"ugc":"شهادة UGC","pain":"مشكلة/حل","hook":"hook صادم","before":"قبل/بعد","product":"عرض منتج","urgency":"إلحاح"}
        dur = data.get("duration","30")
        words = "60-75 كلمة" if dur=="15" else "120-145 كلمة"
        prompt = f"""اكتب سكريبت فيديو إعلاني بـ{dm.get(data.get('dialect','gulf'),'الخليجية')} للمنتج:
المنتج: {data.get('product','')}
الوصف: {data.get('description','')}
العرض: {data.get('offer','')}
السوق: {data.get('market','KSA')}
نوع: {tm.get(data.get('type','ugc'),'')}
المدة: {dur} ثانية ({words})
قواعد: Hook قوي، لهجة طبيعية، لا مقدمات، CTA واضح. السكريبت فقط."""
        body = json.dumps({"model":"claude-haiku-4-5-20251001","max_tokens":1000,"messages":[{"role":"user","content":prompt}]}).encode()
        clean = api_key.strip().replace("\n","").replace("\r","")
        ctx = ssl.create_default_context()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
              headers={"Content-Type":"application/json","x-api-key":clean,"anthropic-version":"2023-06-01"}, method="POST")
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            return json.loads(r.read())["content"][0]["text"]

    def submit_video(self, data):
        if not KLING_ACCESS_KEY: raise Exception("no kling keys")
        token = kling_token()
        prompt = data.get("prompt","")
        image_url = data.get("image_url","")
        duration = data.get("duration","5")
        aspect = data.get("aspect_ratio","9:16")
        ctx = ssl.create_default_context()
        if image_url:
            payload = {"model_name":"kling-v1","image":image_url,"prompt":prompt,"duration":duration,"aspect_ratio":aspect,"mode":"std"}
            url = "https://api-singapore.klingai.com/v1/videos/image2video"
        else:
            payload = {"model_name":"kling-v1","prompt":prompt,"duration":duration,"aspect_ratio":aspect,"mode":"std"}
            url = "https://api-singapore.klingai.com/v1/videos/text2video"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body,
              headers={"Content-Type":"application/json","Authorization":f"Bearer {token}"}, method="POST")
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            res = json.loads(r.read())
        if res.get("code") != 0: raise Exception(f"Kling: {res.get('message','error')}")
        return {"task_id": res["data"]["task_id"], "status":"submitted"}

    def video_status(self, task_id):
        try:
            token = kling_token()
            ctx = ssl.create_default_context()
            for ep in ["image2video","text2video"]:
                url = f"https://api-singapore.klingai.com/v1/videos/{ep}/{task_id}"
                try:
                    req = urllib.request.Request(url, headers={"Authorization":f"Bearer {token}"}, method="GET")
                    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                        res = json.loads(r.read())
                    if res.get("code") == 0:
                        d = res["data"]
                        st = d.get("task_status","")
                        if st == "succeed":
                            vids = d.get("task_result",{}).get("videos",[])
                            if vids: self.json({"status":"done","url":vids[0]["url"]}); return
                        elif st == "failed":
                            self.json({"status":"failed","error":d.get("task_status_msg","failed")}); return
                        else:
                            self.json({"status":"processing"}); return
                except: continue
            self.json({"status":"processing"})
        except Exception as e:
            self.json({"error":str(e)}, 500)

    def serve_file(self, path, ct):
        try:
            with open(path, "rb") as f: content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", len(content))
            self.cors()
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.cors()
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    print(f"Server on port {PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
