from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlparse, unquote
import json
import mimetypes
import threading

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
HOST = "127.0.0.1"
PORT = 8000
LOCK = threading.RLock()

CATALOG = [
    {"id": 101, "name": "Термокружка Север", "category": "Для дома", "price": 890, "description": "Стальная кружка с крышкой, 350 мл.", "tone": "sea"},
    {"id": 102, "name": "Блокнот Линии", "category": "Канцелярия", "price": 420, "description": "Твёрдая обложка, 96 страниц.", "tone": "sand"},
    {"id": 103, "name": "Настольная лампа Луч", "category": "Для дома", "price": 2190, "description": "Мягкий свет и три уровня яркости.", "tone": "rose"},
]
BASE_PROFILE = {"name": "Анна Морозова", "email": "anna.qa@example.test", "phone": "+7 900 123-45-67", "role": "QA trainee"}
BASE_FEED = [
    {"id": "N-201", "title": "Обновлён график доставки", "category": "Доставка", "status": "Опубликовано"},
    {"id": "N-202", "title": "Новые способы оплаты", "category": "Оплата", "status": "На проверке"},
    {"id": "N-203", "title": "Изменения в правилах возврата", "category": "Возврат", "status": "Опубликовано"},
]

def fresh_state():
    return {"cart": {}, "profile": dict(BASE_PROFILE), "feed_version": 1, "sessions": {"lab-session-anna": "Анна Морозова"}}

STATE = fresh_state()

def cookie_session(headers):
    cookie = SimpleCookie()
    try:
        cookie.load(headers.get("Cookie", ""))
        morsel = cookie.get("qa_session")
        return morsel.value if morsel else None
    except Exception:
        return None

