import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from src.utils import get_env


auth_bp = Blueprint("auth", __name__)

PUBLIC_ENDPOINTS = {
    "health",
    "verify_webhook",
    "receive_webhook",
    "ingest_companion",
    "static",
    "auth.login",
}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
_failed_logins = defaultdict(deque)


def configure_auth(app):
    app.secret_key = get_env("FLASK_SECRET_KEY")
    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=get_env("SESSION_COOKIE_SECURE", "1") != "0",
    )


def auth_is_configured():
    return bool(
        current_app.secret_key
        and get_env("QUERY_USERNAME")
        and get_env("QUERY_PASSWORD_HASH")
    )


def current_username():
    return session.get("authenticated_user")


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _client_key():
    forwarded = request.headers.get("CF-Connecting-IP") or request.headers.get(
        "X-Forwarded-For", ""
    )
    return (forwarded.split(",", 1)[0].strip() or request.remote_addr or "unknown")


def _is_rate_limited(client_key):
    now = time.monotonic()
    attempts = _failed_logins[client_key]
    while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) >= MAX_LOGIN_ATTEMPTS


def _record_failed_login(client_key):
    _failed_logins[client_key].append(time.monotonic())


def _safe_next_url(value):
    if not value:
        return url_for("dashboard.dashboard")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return url_for("dashboard.dashboard")
    return value


@auth_bp.before_app_request
def protect_private_routes():
    if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
        return None

    if not auth_is_configured():
        if request.endpoint == "auth.logout":
            return redirect(url_for("auth.login"))
        return redirect(url_for("auth.login", setup="required"))

    if request.method == "POST":
        expected = session.get("csrf_token", "")
        supplied = request.form.get("csrf_token") or request.headers.get(
            "X-CSRF-Token", ""
        )
        if not expected or not hmac.compare_digest(expected, supplied):
            abort(400, description="Invalid CSRF token")

    if not current_username() and request.endpoint not in {"auth.login"}:
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))

    return None


@auth_bp.after_app_request
def add_security_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; frame-ancestors 'self'; form-action 'self'"
    )
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_bp.app_context_processor
def inject_auth_context():
    return {
        "csrf_token": csrf_token if current_app.secret_key else lambda: "",
        "authenticated_user": current_username(),
    }


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    configured = auth_is_configured()
    error = None
    next_url = _safe_next_url(request.values.get("next"))

    if request.method == "POST":
        if not configured:
            return render_template("login.html", configured=False, error=None), 503
        expected_token = session.get("csrf_token", "")
        supplied_token = request.form.get("csrf_token", "")
        if not expected_token or not hmac.compare_digest(
            expected_token, supplied_token
        ):
            abort(400, description="Invalid CSRF token")

        client_key = _client_key()
        if _is_rate_limited(client_key):
            error = "Too many failed attempts. Try again in 15 minutes."
        else:
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            expected_username = get_env("QUERY_USERNAME", "")
            username_ok = hmac.compare_digest(username, expected_username)
            password_ok = check_password_hash(
                get_env("QUERY_PASSWORD_HASH", ""), password
            )
            if username_ok and password_ok:
                _failed_logins.pop(client_key, None)
                session.clear()
                session["authenticated_user"] = expected_username
                session["csrf_token"] = secrets.token_urlsafe(32)
                session.permanent = True
                return redirect(next_url)

            _record_failed_login(client_key)
            error = "Invalid username or password."

    return render_template(
        "login.html",
        configured=configured,
        error=error,
        next_url=next_url,
    )


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
