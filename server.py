import hashlib
import hmac
import json
import logging
import getpass
import os
import re
import secrets
import sqlite3
import sys
import time
import zlib
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse, urlsplit


ROOT = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("BANDILKI_DATABASE", str(ROOT / "data" / "bandilki.sqlite3")))
SESSION_COOKIE = "bandilki_session"
ADMIN_SESSION_COOKIE = "bandilki_admin_session"
SESSION_SECONDS = 60 * 60 * 24 * 30
ADMIN_SESSION_SECONDS = 60 * 60 * 8
PASSWORD_ITERATIONS = 310_000
MAX_REQUEST_BYTES = 64 * 1024
MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024
MAX_REVIEW_IMAGE_BYTES = 5 * 1024 * 1024
MAX_SITE_LOGO_BYTES = 5 * 1024 * 1024
MAX_INTRO_VIDEO_BYTES = 25 * 1024 * 1024
MAX_SITE_MEDIA_FORM_BYTES = MAX_SITE_LOGO_BYTES * 2 + MAX_INTRO_VIDEO_BYTES + 64 * 1024
PRODUCT_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
PHONE_RE = re.compile(r"^\+?[0-9 ()-]{10,20}$")
ORDER_STATUSES = ("Received", "New", "Contacted", "Processing", "Shipped", "Delivered", "Cancelled")
CATEGORY_ICON_OPTIONS = ("♧", "♙", "◉", "◌", "⌁", "◇", "⌘", "◎", "✧", "✦", "○", "❖", "✥", "♢", "❋", "♕", "▣")
CATEGORY_DEFAULT_ICONS = {
    "necklaces": "♧", "earrings": "♙", "rings": "◉", "bracelets": "◌",
    "anklets": "⌁", "pendants": "◇", "chains": "⌘", "bangles": "◎",
    "mangalsutras": "✧", "nose pins": "✦", "toe rings": "○",
    "jewellery sets": "❖", "1 gram gold": "✥", "oxidised jewellery": "♢",
    "hair accessories": "❋", "gift sets": "♕", "mystery jars": "▣",
}

SEED_PRODUCTS = (
    (1, "Solstice Pendant", "Necklaces", 48, "Bestseller", "photo-1617171511579-c2711d7a91f6", ["#d8b765", "#b8c6d9"]),
    (2, "Daydream Hoops", "Earrings", 36, "Just landed", "photo-1708390071625-4096abb3af24", ["#d8b765", "#cc6c6f"]),
    (3, "Little Wish Ring", "Rings", 42, "", "photo-1713950920412-97799efdf870", ["#d8b765", "#b8c6d9", "#cc6c6f"]),
    (4, "Sunday Chain", "Bracelets", 39, "", "photo-1615577073603-47a2345fc40b", ["#d8b765", "#b8c6d9"]),
    (5, "Blue Hour Drops", "Earrings", 52, "A little color", "photo-1708389827834-c4868dbf96ae", ["#5a7fb4", "#d8b765"]),
    (6, "Everyday Layer", "Necklaces", 58, "", "photo-1611652022419-a9419f74343d", ["#d8b765", "#cc6c6f"]),
    (7, "Tiny Spark Band", "Rings", 32, "Gift favorite", "photo-1670229470875-880737e736d0", ["#d8b765", "#b8c6d9"]),
    (8, "Good Luck Charm", "Bracelets", 45, "", "photo-1611591437281-460bfbe1220a", ["#d8b765", "#cc6c6f"]),
)


def product_image_directory():
    return DATABASE.parent / "product-images"


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exception_type, exception, traceback):
        try:
            return super().__exit__(exception_type, exception, traceback)
        finally:
            self.close()


