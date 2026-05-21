from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.request
import urllib.error
import ssl
import os
import time
import hmac
import hashlib
import base64

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
KLING_ACCESS_KEY = os.environ.get("KLING_ACCESS_KEY", "").strip()
KLING_SECRET_KEY = os.environ.get("KLING_SECRET_KEY", "").strip()
PORT = int(os.environ.get("PORT", 8000))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def generate_kling_token(access_key, secret_key):
    now = int(time.time())
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).rstrip(b'=').decode()
    payload = base64.urlsafe_b64encode(json.dumps({"iss":access_key,"exp":now+1800,"nbf":now-5}).encode()).rstrip(b'=').decode()
    msg = f"{header}.{payload}"
    sig = base64.urlsafe_b64encode(hmac.new(secret_key.encode(), msg.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
    return f"{msg}.{sig}"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            filepath = os.path.join(BASE_DIR, "index.html")
            self.serve_file(filepath, "text/html; charset=utf-8")
        elif self.path == "/health":
            self.send_json({"status": "ok", "anthropic": bool(ANTHROPIC_API_KEY), "kling": bool(KLING_ACCESS_KEY)})
        elif self.path.startswith("/api/video/status/"):
            task_id = self.path.split("/")[-1]
            self.check_video_status(task_id)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except:
            self.send_json({"error": "Invalid JSON"}, 400)
            return

        if self.path == "/api/script":
            try:
                api_key = data.get("antKey", "").strip() or ANTHROPIC_API_KEY
                if not api_key:
                    self.send_json({"error": "Anthropic API Key غير موجود"}, 401)
                    return
                script = self.generate_script(data, api_key)
                self.send_json({"script": script})
            except urllib.error.HTTPError as e:
                self.send_json({"error": f"Anthropic Error {e.code}: {e.read().decode()}"}, 500)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif self.path == "/api/video":
            try:
                result = self.generate_video(data)
                self.send_json(result)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
        else:
            self.send_response(404)
            self.end_headers()

    def generate_script(self, data, api_key):
        dialect_map = {
            "gulf": "اللهجة الخليجية السعودية الأصيلة",
            "moroccan": "الدارجة المغربية العامية",
            "egyptian": "اللهجة المصرية العامية",
            "iraqi": "اللهجة العراقية العامية"
        }
        type_map = {
            "ugc": "شهادة UGC كأن عميلة حقيقية تحكي تجربتها",
            "pain": "ابدأ بالمشكلة والألم ثم قدم المنتج كحل",
            "hook": "hook صادم يوقف التمرير في أول ثانيتين",
            "before": "قبل وبعد — تباين حياة الشخص قبل وبعد المنتج",
            "product": "عرض مزايا المنتج بشكل جذاب",
            "urgency": "إلحاح وندرة — العرض محدود اطلب الآن"
        }
        dur = data.get("duration", "30")
        words = "60-75 كلمة" if dur == "15" else "120-145 كلمة"
        prompt = f"""اكتب سكريبت فيديو إعلاني بـ{dialect_map.get(data.get('dialect','gulf'), 'الخليجية')} للمنتج:
المنتج: {data.get('product', '')}
الوصف: {data.get('description', '')}
العرض: {data.get('offer', '')}
السوق: {data.get('market', 'KSA')}
نوع الفيديو: {type_map.get(data.get('type','ugc'), '')}
المدة: {dur} ثانية ({words})
قواعد: Hook قوي، لهجة طبيعية، لا مقدمات، CTA واضح في الآخر. السكريبت فقط بدون عناوين."""

        req_data = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()

        ctx = ssl.create_default_context()
        clean_key = api_key.strip().replace('\n', '').replace('\r', '')
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=req_data,
            headers={"Content-Type": "application/json", "x-api-key": clean_key, "anthropic-version": "2023-06-01"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            return json.loads(resp.read())["content"][0]["text"]

    def generate_video(self, data):
        if not KLING_ACCESS_KEY or not KLING_SECRET_KEY:
            raise Exception("Kling API Keys غير موجودة في السيرفر")

        token = generate_kling_token(KLING_ACCESS_KEY, KLING_SECRET_KEY)
        prompt = data.get("prompt", "")
        image_url = data.get("image_url", "")
        duration = data.get("duration", "5")

        if image_url:
            body = json.dumps({
                "model_name": "kling-v1",
                "image": image_url,
                "prompt": prompt,
                "duration": duration,
                "aspect_ratio": "9:16",
                "mode": "std"
            }).encode()
            url = "https://api-singapore.klingai.com/v1/videos/image2video"
        else:
            body = json.dumps({
                "model_name": "kling-v1",
                "prompt": prompt,
                "duration": duration,
                "aspect_ratio": "9:16",
                "mode": "std"
            }).encode()
            url = "https://api-singapore.klingai.com/v1/videos/text2video"

        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            result = json.loads(resp.read())

        if result.get("code") != 0:
            raise Exception(f"Kling Error: {result.get('message', 'Unknown error')}")

        task_id = result["data"]["task_id"]
        return {"task_id": task_id, "status": "submitted"}

    def check_video_status(self, task_id):
        try:
            if not KLING_ACCESS_KEY or not KLING_SECRET_KEY:
                self.send_json({"error": "Kling keys missing"}, 500)
                return

            token = generate_kling_token(KLING_ACCESS_KEY, KLING_SECRET_KEY)
            ctx = ssl.create_default_context()

            # Try image2video first, then text2video
            for endpoint in ["image2video", "text2video"]:
                url = f"https://api-singapore.klingai.com/v1/videos/{endpoint}/{task_id}"
                try:
                    req = urllib.request.Request(
                        url,
                        headers={"Authorization": f"Bearer {token}"},
                        method="GET"
                    )
                    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                        result = json.loads(resp.read())
                        if result.get("code") == 0:
                            task_data = result["data"]
                            status = task_data.get("task_status", "")
                            if status == "succeed":
                                videos = task_data.get("task_result", {}).get("videos", [])
                                if videos:
                                    self.send_json({"status": "done", "url": videos[0]["url"]})
                                    return
                            elif status == "failed":
                                self.send_json({"status": "failed", "error": task_data.get("task_status_msg", "Failed")})
                                return
                            else:
                                self.send_json({"status": "processing"})
                                return
                except:
                    continue

            self.send_json({"status": "processing"})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def serve_file(self, filepath, ctype):
        try:
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", len(content))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    print(f"Server running on port {PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
