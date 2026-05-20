from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.request
import urllib.error
import os

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
PORT = int(os.environ.get("PORT", 8000))

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.serve_file("index.html", "text/html; charset=utf-8")
        elif self.path == "/health":
            self.send_json({"status": "ok"})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/script":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                script = self.generate_script(data)
                self.send_json({"script": script})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
        else:
            self.send_response(404)
            self.end_headers()

    def generate_script(self, data):
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
        dialect = data.get("dialect", "gulf")
        vtype = data.get("type", "ugc")

        prompt = f"""اكتب سكريبت فيديو إعلاني بـ{dialect_map.get(dialect, 'الخليجية')} للمنتج:

المنتج: {data.get('product', '')}
الوصف: {data.get('description', '')}
العرض: {data.get('offer', '')}
السوق: {data.get('market', 'KSA')}
نوع الفيديو: {type_map.get(vtype, '')}
المدة: {dur} ثانية ({words})

قواعد صارمة:
1. Hook قوي في أول جملة يوقف التمرير
2. اللهجة طبيعية وأصيلة 100%
3. لا مقدمات — كل جملة لها هدف
4. أرقام وتفاصيل ملموسة تزيد المصداقية
5. CTA واضح في الآخر
6. السكريبت فقط جاهز للقراءة بدون أي عناوين أو تعليقات"""

        req_data = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]

    def serve_file(self, filename, ctype):
        try:
            with open(filename, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", len(content))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

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