def connect_db():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE, timeout=10, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    with connect_db() as connection:
        connection.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
        category_columns = {row["name"] for row in connection.execute("PRAGMA table_info(categories)")}
        if "icon" not in category_columns:
            connection.execute("ALTER TABLE categories ADD COLUMN icon TEXT NOT NULL DEFAULT '✧'")
            for name, icon in CATEGORY_DEFAULT_ICONS.items():
                connection.execute(
                    "UPDATE categories SET icon = ? WHERE name = ? COLLATE NOCASE",
                    (icon, name),
                )
        review_columns = {row["name"] for row in connection.execute("PRAGMA table_info(reviews)")}
        for column in ("email", "phone", "state", "address", "image_url"):
            if column not in review_columns:
                connection.execute(f"ALTER TABLE reviews ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        connection.executemany(
            """INSERT OR IGNORE INTO products
               (id, name, category, price, badge, image, colors_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (pid, name, category, price, badge, image, json.dumps(colors))
                for pid, name, category, price, badge, image, colors in SEED_PRODUCTS
            ],
        )
        if connection.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            category_names = (
                    "Necklaces", "Earrings", "Rings", "Bracelets", "Anklets",
                    "Pendants", "Chains", "Bangles", "Mangalsutras", "Nose Pins",
                    "Toe Rings", "Jewellery Sets", "1 Gram Gold", "Oxidised Jewellery",
                    "Hair Accessories", "Gift Sets", "Mystery Jars",
                )
            connection.executemany(
                "INSERT INTO categories (name, icon) VALUES (?, ?)",
                [(name, CATEGORY_DEFAULT_ICONS[name.lower()]) for name in category_names],
            )
        connection.execute(
            """INSERT INTO categories (name, icon)
               SELECT DISTINCT products.category, '✧' FROM products
               WHERE TRIM(products.category) <> ''
                 AND NOT EXISTS (
                     SELECT 1 FROM categories
                     WHERE categories.name = products.category COLLATE NOCASE
                 )"""
        )
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))


def create_admin_account(email, password):
    email = clean_email(email)
    if len(password) < 12 or len(password) > 128:
        raise ValueError("Admin passwords must be between 12 and 128 characters.")
    with connect_db() as connection:
        try:
            connection.execute(
                "INSERT INTO admin_users (email, password_hash) VALUES (?, ?)",
                (email, hash_password(password)),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("An admin account with that email already exists.") from error


def clean_text(value, field, maximum, required=True):
    if not isinstance(value, str):
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{field} is required.")
    value = value.strip()
    if required and not value:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{field} is required.")
    if len(value) > maximum:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{field} is too long.")
    return value


def clean_email(value):
    email = clean_text(value, "Email address", 254).lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ApiError(HTTPStatus.BAD_REQUEST, "Enter a valid email address.")
    return email


def clean_phone(value):
    phone = clean_text(value, "Phone number", 20)
    if not PHONE_RE.fullmatch(phone) or len(re.sub(r"\D", "", phone)) < 10:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Enter a valid phone number.")
    return phone


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return salt.hex() + "$" + digest.hex()


def verify_password(password, stored):
    try:
        salt_hex, expected = stored.split("$", 1)
        actual = hash_password(password, bytes.fromhex(salt_hex)).split("$", 1)[1]
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


class StoreHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def translate_path(self, path):
        request_path = urlsplit(path).path
        page_routes = {
            "/": ROOT / "user" / "html" / "index.html",
            "/index.html": ROOT / "user" / "html" / "index.html",
            "/admin.html": ROOT / "admin" / "html" / "index.html",
        }
        if request_path in page_routes:
            return str(page_routes[request_path])

        static_roots = {
            "/user/html/": ROOT / "user" / "html",
            "/user/css/": ROOT / "user" / "css",
            "/user/js/": ROOT / "user" / "js",
            "/user/assets/": ROOT / "user" / "assets",
            "/admin/html/": ROOT / "admin" / "html",
            "/admin/css/": ROOT / "admin" / "css",
            "/admin/js/": ROOT / "admin" / "js",
        }
        for prefix, directory in static_roots.items():
            if request_path.startswith(prefix):
                base = directory.resolve()
                target = (base / unquote(request_path[len(prefix):])).resolve()
                if target == base or base in target.parents:
                    return str(target)
                break
        return str(ROOT / "__not_found__")

    def log_message(self, message, *args):
        logging.info("%s - %s", self.address_string(), message % args)

    def send_head(self):
        path = urlparse(self.path).path
        if path.startswith("/review-images/"):
            match = re.fullmatch(r"/review-images/([a-f0-9]{32}\.(?:jpg|png))", path)
            if match is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Review image not found.")
                return None
            image_path = DATABASE.parent / "review-images" / match.group(1)
            try:
                image = image_path.open("rb")
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND, "Review image not found.")
                return None
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/jpeg" if image_path.suffix == ".jpg" else "image/png")
            self.send_header("Content-Length", str(image_path.stat().st_size))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return image
        if path.startswith("/images/"):
            match = re.fullmatch(r"/images/([a-zA-Z0-9._-]+\.png)", path)
            if match is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Image not found.")
                return None
            image_path = ROOT / "images" / match.group(1)
            try:
                image = image_path.open("rb")
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND, "Image not found.")
                return None
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(image_path.stat().st_size))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return image
        if path.startswith("/site-media/"):
            match = re.fullmatch(r"/site-media/([a-f0-9]{32}\.(?:jpg|png|mp4|webm))", path)
            if match is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Site media not found.")
                return None
            media_path = DATABASE.parent / "site-media" / match.group(1)
            try:
                media = media_path.open("rb")
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND, "Site media not found.")
                return None
            media_type = {
                ".jpg": "image/jpeg",
                ".png": "image/png",
                ".mp4": "video/mp4",
                ".webm": "video/webm",
            }[media_path.suffix]
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(media_path.stat().st_size))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return media
        if not path.startswith("/product-images/"):
            return super().send_head()
        match = re.fullmatch(r"/product-images/([a-f0-9]{32}\.(?:jpg|png))", path)
        if match is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Product image not found.")
            return None
        image_path = product_image_directory() / match.group(1)
        try:
            image = image_path.open("rb")
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, "Product image not found.")
            return None
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg" if image_path.suffix == ".jpg" else "image/png")
        self.send_header("Content-Length", str(image_path.stat().st_size))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        return image

    def send_json(self, status, value, headers=None):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if headers:
            for name, value in headers.items():
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid request size.") from error
        if size <= 0 or size > MAX_REQUEST_BYTES:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Request is empty or too large.")
        if "application/json" not in self.headers.get("Content-Type", "").lower():
            raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Send JSON data.")
        try:
            value = json.loads(self.rfile.read(size))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid JSON request.") from error
        if not isinstance(value, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Expected a JSON object.")
        return value

    def require_session(self, connection):
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        token = morsel.value if morsel else ""
        if not re.fullmatch(r"[a-f0-9]{64}", token):
            token = secrets.token_hex(32)
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        row = connection.execute(
            "SELECT customer_id FROM sessions WHERE token_hash = ? AND expires_at > ?",
            (token_hash, int(time.time())),
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT OR REPLACE INTO sessions (token_hash, expires_at) VALUES (?, ?)",
                (token_hash, int(time.time()) + SESSION_SECONDS),
            )
            customer_id = None
        else:
            customer_id = row["customer_id"]
            connection.execute(
                "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                (int(time.time()) + SESSION_SECONDS, token_hash),
            )
        self.session_token = token
        self.session_hash = token_hash
        self.customer_id = customer_id
        self.refresh_cookie()
        return customer_id

    def refresh_cookie(self):
        self.session_cookie = (
            f"{SESSION_COOKIE}={self.session_token}; Path=/; HttpOnly; SameSite=Lax; "
            f"Max-Age={SESSION_SECONDS}"
        )
        if self.headers.get("X-Forwarded-Proto", "").lower() == "https":
            self.session_cookie += "; Secure"

    def bind_authenticated_session(self, connection, customer_id):
        old_hash = self.session_hash
        token = secrets.token_hex(32)
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        connection.execute(
            "INSERT INTO sessions (token_hash, customer_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, customer_id, int(time.time()) + SESSION_SECONDS),
        )
        connection.execute(
            """INSERT INTO cart_items (token_hash, product_id, quantity)
               SELECT ?, product_id, quantity FROM cart_items WHERE token_hash = ?""",
            (token_hash, old_hash),
        )
        connection.execute("DELETE FROM sessions WHERE token_hash = ?", (old_hash,))
        self.session_token = token
        self.session_hash = token_hash
        self.customer_id = customer_id
        self.refresh_cookie()

    def json_response(self, status, value):
        headers = {}
        if hasattr(self, "session_cookie"):
            headers["Set-Cookie"] = self.session_cookie
        self.send_json(status, value, headers)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/admin/"):
            return self.handle_admin_get(parsed)
        if not parsed.path.startswith("/api/"):
            return super().do_GET()
        try:
            with connect_db() as connection:
                if parsed.path == "/api/health":
                    self.send_json(HTTPStatus.OK, {"ok": True})
                    return
                if parsed.path == "/api/site-settings":
                    self.send_json(HTTPStatus.OK, self.public_site_settings(connection))
                    return
                customer_id = self.require_session(connection)
                if parsed.path == "/api/products":
                    rows = connection.execute(
                        """SELECT id, name, category, price, badge, image, colors_json
                           FROM products ORDER BY id"""
                    ).fetchall()
                    result = {
                        "products": [
                            {
                                "id": row["id"],
                                "name": row["name"],
                                "cat": row["category"],
                                "price": row["price"],
                                "badge": row["badge"],
                                "img": row["image"],
                                "imageUrl": row["image"] if row["image"].startswith(("http://", "https://", "/")) else "",
                                "dots": json.loads(row["colors_json"]),
                            }
                            for row in rows
                        ]
                    }
                elif parsed.path == "/api/categories":
                    rows = connection.execute(
                        "SELECT name, icon FROM categories ORDER BY id"
                    ).fetchall()
                    result = {
                        "categories": [row["name"] for row in rows],
                        "icons": {row["name"]: row["icon"] for row in rows},
                    }
                elif parsed.path == "/api/session":
                    user = None
                    if customer_id is not None:
                        user = dict(connection.execute(
                            "SELECT id, name, email FROM customers WHERE id = ?",
                            (customer_id,),
                        ).fetchone())
                    result = {"user": user}
                elif parsed.path == "/api/cart":
                    result = {"items": self.cart_contents(connection)}
                elif parsed.path == "/api/reviews":
                    rows = connection.execute(
                        """SELECT name, rating, note, image_url, created_at
                           FROM reviews ORDER BY id DESC LIMIT 30"""
                    ).fetchall()
                    result = {"reviews": [dict(row) for row in rows]}
                elif parsed.path == "/api/orders/track":
                    query = parse_qs(parsed.query)
                    order_id = clean_text(query.get("orderId", [""])[0], "Order number", 40).upper()
                    phone = re.sub(r"\D", "", clean_phone(query.get("phone", [""])[0]))
                    row = connection.execute(
                        """SELECT id, customer_name, total, status, created_at
                           FROM orders
                           WHERE id = ? AND substr(phone_digits, -10) = substr(?, -10)""",
                        (order_id, phone),
                    ).fetchone()
                    if row is None:
                        raise ApiError(HTTPStatus.NOT_FOUND, "We couldn't find an order with those details.")
                    items = connection.execute(
                        """SELECT product_name, unit_price, quantity FROM order_items
                           WHERE order_id = ? ORDER BY id""",
                        (order_id,),
                    ).fetchall()
                    result = {"order": dict(row), "items": [dict(item) for item in items]}
                else:
                    raise ApiError(HTTPStatus.NOT_FOUND, "API route not found.")
            self.json_response(HTTPStatus.OK, result)
        except ApiError as error:
            self.send_json(error.status, {"error": error.message})
        except sqlite3.Error:
            logging.exception("Database error handling GET %s", parsed.path)
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The request could not be completed."})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/admin/"):
            return self.handle_admin_post(parsed)
        review_image_path = None
        try:
            content_type = self.headers.get("Content-Type", "").lower()
            if parsed.path == "/api/reviews" and content_type.startswith("multipart/form-data"):
                data, review_upload = self.read_review_form()
            else:
                data, review_upload = self.read_json(), None
            with connect_db() as connection:
                customer_id = self.require_session(connection)
                response_status = HTTPStatus.CREATED
                if parsed.path == "/api/accounts":
                    name = clean_text(data.get("name"), "Full name", 100)
                    email = clean_email(data.get("email"))
                    password = clean_text(data.get("password"), "Password", 128)
                    if len(password) < 8:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Use a password with at least 8 characters.")
                    try:
                        cursor = connection.execute(
                            "INSERT INTO customers (name, email, password_hash) VALUES (?, ?, ?)",
                            (name, email, hash_password(password)),
                        )
                    except sqlite3.IntegrityError as error:
                        raise ApiError(HTTPStatus.CONFLICT, "An account with that email already exists.") from error
                    customer_id = cursor.lastrowid
                    self.bind_authenticated_session(connection, customer_id)
                    result = {"user": {"id": customer_id, "name": name, "email": email}}
                elif parsed.path == "/api/session":
                    email = clean_email(data.get("email"))
                    password = clean_text(data.get("password"), "Password", 128)
                    user = connection.execute(
                        "SELECT id, name, email, password_hash FROM customers WHERE email = ?",
                        (email,),
                    ).fetchone()
                    if user is None or not verify_password(password, user["password_hash"]):
                        raise ApiError(HTTPStatus.UNAUTHORIZED, "Email or password is incorrect.")
                    customer_id = user["id"]
                    self.bind_authenticated_session(connection, customer_id)
                    result = {"user": {"id": user["id"], "name": user["name"], "email": user["email"]}}
                    response_status = HTTPStatus.OK
                elif parsed.path == "/api/orders":
                    name = clean_text(data.get("name"), "Full name", 100)
                    phone = clean_phone(data.get("phone"))
                    address = clean_text(data.get("address"), "Delivery address", 1000)
                    items = data.get("items")
                    if not isinstance(items, list) or not items or len(items) > 50:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Your bag is empty or has too many products.")
                    normalized = {}
                    for item in items:
                        if not isinstance(item, dict):
                            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid product in bag.")
                        try:
                            product_id = int(item.get("id"))
                            quantity = int(item.get("qty"))
                        except (TypeError, ValueError) as error:
                            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid product quantity.") from error
                        if quantity < 1 or quantity > 99:
                            raise ApiError(HTTPStatus.BAD_REQUEST, "Product quantity must be from 1 to 99.")
                        normalized[product_id] = normalized.get(product_id, 0) + quantity
                        if normalized[product_id] > 99:
                            raise ApiError(HTTPStatus.BAD_REQUEST, "Product quantity must be from 1 to 99.")
                    products = []
                    for product_id, quantity in normalized.items():
                        product = connection.execute(
                            "SELECT id, name, price FROM products WHERE id = ?",
                            (product_id,),
                        ).fetchone()
                        if product is None:
                            raise ApiError(HTTPStatus.BAD_REQUEST, "A product in your bag is no longer available.")
                        products.append((product, quantity))
                    total = round(sum(row["price"] * qty for row, qty in products), 2)
                    order_id = "BS-" + str(secrets.randbelow(900_000_000) + 100_000_000)
                    connection.execute(
                        """INSERT INTO orders
                           (id, customer_id, customer_name, phone, phone_digits, address, total)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (order_id, customer_id, name, phone, re.sub(r"\D", "", phone), address, total),
                    )
                    connection.executemany(
                        """INSERT INTO order_items
                           (order_id, product_id, product_name, unit_price, quantity)
                           VALUES (?, ?, ?, ?, ?)""",
                        [(order_id, row["id"], row["name"], row["price"], qty) for row, qty in products],
                    )
                    connection.execute("DELETE FROM cart_items WHERE token_hash = ?", (self.session_hash,))
                    result = {
                        "order": {
                            "id": order_id,
                            "total": total,
                            "status": "Received",
                            "customerName": name,
                            "phone": phone,
                        }
                    }
                elif parsed.path == "/api/contact":
                    name = clean_text(data.get("name"), "Full name", 100)
                    email = clean_email(data.get("email"))
                    phone = clean_phone(data.get("phone"))
                    address = clean_text(data.get("address"), "Address", 1000)
                    state = clean_text(data.get("state"), "State", 100)
                    zipcode = clean_text(data.get("zipcode"), "ZIP / PIN code", 20)
                    connection.execute(
                        """INSERT INTO contact_requests
                           (name, email, phone, address, state, zipcode)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (name, email, phone, address, state, zipcode),
                    )
                    result = {"message": "Your details were received."}
                elif parsed.path == "/api/newsletter":
                    email = clean_email(data.get("email"))
                    connection.execute(
                        "INSERT OR IGNORE INTO newsletter_subscriptions (email) VALUES (?)",
                        (email,),
                    )
                    result = {"message": "You're on the list. Thank you!"}
                elif parsed.path == "/api/reviews":
                    order_id = clean_text(data.get("orderId", ""), "Order number", 40, required=False).upper() or None
                    order = None
                    if order_id:
                        phone = re.sub(r"\D", "", clean_phone(data.get("phone")))
                        order = connection.execute(
                            """SELECT id, customer_name FROM orders
                               WHERE id = ? AND substr(phone_digits, -10) = substr(?, -10)""",
                            (order_id, phone),
                        ).fetchone()
                        if order is None:
                            raise ApiError(HTTPStatus.NOT_FOUND, "We couldn't verify that order and phone number.")
                        name = order["customer_name"]
                    else:
                        name = clean_text(data.get("name", "Bandilki customer"), "Name", 100, required=False)
                        name = name or "Bandilki customer"
                    phone_value = clean_text(data.get("phone", ""), "Phone number", 20, required=False)
                    phone = clean_phone(phone_value) if phone_value else ""
                    email_value = clean_text(data.get("email", ""), "Email address", 254, required=False)
                    email = clean_email(email_value) if email_value else ""
                    state = clean_text(data.get("state", ""), "State", 100, required=False)
                    address = clean_text(data.get("address", ""), "Address", 1000, required=False)
                    try:
                        rating = int(data.get("rating"))
                    except (TypeError, ValueError) as error:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Choose a rating from 1 to 5 stars.") from error
                    if rating < 1 or rating > 5:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Choose a rating from 1 to 5 stars.")
                    note = clean_text(data.get("note", ""), "Feedback", 500, required=False)
                    try:
                        cursor = connection.execute(
                            """INSERT INTO reviews
                               (customer_id, order_id, name, email, phone, state, address, rating, note)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (customer_id, order_id, name, email, phone, state, address, rating, note),
                        )
                    except sqlite3.IntegrityError as error:
                        if order_id:
                            raise ApiError(HTTPStatus.CONFLICT, "A rating has already been submitted for this order.") from error
                        raise
                    image_url = ""
                    if review_upload:
                        payload, extension = review_upload
                        image_directory = DATABASE.parent / "review-images"
                        image_directory.mkdir(parents=True, exist_ok=True)
                        filename = secrets.token_hex(16) + extension
                        review_image_path = image_directory / filename
                        review_image_path.write_bytes(payload)
                        image_url = "/review-images/" + filename
                        connection.execute(
                            "UPDATE reviews SET image_url = ? WHERE id = ?",
                            (image_url, cursor.lastrowid),
                        )
                    row = connection.execute(
                        """SELECT name, rating, note, image_url, created_at
                           FROM reviews WHERE id = ?""",
                        (cursor.lastrowid,),
                    ).fetchone()
                    result = {"review": dict(row)}
                else:
                    raise ApiError(HTTPStatus.NOT_FOUND, "API route not found.")
            self.json_response(response_status, result)
        except ApiError as error:
            if review_image_path:
                review_image_path.unlink(missing_ok=True)
            self.send_json(error.status, {"error": error.message})
        except sqlite3.Error:
            if review_image_path:
                review_image_path.unlink(missing_ok=True)
            logging.exception("Database error handling POST %s", parsed.path)
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The request could not be completed."})
        except OSError:
            if review_image_path:
                review_image_path.unlink(missing_ok=True)
            logging.exception("Could not save review image.")
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The review image could not be saved."})

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/admin/"):
            return self.handle_admin_put(parsed)
        try:
            if parsed.path != "/api/cart":
                raise ApiError(HTTPStatus.NOT_FOUND, "API route not found.")
            data = self.read_json()
            items = data.get("items")
            if not isinstance(items, list) or len(items) > 50:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid bag contents.")
            normalized = {}
            for item in items:
                if not isinstance(item, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid product in bag.")
                try:
                    product_id = int(item.get("id"))
                    quantity = int(item.get("qty"))
                except (TypeError, ValueError) as error:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid product quantity.") from error
                if quantity < 1 or quantity > 99:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Product quantity must be from 1 to 99.")
                normalized[product_id] = normalized.get(product_id, 0) + quantity
                if normalized[product_id] > 99:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Product quantity must be from 1 to 99.")
            with connect_db() as connection:
                self.require_session(connection)
                for product_id in normalized:
                    if connection.execute(
                        "SELECT 1 FROM products WHERE id = ?", (product_id,)
                    ).fetchone() is None:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "A product in your bag is unavailable.")
                connection.execute("DELETE FROM cart_items WHERE token_hash = ?", (self.session_hash,))
                connection.executemany(
                    "INSERT INTO cart_items (token_hash, product_id, quantity) VALUES (?, ?, ?)",
                    [(self.session_hash, pid, qty) for pid, qty in normalized.items()],
                )
                result = {"items": self.cart_contents(connection)}
            self.json_response(HTTPStatus.OK, result)
        except ApiError as error:
            self.send_json(error.status, {"error": error.message})
        except sqlite3.Error:
            logging.exception("Database error handling PUT %s", parsed.path)
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The request could not be completed."})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/admin/"):
            return self.handle_admin_delete(parsed)
        if parsed.path != "/api/session":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "API route not found."})
            return
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        if morsel:
            token_hash = hashlib.sha256(morsel.value.encode("ascii")).hexdigest()
            with connect_db() as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        self.send_json(
            HTTPStatus.OK,
            {"user": None},
            { "Set-Cookie": f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0" },
        )

    def require_admin(self, connection):
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get(ADMIN_SESSION_COOKIE)
        token = morsel.value if morsel else ""
        if not re.fullmatch(r"[a-f0-9]{64}", token):
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Sign in to the admin panel.")
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        row = connection.execute(
            """SELECT admin_users.id, admin_users.email
               FROM admin_sessions
               JOIN admin_users ON admin_users.id = admin_sessions.admin_id
               WHERE admin_sessions.token_hash = ? AND admin_sessions.expires_at > ?""",
            (token_hash, int(time.time())),
        ).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Sign in to the admin panel.")
        connection.execute(
            "UPDATE admin_sessions SET expires_at = ? WHERE token_hash = ?",
            (int(time.time()) + ADMIN_SESSION_SECONDS, token_hash),
        )
        self.admin_id = row["id"]
        self.admin_email = row["email"]
        self.admin_token_hash = token_hash
        return row

    def admin_json_response(self, status, value, token=None, clear_session=False):
        headers = {}
        if token:
            headers["Set-Cookie"] = (
                f"{ADMIN_SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; "
                f"Max-Age={ADMIN_SESSION_SECONDS}"
            )
        elif clear_session:
            headers["Set-Cookie"] = (
                f"{ADMIN_SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
            )
        if self.headers.get("X-Forwarded-Proto", "").lower() == "https" and token:
            headers["Set-Cookie"] += "; Secure"
        self.send_json(status, value, headers)

    def handle_admin_get(self, parsed):
        try:
            with connect_db() as connection:
                admin = self.require_admin(connection)
                if parsed.path == "/api/admin/session":
                    result = {"admin": {"id": admin["id"], "email": admin["email"]}}
                elif parsed.path == "/api/admin/dashboard":
                    result = {
                        "customers": connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
                        "orders": connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
                        "products": connection.execute("SELECT COUNT(*) FROM products").fetchone()[0],
                    }
                elif parsed.path == "/api/admin/customers":
                    rows = connection.execute(
                        """SELECT customers.id, customers.name, customers.email,
                                  customers.created_at, COUNT(orders.id) AS order_count
                           FROM customers LEFT JOIN orders ON orders.customer_id = customers.id
                           GROUP BY customers.id ORDER BY customers.created_at DESC, customers.id DESC"""
                    ).fetchall()
                    result = {"customers": [dict(row) for row in rows]}
                elif parsed.path == "/api/admin/products":
                    rows = connection.execute(
                        """SELECT id, name, category, price, badge, image, colors_json
                           FROM products ORDER BY id DESC"""
                    ).fetchall()
                    result = {"products": [self.admin_product_json(row) for row in rows]}
                elif parsed.path == "/api/admin/settings":
                    result = self.admin_site_settings(connection)
                elif parsed.path == "/api/admin/footer":
                    result = {"sections": self.footer_sections(connection)}
                elif parsed.path == "/api/admin/categories":
                    result = {"categories": self.admin_categories(connection)}
                elif parsed.path == "/api/admin/newsletter":
                    rows = connection.execute(
                        """SELECT email, created_at FROM newsletter_subscriptions
                           ORDER BY created_at DESC, id DESC"""
                    ).fetchall()
                    result = {"subscriptions": [dict(row) for row in rows]}
                elif parsed.path == "/api/admin/reviews":
                    rows = connection.execute(
                        """SELECT name, email, phone, state, address, rating, note, image_url, created_at
                           FROM reviews ORDER BY created_at DESC, id DESC"""
                    ).fetchall()
                    result = {"reviews": [dict(row) for row in rows]}
                elif parsed.path == "/api/admin/orders":
                    result = {"orders": self.admin_orders(connection)}
                elif parsed.path == "/api/admin/orders/track":
                    query = parse_qs(parsed.query)
                    order_id = clean_text(query.get("orderId", [""])[0], "Order number", 40).upper()
                    phone = re.sub(r"\D", "", clean_phone(query.get("phone", [""])[0]))
                    order = connection.execute(
                        """SELECT id, customer_name AS name, phone, address, total, status, created_at
                           FROM orders WHERE id = ?
                             AND substr(phone_digits, -10) = substr(?, -10)""",
                        (order_id, phone),
                    ).fetchone()
                    if order is None:
                        raise ApiError(HTTPStatus.NOT_FOUND, "No matching order was found.")
                    result = {"order": dict(order), "items": self.admin_order_items(connection, order_id)}
                elif re.fullmatch(r"/api/admin/orders/BS-[A-Za-z0-9-]+", parsed.path):
                    order_id = parsed.path.rsplit("/", 1)[1].upper()
                    order = connection.execute(
                        """SELECT orders.id, orders.customer_id, orders.customer_name AS name,
                                  orders.phone, orders.address, orders.total, orders.status,
                                  orders.created_at, customers.email
                           FROM orders LEFT JOIN customers ON customers.id = orders.customer_id
                           WHERE orders.id = ?""",
                        (order_id,),
                    ).fetchone()
                    if order is None:
                        raise ApiError(HTTPStatus.NOT_FOUND, "Order not found.")
                    result = {"order": dict(order), "items": self.admin_order_items(connection, order_id)}
                else:
                    raise ApiError(HTTPStatus.NOT_FOUND, "Admin API route not found.")
            self.send_json(HTTPStatus.OK, result)
        except ApiError as error:
            self.send_json(error.status, {"error": error.message})
        except sqlite3.Error:
            logging.exception("Database error handling admin GET %s", parsed.path)
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The admin request could not be completed."})

    def handle_admin_post(self, parsed):
        try:
            if parsed.path == "/api/admin/session":
                data = self.read_json()
                email = clean_email(data.get("email"))
                password = clean_text(data.get("password"), "Password", 128)
                with connect_db() as connection:
                    admin = connection.execute(
                        "SELECT id, email, password_hash FROM admin_users WHERE email = ?",
                        (email,),
                    ).fetchone()
                    if admin is None or not verify_password(password, admin["password_hash"]):
                        raise ApiError(HTTPStatus.UNAUTHORIZED, "Email or password is incorrect.")
                    token = secrets.token_hex(32)
                    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
                    connection.execute(
                        "INSERT INTO admin_sessions (token_hash, admin_id, expires_at) VALUES (?, ?, ?)",
                        (token_hash, admin["id"], int(time.time()) + ADMIN_SESSION_SECONDS),
                    )
                    result = {"admin": {"id": admin["id"], "email": admin["email"]}}
                self.admin_json_response(HTTPStatus.OK, result, token=token)
                return

            response_status = HTTPStatus.CREATED
            self.site_media_to_remove = []
            self.site_media_created = []
            with connect_db() as connection:
                self.require_admin(connection)
                if parsed.path == "/api/admin/settings":
                    data, uploads = self.read_site_media_form()
                    result = self.update_site_settings(connection, data, uploads)
                    response_status = HTTPStatus.OK
                elif parsed.path == "/api/admin/footer":
                    data = self.read_json()
                    category_names = [
                        row["name"]
                        for row in connection.execute("SELECT name FROM categories ORDER BY id").fetchall()
                    ]
                    sections = self.validate_footer_sections(data, category_names)
                    connection.execute(
                        """INSERT INTO site_settings (key, value) VALUES ('footer_sections', ?)
                           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                        (json.dumps(sections, ensure_ascii=False),),
                    )
                    result = {"sections": sections}
                    response_status = HTTPStatus.OK
                elif parsed.path == "/api/admin/products":
                    content_type = self.headers.get("Content-Type", "").lower()
                    if content_type.startswith("multipart/form-data"):
                        data, upload = self.read_product_form()
                    else:
                        data, upload = self.read_json(), None
                    result = {"product": self.create_admin_product(connection, data, upload)}
                elif parsed.path == "/api/admin/categories":
                    data = self.read_json()
                    name = clean_text(data.get("name"), "Category name", 80)
                    icon = self.clean_category_icon(data.get("icon", CATEGORY_DEFAULT_ICONS.get(name.lower(), "✧")))
                    if connection.execute(
                        "SELECT 1 FROM categories WHERE name = ? COLLATE NOCASE", (name,)
                    ).fetchone():
                        raise ApiError(HTTPStatus.CONFLICT, "A category with that name already exists.")
                    cursor = connection.execute("INSERT INTO categories (name, icon) VALUES (?, ?)", (name, icon))
                    result = {"category": {"id": cursor.lastrowid, "name": name, "icon": icon, "product_count": 0}}
                elif parsed.path == "/api/admin/orders":
                    data = self.read_json()
                    name = clean_text(data.get("name"), "Customer name", 100)
                    phone = clean_phone(data.get("phone"))
                    item_name = clean_text(data.get("items"), "Items / notes", 300)
                    address = clean_text(data.get("address"), "Delivery address", 1000)
                    try:
                        total = float(data.get("total"))
                    except (TypeError, ValueError) as error:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Enter a valid order total.") from error
                    if total < 0 or total > 10_000_000:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Order total is outside the allowed range.")
                    order_id = self.new_order_id(connection)
                    connection.execute(
                        """INSERT INTO orders
                           (id, customer_name, phone, phone_digits, address, total, status)
                           VALUES (?, ?, ?, ?, ?, ?, 'New')""",
                        (order_id, name, phone, re.sub(r"\D", "", phone), address, round(total, 2)),
                    )
                    connection.execute(
                        """INSERT INTO order_items
                           (order_id, product_name, unit_price, quantity)
                           VALUES (?, ?, ?, 1)""",
                        (order_id, item_name, round(total, 2)),
                    )
                    result = {"order": {"id": order_id}}
                else:
                    raise ApiError(HTTPStatus.NOT_FOUND, "Admin API route not found.")
            self.site_media_created = []
            for file_path in self.site_media_to_remove:
                try:
                    file_path.unlink(missing_ok=True)
                except OSError:
                    logging.exception("Could not remove replaced site media file %s", file_path.name)
            self.send_json(response_status, result)
        except ApiError as error:
            self.send_json(error.status, {"error": error.message})
        except sqlite3.Error:
            self.cleanup_failed_site_media()
            logging.exception("Database error handling admin POST %s", parsed.path)
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The admin request could not be completed."})
        except OSError:
            self.cleanup_failed_site_media()
            logging.exception("File error handling admin POST %s", parsed.path)
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The uploaded media could not be saved."})

    def cleanup_failed_site_media(self):
        for file_path in getattr(self, "site_media_created", []):
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                logging.exception("Could not remove incomplete site media file %s", file_path.name)
        self.site_media_created = []

    @staticmethod
    def site_settings_values(connection):
        return {
            row["key"]: row["value"]
            for row in connection.execute(
                """SELECT key, value FROM site_settings
                   WHERE key IN ('logo_url', 'intro_video_url', 'hero_image_url', 'footer_sections')"""
            ).fetchall()
        }

    @classmethod
    def public_site_settings(cls, connection):
        settings = cls.site_settings_values(connection)
        review_stats = connection.execute(
            "SELECT AVG(rating) AS average_rating, COUNT(*) AS review_count FROM reviews"
        ).fetchone()
        delivered_count = connection.execute(
            "SELECT COUNT(*) FROM orders WHERE status = 'Delivered'"
        ).fetchone()[0]
        return {
            "logoUrl": settings.get("logo_url", "/user/assets/bandilki-mark.svg"),
            "introVideoUrl": settings.get("intro_video_url", ""),
            "heroImageUrl": settings.get("hero_image_url", "/images/storefront-hero.png"),
            "averageRating": round(review_stats["average_rating"], 1) if review_stats["average_rating"] is not None else None,
            "reviewCount": review_stats["review_count"],
            "deliveredOrderCount": delivered_count,
            "footerSections": cls.footer_sections(connection),
        }

    @classmethod
    def admin_site_settings(cls, connection):
        return cls.public_site_settings(connection)

    @classmethod
    def footer_sections(cls, connection):
        category_names = [
            row["name"] for row in connection.execute("SELECT name FROM categories ORDER BY id").fetchall()
        ]
        stored = cls.site_settings_values(connection).get("footer_sections")
        if stored is not None:
            try:
                sections = json.loads(stored)
            except json.JSONDecodeError as error:
                logging.exception("Stored footer configuration is invalid")
                raise sqlite3.DatabaseError("Stored footer configuration is invalid.") from error
            return cls.validate_footer_sections({"sections": sections})
        explore_links = [{"label": "Shop all", "url": "#shop", "filter": "All"}]
        explore_links.extend(
            {
                "label": "Bracelets / Kadas" if name == "Bracelets" else name,
                "url": "#shop",
                "filter": name,
            }
            for name in category_names
        )
        return [
            {"id": "explore", "title": "Explore", "links": explore_links},
            {
                "id": "contact",
                "title": "Contact us",
                "links": [
                    {"label": "bandilkishines@gmail.com", "url": "mailto:bandilkishines@gmail.com", "filter": ""},
                    {"label": "+91 81490 70941", "url": "tel:+918149070941", "filter": ""},
                    {"label": "WhatsApp us", "url": "https://wa.me/918149070941", "filter": ""},
                    {"label": "Track your order", "url": "#trackOrderBackdrop", "filter": ""},
                ],
            },
            {
                "id": "follow",
                "title": "Follow along",
                "links": [
                    {"label": "WhatsApp Broadcast", "url": "https://chat.whatsapp.com/F9D3hKgcoh040tcgbi5nJr", "filter": ""},
                    {"label": "Instagram", "url": "https://www.instagram.com/bandilkishines/", "filter": ""},
                ],
            },
            {
                "id": "legal",
                "title": "",
                "links": [
                    {
                        "label": "Terms & Conditions",
                        "url": "mailto:bandilkishines@gmail.com?subject=Terms%20and%20Conditions",
                        "filter": "",
                    },
                    {
                        "label": "Refund Policy",
                        "url": "mailto:bandilkishines@gmail.com?subject=Refund%20Policy",
                        "filter": "",
                    },
                ],
            },
        ]

    @staticmethod
    def validate_footer_sections(data, category_names=None):
        sections = data.get("sections")
        expected = ("explore", "contact", "follow", "legal")
        allowed_filters = {"All", *(category_names or [])}
        if not isinstance(sections, list) or len(sections) != len(expected):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Footer settings must include all four footer link groups.")
        normalized = []
        for section, expected_id in zip(sections, expected):
            if not isinstance(section, dict) or section.get("id") != expected_id:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Footer link groups are invalid or out of order.")
            title = clean_text(section.get("title", ""), "Footer section heading", 60, required=expected_id != "legal")
            links = section.get("links")
            if not isinstance(links, list) or len(links) > 25:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Each footer section can contain up to 25 links.")
            normalized_links = []
            for link in links:
                if not isinstance(link, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Footer links must include a label and destination.")
                label = clean_text(link.get("label"), "Footer link name", 80)
                destination = clean_text(link.get("url"), "Footer link destination", 1000)
                if any(ord(character) < 32 for character in destination) or "\\" in destination:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Enter a valid footer link destination.")
                if destination.startswith("#"):
                    pass
                elif destination.startswith("/") and not destination.startswith("//"):
                    pass
                else:
                    try:
                        parsed = urlsplit(destination)
                    except ValueError as error:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Enter a valid footer link destination.") from error
                    scheme = parsed.scheme.lower()
                    valid_http_url = scheme in ("http", "https") and bool(parsed.netloc and parsed.hostname)
                    valid_contact_url = (
                        (scheme == "mailto" and bool(parsed.path))
                        or (scheme == "tel" and bool(parsed.path))
                    )
                    if not valid_http_url and not valid_contact_url:
                        raise ApiError(
                            HTTPStatus.BAD_REQUEST,
                            "Footer links must use a website, email, phone, or page destination.",
                        )
                category_filter = clean_text(
                    link.get("filter", ""), "Footer category filter", 80, required=False
                )
                if category_filter and category_names is not None and category_filter not in allowed_filters:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Choose an existing storefront category for the link filter.")
                if category_filter and expected_id != "explore":
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Category filters can only be used for Explore links.")
                normalized_links.append(
                    {"label": label, "url": destination, "filter": category_filter}
                )
            normalized.append({"id": expected_id, "title": title, "links": normalized_links})
        return normalized

    def read_site_media_form(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid request size.") from error
        if size <= 0:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Settings form is empty.")
        if size > MAX_SITE_MEDIA_FORM_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "The uploaded media is too large.")
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Send the settings form with multipart form data.")
        body = self.rfile.read(size)
        if len(body) != size:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Incomplete settings upload.")
        try:
            message = BytesParser(policy=policy.default).parsebytes(
                b"Content-Type: " + content_type.encode("ascii") +
                b"\r\nMIME-Version: 1.0\r\n\r\n" + body
            )
        except (UnicodeEncodeError, ValueError) as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid settings form.") from error
        if not message.is_multipart():
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid settings form.")
        fields = {}
        uploads = {}
        for part in message.iter_parts():
            field_name = part.get_param("name", header="content-disposition")
            if part.get_content_disposition() != "form-data" or not field_name:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid settings form field.")
            payload = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if field_name in ("logo", "introVideo", "heroImage") and filename in (None, "") and not payload:
                continue
            if filename is not None:
                if field_name not in ("logo", "introVideo", "heroImage") or field_name in uploads:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Upload one logo, banner image, and intro video at most.")
                media_type = part.get_content_type().lower()
                if field_name in ("logo", "heroImage"):
                    extension = PRODUCT_IMAGE_TYPES.get(media_type)
                    valid = (
                        len(payload) <= MAX_SITE_LOGO_BYTES
                        and extension is not None
                        and self.valid_product_image(payload, media_type)
                    )
                    if len(payload) > MAX_SITE_LOGO_BYTES:
                        label = "Banner images" if field_name == "heroImage" else "Logo images"
                        raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"{label} must be 5 MB or smaller.")
                    if not valid:
                        label = "banner image" if field_name == "heroImage" else "logo"
                        raise ApiError(HTTPStatus.BAD_REQUEST, f"Upload a valid JPEG or PNG {label}.")
                else:
                    video_types = {"video/mp4": ".mp4", "video/webm": ".webm"}
                    extension = video_types.get(media_type)
                    if len(payload) > MAX_INTRO_VIDEO_BYTES:
                        raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Intro videos must be 25 MB or smaller.")
                    valid = (
                        extension == ".mp4" and len(payload) >= 12 and payload[4:8] == b"ftyp"
                    ) or (
                        extension == ".webm" and payload.startswith(b"\x1a\x45\xdf\xa3")
                    )
                    if not valid:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Upload a valid MP4 or WebM intro video.")
                uploads[field_name] = (payload, extension)
            else:
                if field_name not in ("clearLogo", "clearIntroVideo", "clearHeroImage") or field_name in fields:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid or repeated settings field.")
                try:
                    fields[field_name] = payload.decode(part.get_content_charset() or "utf-8")
                except (LookupError, UnicodeDecodeError) as error:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Settings form contains invalid text.") from error
        if "logo" in uploads and fields.get("clearLogo") == "true":
            raise ApiError(HTTPStatus.BAD_REQUEST, "Choose either a new logo or remove the current logo.")
        if "introVideo" in uploads and fields.get("clearIntroVideo") == "true":
            raise ApiError(HTTPStatus.BAD_REQUEST, "Choose either a new video or remove the current video.")
        if "heroImage" in uploads and fields.get("clearHeroImage") == "true":
            raise ApiError(HTTPStatus.BAD_REQUEST, "Choose either a new banner image or restore the default banner.")
        return fields, uploads

    def update_site_settings(self, connection, fields, uploads):
        current = self.site_settings_values(connection)
        directory = DATABASE.parent / "site-media"
        new_files = {}
        old_files = []
        try:
            media_settings = (
                ("logo", "logo_url", "clearLogo"),
                ("introVideo", "intro_video_url", "clearIntroVideo"),
                ("heroImage", "hero_image_url", "clearHeroImage"),
            )
            for field_name, key, clear_field in media_settings:
                if fields.get(clear_field) == "true":
                    old_value = current.get(key, "")
                    if old_value.startswith("/site-media/"):
                        old_files.append(directory / old_value.rsplit("/", 1)[1])
                    connection.execute("DELETE FROM site_settings WHERE key = ?", (key,))
                if field_name in uploads:
                    payload, extension = uploads[field_name]
                    directory.mkdir(parents=True, exist_ok=True)
                    filename = secrets.token_hex(16) + extension
                    file_path = directory / filename
                    self.site_media_created.append(file_path)
                    file_path.write_bytes(payload)
                    new_files[key] = (file_path, "/site-media/" + filename)
                    old_value = current.get(key, "")
                    if old_value.startswith("/site-media/"):
                        old_files.append(directory / old_value.rsplit("/", 1)[1])
                    connection.execute(
                        """INSERT INTO site_settings (key, value) VALUES (?, ?)
                           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                        (key, "/site-media/" + filename),
                    )
        except (OSError, sqlite3.Error):
            for file_path, _ in new_files.values():
                file_path.unlink(missing_ok=True)
            raise
        updated = self.admin_site_settings(connection)
        self.site_media_to_remove = old_files
        return updated

    def read_product_form(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid request size.") from error
        if size <= 0:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Product image upload is empty.")
        if size > MAX_PRODUCT_IMAGE_BYTES + MAX_REQUEST_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Product image upload is too large.")
        if not self.headers.get("Content-Type", "").lower().startswith("multipart/form-data"):
            raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Send a product form with an image upload.")
        body = self.rfile.read(size)
        if len(body) != size:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Incomplete product image upload.")
        try:
            message = BytesParser(policy=policy.default).parsebytes(
                b"Content-Type: " + self.headers["Content-Type"].encode("ascii") +
                b"\r\nMIME-Version: 1.0\r\n\r\n" + body
            )
        except (UnicodeEncodeError, ValueError) as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid product form.") from error
        if not message.is_multipart():
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid product form.")
        form = {}
        upload = None
        for part in message.iter_parts():
            disposition = part.get_content_disposition()
            field_name = part.get_param("name", header="content-disposition")
            if disposition != "form-data" or not field_name:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid product form field.")
            payload = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if field_name == "image" and filename in (None, "") and not payload:
                continue
            if filename is not None:
                if field_name != "image" or upload is not None:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Upload a single product image.")
                if len(payload) > MAX_PRODUCT_IMAGE_BYTES:
                    raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Product images must be 5 MB or smaller.")
                media_type = part.get_content_type().lower()
                extension = PRODUCT_IMAGE_TYPES.get(media_type)
                if extension is None or not self.valid_product_image(payload, media_type):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Upload a valid JPEG or PNG image.")
                upload = (payload, extension)
            else:
                if field_name not in ("name", "category", "price", "badge", "imageUrl") or field_name in form:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid or repeated product form field.")
                try:
                    form[field_name] = payload.decode(part.get_content_charset() or "utf-8")
                except (LookupError, UnicodeDecodeError) as error:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Product form contains invalid text.") from error
        return form, upload

    def read_review_form(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid request size.") from error
        if size <= 0 or size > MAX_REVIEW_IMAGE_BYTES + MAX_REQUEST_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Review submission or image is too large.")
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Send feedback with multipart form data.")
        body = self.rfile.read(size)
        if len(body) != size:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Incomplete feedback submission.")
        try:
            message = BytesParser(policy=policy.default).parsebytes(
                b"Content-Type: " + content_type.encode("ascii") +
                b"\r\nMIME-Version: 1.0\r\n\r\n" + body
            )
        except (UnicodeEncodeError, ValueError) as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid feedback submission.") from error
        if not message.is_multipart():
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid feedback submission.")
        form = {}
        upload = None
        allowed_fields = {"name", "email", "phone", "state", "address", "rating", "note", "orderId"}
        for part in message.iter_parts():
            field_name = part.get_param("name", header="content-disposition")
            if part.get_content_disposition() != "form-data" or not field_name:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid feedback form field.")
            payload = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if field_name == "image" and filename in (None, "") and not payload:
                continue
            if filename is not None:
                if field_name != "image" or upload is not None:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Upload one review image at most.")
                if len(payload) > MAX_REVIEW_IMAGE_BYTES:
                    raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Review images must be 5 MB or smaller.")
                media_type = part.get_content_type().lower()
                extension = PRODUCT_IMAGE_TYPES.get(media_type)
                if extension is None or not self.valid_product_image(payload, media_type):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Upload a valid JPEG or PNG review image.")
                upload = (payload, extension)
                continue
            if field_name not in allowed_fields or field_name in form:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid or repeated feedback form field.")
            try:
                form[field_name] = payload.decode(part.get_content_charset() or "utf-8")
            except (LookupError, UnicodeDecodeError) as error:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Feedback form contains invalid text.") from error
        return form, upload

    @staticmethod
    def valid_product_image(payload, media_type):
        if media_type == "image/png":
            if len(payload) < 45 or not payload.startswith(b"\x89PNG\r\n\x1a\n"):
                return False
            offset = 8
            width = height = 0
            first_chunk = True
            has_image_data = False
            has_end = False
            while offset + 12 <= len(payload):
                chunk_length = int.from_bytes(payload[offset:offset + 4], "big")
                chunk_end = offset + 12 + chunk_length
                if chunk_end > len(payload):
                    return False
                chunk_type = payload[offset + 4:offset + 8]
                chunk_data = payload[offset + 8:offset + 8 + chunk_length]
                expected_crc = int.from_bytes(payload[offset + 8 + chunk_length:chunk_end], "big")
                if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
                    return False
                if first_chunk:
                    if chunk_type != b"IHDR" or chunk_length != 13:
                        return False
                    width = int.from_bytes(chunk_data[:4], "big")
                    height = int.from_bytes(chunk_data[4:8], "big")
                    first_chunk = False
                elif chunk_type == b"IHDR":
                    return False
                if chunk_type == b"IDAT":
                    has_image_data = True
                if chunk_type == b"IEND":
                    if chunk_length != 0 or not has_image_data or chunk_end != len(payload):
                        return False
                    has_end = True
                    break
                offset = chunk_end
            if not has_end:
                return False
        else:
            if len(payload) < 4 or payload[:2] != b"\xff\xd8":
                return False
            offset = 2
            width = height = 0
            sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
            while offset + 4 <= len(payload):
                if payload[offset] != 0xFF:
                    return False
                while offset < len(payload) and payload[offset] == 0xFF:
                    offset += 1
                if offset >= len(payload):
                    return False
                marker = payload[offset]
                offset += 1
                if marker in {0xD8, 0x01, *range(0xD0, 0xD8)}:
                    continue
                if offset + 2 > len(payload):
                    return False
                segment_length = int.from_bytes(payload[offset:offset + 2], "big")
                if segment_length < 2 or offset + segment_length > len(payload):
                    return False
                if marker in sof_markers:
                    if segment_length < 7:
                        return False
                    height = int.from_bytes(payload[offset + 3:offset + 5], "big")
                    width = int.from_bytes(payload[offset + 5:offset + 7], "big")
                if marker == 0xDA:
                    return (
                        width > 0 and height > 0 and segment_length >= 6
                        and payload.endswith(b"\xff\xd9")
                        and width <= 12000 and height <= 12000
                        and width * height <= 40_000_000
                    )
                if marker == 0xD9:
                    return False
                offset += segment_length
        return 0 < width <= 12000 and 0 < height <= 12000 and width * height <= 40_000_000

    def create_admin_product(self, connection, data, upload):
        name = clean_text(data.get("name"), "Product name", 120)
        category = clean_text(data.get("category"), "Category", 80)
        category_row = connection.execute(
            "SELECT name FROM categories WHERE name = ? COLLATE NOCASE", (category,)
        ).fetchone()
        if category_row is None:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Choose a category that exists in the store.")
        category = category_row["name"]
        try:
            price = float(data.get("price"))
        except (TypeError, ValueError) as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Enter a valid product price.") from error
        if not 0 < price <= 1_000_000:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Product price must be greater than zero.")
        image = clean_text(data.get("imageUrl", ""), "Photo URL", 2000, required=False)
        if image and not re.fullmatch(r"https?://[^\s]+", image):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Photo URL must start with http:// or https://.")
        if image and upload:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Choose either an uploaded image or a photo URL, not both.")
        badge = clean_text(data.get("badge", ""), "Badge", 24, required=False)
        next_id = connection.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM products").fetchone()[0]
        image_path = None
        if upload:
            payload, extension = upload
            image_directory = product_image_directory()
            image_directory.mkdir(parents=True, exist_ok=True)
            filename = secrets.token_hex(16) + extension
            image_path = image_directory / filename
            image_path.write_bytes(payload)
            image = "/product-images/" + filename
        image = image or "photo-1599643478518-a784e5dc4c8f"
        try:
            connection.execute(
                """INSERT INTO products
                   (id, name, category, price, badge, image, colors_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (next_id, name, category, price, badge, image, json.dumps(["#d8b765", "#5a7fb4"])),
            )
            row = connection.execute(
                """SELECT id, name, category, price, badge, image, colors_json
                   FROM products WHERE id = ?""",
                (next_id,),
            ).fetchone()
        except sqlite3.Error:
            if image_path:
                image_path.unlink(missing_ok=True)
            raise
        return self.admin_product_json(row)

    def handle_admin_put(self, parsed):
        category_match = re.fullmatch(r"/api/admin/categories/(\d+)", parsed.path)
        match = re.fullmatch(r"/api/admin/orders/(BS-[A-Za-z0-9-]+)/status", parsed.path)
        try:
            if category_match:
                data = self.read_json()
                name = clean_text(data.get("name"), "Category name", 80)
                icon = self.clean_category_icon(data.get("icon", "✧"))
                category_id = int(category_match.group(1))
                with connect_db() as connection:
                    self.require_admin(connection)
                    category = connection.execute(
                        "SELECT id, name FROM categories WHERE id = ?", (category_id,)
                    ).fetchone()
                    if category is None:
                        raise ApiError(HTTPStatus.NOT_FOUND, "Category not found.")
                    if connection.execute(
                        "SELECT 1 FROM categories WHERE name = ? COLLATE NOCASE AND id <> ?",
                        (name, category_id),
                    ).fetchone():
                        raise ApiError(HTTPStatus.CONFLICT, "A category with that name already exists.")
                    connection.execute(
                        "UPDATE products SET category = ? WHERE category = ? COLLATE NOCASE",
                        (name, category["name"]),
                    )
                    connection.execute(
                        "UPDATE categories SET name = ?, icon = ? WHERE id = ?",
                        (name, icon, category_id),
                    )
                self.send_json(HTTPStatus.OK, {"category": {"id": category_id, "name": name, "icon": icon}})
                return
            if match is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "Admin API route not found.")
            data = self.read_json()
            status = clean_text(data.get("status"), "Order status", 30)
            if status not in ORDER_STATUSES:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Choose a valid order status.")
            order_id = match.group(1).upper()
            with connect_db() as connection:
                self.require_admin(connection)
                cursor = connection.execute(
                    "UPDATE orders SET status = ? WHERE id = ?",
                    (status, order_id),
                )
                if cursor.rowcount == 0:
                    raise ApiError(HTTPStatus.NOT_FOUND, "Order not found.")
            self.send_json(HTTPStatus.OK, {"order": {"id": order_id, "status": status}})
        except ApiError as error:
            self.send_json(error.status, {"error": error.message})
        except sqlite3.Error:
            logging.exception("Database error handling admin PUT %s", parsed.path)
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The admin request could not be completed."})

    def handle_admin_delete(self, parsed):
        try:
            if parsed.path == "/api/admin/session":
                cookie = SimpleCookie()
                cookie.load(self.headers.get("Cookie", ""))
                morsel = cookie.get(ADMIN_SESSION_COOKIE)
                if morsel and re.fullmatch(r"[a-f0-9]{64}", morsel.value):
                    token_hash = hashlib.sha256(morsel.value.encode("ascii")).hexdigest()
                    with connect_db() as connection:
                        connection.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (token_hash,))
                self.admin_json_response(HTTPStatus.OK, {"admin": None}, clear_session=True)
                return
            category_match = re.fullmatch(r"/api/admin/categories/(\d+)", parsed.path)
            if category_match:
                category_id = int(category_match.group(1))
                with connect_db() as connection:
                    self.require_admin(connection)
                    category = connection.execute(
                        "SELECT id, name FROM categories WHERE id = ?", (category_id,)
                    ).fetchone()
                    if category is None:
                        raise ApiError(HTTPStatus.NOT_FOUND, "Category not found.")
                    if connection.execute("SELECT COUNT(*) FROM categories").fetchone()[0] <= 1:
                        raise ApiError(HTTPStatus.CONFLICT, "Keep at least one category in the store.")
                    product_count = connection.execute(
                        "SELECT COUNT(*) FROM products WHERE category = ? COLLATE NOCASE",
                        (category["name"],),
                    ).fetchone()[0]
                    data = self.read_json()
                    replacement_id = data.get("replacementId")
                    replacement = None
                    if replacement_id not in (None, ""):
                        try:
                            replacement_id = int(replacement_id)
                        except (TypeError, ValueError) as error:
                            raise ApiError(HTTPStatus.BAD_REQUEST, "Choose a valid replacement category.") from error
                        if replacement_id == category_id:
                            raise ApiError(HTTPStatus.BAD_REQUEST, "Choose a different replacement category.")
                        replacement = connection.execute(
                            "SELECT id, name FROM categories WHERE id = ?", (replacement_id,)
                        ).fetchone()
                        if replacement is None:
                            raise ApiError(HTTPStatus.BAD_REQUEST, "Choose a valid replacement category.")
                    if product_count and replacement is None:
                        raise ApiError(
                            HTTPStatus.CONFLICT,
                            "This category has products. Choose another category to move them into before deleting it.",
                        )
                    if product_count:
                        connection.execute(
                            "UPDATE products SET category = ? WHERE category = ? COLLATE NOCASE",
                            (replacement["name"], category["name"]),
                        )
                    connection.execute("DELETE FROM categories WHERE id = ?", (category_id,))
                self.send_json(
                    HTTPStatus.OK,
                    {"deleted": category_id, "moved_products": product_count},
                )
                return
            match = re.fullmatch(r"/api/admin/products/(\d+)", parsed.path)
            if match is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "Admin API route not found.")
            product_id = int(match.group(1))
            image_path = None
            with connect_db() as connection:
                self.require_admin(connection)
                row = connection.execute("SELECT image FROM products WHERE id = ?", (product_id,)).fetchone()
                if row is None:
                    raise ApiError(HTTPStatus.NOT_FOUND, "Product not found.")
                connection.execute("DELETE FROM cart_items WHERE product_id = ?", (product_id,))
                connection.execute("DELETE FROM products WHERE id = ?", (product_id,))
                image_match = re.fullmatch(r"/product-images/([a-f0-9]{32}\.(?:jpg|png))", row["image"])
                if image_match:
                    image_path = product_image_directory() / image_match.group(1)
            if image_path:
                try:
                    image_path.unlink(missing_ok=True)
                except OSError:
                    logging.exception("Could not remove image for deleted product %s", product_id)
                    self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Product deleted, but its image file could not be removed."})
                    return
            self.send_json(HTTPStatus.OK, {"deleted": product_id})
        except ApiError as error:
            self.send_json(error.status, {"error": error.message})
        except sqlite3.Error:
            logging.exception("Database error handling admin DELETE %s", parsed.path)
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The admin request could not be completed."})

    @staticmethod
    def admin_product_json(row):
        image = row["image"]
        is_url = image.startswith(("http://", "https://"))
        is_uploaded = image.startswith("/product-images/")
        return {
            "id": row["id"],
            "name": row["name"],
            "cat": "Bracelets / Kadas" if row["category"] == "Bracelets" else row["category"],
            "price": row["price"],
            "badge": row["badge"],
            "img": "" if is_url or is_uploaded else image,
            "imageUrl": image if is_url or is_uploaded else "",
            "dots": json.loads(row["colors_json"]),
        }

    @staticmethod
    def admin_categories(connection):
        rows = connection.execute(
            """SELECT categories.id, categories.name, categories.icon, COUNT(products.id) AS product_count
               FROM categories
               LEFT JOIN products ON products.category = categories.name COLLATE NOCASE
               GROUP BY categories.id
               ORDER BY categories.name COLLATE NOCASE"""
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def clean_category_icon(value):
        icon = clean_text(value, "Category icon", 4)
        if icon not in CATEGORY_ICON_OPTIONS:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Choose a supported category icon.")
        return icon

    @staticmethod
    def admin_order_items(connection, order_id):
        rows = connection.execute(
            """SELECT product_name AS name, unit_price AS price, quantity AS qty
               FROM order_items WHERE order_id = ? ORDER BY id""",
            (order_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    @classmethod
    def admin_orders(cls, connection):
        rows = connection.execute(
            """SELECT id, customer_id, customer_name AS name, phone, address, total,
                      status, created_at
               FROM orders ORDER BY created_at DESC, id DESC"""
        ).fetchall()
        orders = []
        for row in rows:
            order = dict(row)
            order["items"] = cls.admin_order_items(connection, order["id"])
            orders.append(order)
        return orders

    @staticmethod
    def new_order_id(connection):
        for _ in range(10):
            order_id = "BS-" + str(secrets.randbelow(900_000_000) + 100_000_000)
            if connection.execute("SELECT 1 FROM orders WHERE id = ?", (order_id,)).fetchone() is None:
                return order_id
        raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "Could not generate a unique order number.")

    def cart_contents(self, connection):
        rows = connection.execute(
            """SELECT p.id, p.name, p.category, p.price, p.image, ci.quantity AS qty
               FROM cart_items ci JOIN products p ON p.id = ci.product_id
               WHERE ci.token_hash = ? ORDER BY p.id""",
            (self.session_hash,),
        ).fetchall()
        return [dict(row) for row in rows]


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    initialize_database()
    if sys.argv[1:] == ["--create-admin"]:
        try:
            email = input("Admin email: ").strip()
            password = getpass.getpass("Admin password (12+ characters): ")
            confirmation = getpass.getpass("Confirm admin password: ")
            if password != confirmation:
                raise ValueError("Passwords do not match.")
            create_admin_account(email, password)
        except (ValueError, ApiError) as error:
            raise SystemExit(str(error)) from error
        print("Admin account created. Start the server with: py -3 server.py")
        return
    if sys.argv[1:]:
        raise SystemExit("Usage: py -3 server.py [--create-admin]")
    host = os.environ.get("HOST", "0.0.0.0")
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError as error:
        raise SystemExit("PORT must be a valid number.") from error
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be between 1 and 65535.")
    server = ThreadingHTTPServer((host, port), StoreHandler)
    logging.info("Bandilki store listening on %s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