class Handler(BaseHTTPRequestHandler):
    server_version = "DevToolsQALab/1.0"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.log_date_time_string(), fmt % args), flush=True)

    def send_json(self, status, payload, headers=None, body=True):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        if not any(key.lower() == "cache-control" for key in (headers or {})):
            self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body and raw:
            self.wfile.write(raw)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_000_000:
                return None
            raw = self.rfile.read(length) if length else b"{}"
            value = json.loads(raw.decode("utf-8"))
            return value if isinstance(value, dict) else None
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def is_authenticated(self):
        token = cookie_session(self.headers)
        with LOCK:
            return bool(token and token in STATE["sessions"])

    def require_auth(self):
        if not self.is_authenticated():
            self.send_json(401, {"error": "Требуется вход"})
            return False
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in ("/", "/login"):
            return self.serve_file("login.html")
        # Serve the app's static assets explicitly. Without these routes the HTML
        # pages load, but their stylesheet and client-side application return 404.
        static_assets = {"/app.js": "app.js", "/styles.css": "styles.css"}
        if path in static_assets:
            return self.serve_file(static_assets[path])
        routes = {"/catalog": "catalog.html", "/cart": "cart.html", "/profile": "profile.html", "/settings": "settings.html"}
        if path in routes:
            return self.serve_file(routes[path])
        if path == "/api/session":
            authenticated = self.is_authenticated()
            return self.send_json(200, {"authenticated": authenticated, "user": BASE_PROFILE["name"] if authenticated else None})
        if path == "/api/catalog":
            return self.send_json(200, {"items": CATALOG})
        if path == "/api/cart":
            if not self.require_auth(): return
            with LOCK:
                return self.send_json(200, self.cart_response())
        if path == "/api/profile":
            if not self.require_auth(): return
            with LOCK:
                return self.send_json(200, {"profile": dict(STATE["profile"])})
        if path == "/api/settings/feed":
            if not self.require_auth(): return
            with LOCK:
                version = STATE["feed_version"]
                payload = {"version": version, "entries": [dict(x) for x in BASE_FEED] + ([{"id": "N-204", "title": "Летний график поддержки", "category": "Поддержка", "status": "Опубликовано"}] if version > 1 else [])}
            etag = '"feed-v%s"' % version
            cache_headers = {"Cache-Control": "public, max-age=120", "ETag": etag}
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                for key, value in cache_headers.items(): self.send_header(key, value)
                self.end_headers()
                return
            return self.send_json(200, payload, headers=cache_headers)
        return self.send_json(404, {"error": "Маршрут не найден"})

    def cart_response(self):
        lines = []
        total = 0
        units = 0
        for product_id, quantity in STATE["cart"].items():
            item = next((x for x in CATALOG if x["id"] == int(product_id)), None)
            if item:
                line = {"product": item, "quantity": quantity, "lineTotal": item["price"] * quantity}
                lines.append(line)
                total += line["lineTotal"]
                units += quantity
        return {"items": lines, "total": total, "units": units}

    def do_POST(self):
        path = urlparse(self.path).path
        data = self.read_json()
        if path == "/api/reset":
            with LOCK:
                STATE.clear()
                STATE.update(fresh_state())
            return self.send_json(200, {"ok": True}, headers={"Set-Cookie": "qa_session=; Max-Age=0; Path=/; SameSite=Lax; HttpOnly"})
        if path == "/api/login":
            data = data or {}
            if data.get("username") == "anna.qa" and data.get("password") == "QA_Lab_2026!":
                with LOCK:
                    STATE["sessions"]["lab-session-anna"] = "Анна Морозова"
                return self.send_json(200, {"ok": True, "user": "Анна Морозова"}, headers={"Set-Cookie": "qa_session=lab-session-anna; Max-Age=3600; Path=/; SameSite=Lax; HttpOnly"})
            return self.send_json(401, {"error": "Неверный логин или пароль"})
        if path == "/api/logout":
            if not self.require_auth(): return
            return self.send_json(200, {"ok": True}, headers={"Set-Cookie": "qa_session=; Max-Age=0; Path=/; SameSite=Lax; HttpOnly"})
        if not self.require_auth(): return
        if path == "/api/cart/items":
            data = data or {}
            product_id, quantity = data.get("productId"), data.get("quantity")
            if not isinstance(product_id, int) or not any(x["id"] == product_id for x in CATALOG):
                return self.send_json(400, {"error": "Неизвестный товар"})
            if not isinstance(quantity, int) or quantity < 1:
                return self.send_json(422, {"error": "Количество должно быть целым числом от 1"})
            with LOCK:
                STATE["cart"][str(product_id)] = STATE["cart"].get(str(product_id), 0) + quantity
                return self.send_json(201, self.cart_response())
        if path == "/api/settings/publish":
            with LOCK:
                STATE["feed_version"] += 1
                return self.send_json(200, {"published": True, "version": STATE["feed_version"]})
        return self.send_json(404, {"error": "Маршрут не найден"})

    def do_PUT(self):
        path = urlparse(self.path).path
        if path != "/api/profile":
            return self.send_json(404, {"error": "Маршрут не найден"})
        if not self.require_auth(): return
        data = self.read_json() or {}
        name, email, phone = data.get("name"), data.get("email"), data.get("phone")
        if not all(isinstance(v, str) and v.strip() for v in (name, email, phone)):
            return self.send_json(400, {"error": "Заполните все поля"})
        with LOCK:
            STATE["profile"]["name"] = name.strip()
            STATE["profile"]["email"] = email.strip()
            # The phone field is accepted in the request but is not applied to the profile.
            saved = dict(STATE["profile"])
        return self.send_json(200, {"saved": True, "profile": saved})

    def do_DELETE(self):
        path = urlparse(self.path).path
        if not self.require_auth(): return
        if path.startswith("/api/cart/items/"):
            product_id = path.rsplit("/", 1)[-1]
            with LOCK:
                STATE["cart"].pop(product_id, None)
                return self.send_json(200, self.cart_response())
        return self.send_json(404, {"error": "Маршрут не найден"})

    def serve_file(self, name):
        path = WEB / name
        try:
            raw = path.read_bytes()
        except OSError:
            self.send_json(404, {"error": "Файл не найден"})
            return
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in ("application/javascript", "text/javascript"):
            mime += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()

if __name__ == "__main__":
    print("DevTools QA Lab is running at http://localhost:%s" % PORT, flush=True)
    print("Press Ctrl+C to stop the local server.", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
