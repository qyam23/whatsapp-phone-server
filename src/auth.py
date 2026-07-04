import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta
from functools import wraps
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from src.utils import get_env


auth_bp = Blueprint("auth", __name__)

DEFAULT_AI_USERNAME = "qyam2323"
DEFAULT_AI_PASSWORD_HASH = (
    "scrypt:32768:8:1$a3XOgWgth0iKLskn$"
    "d9e41e8f5c5b3b3fb1b8c278000d9164720c52dceb53abc7146ebaf9b1492faa"
    "772a8385c6b8e487b7e9ec38af580619461e07d7d762b46fe4a0788bda19b795"
)
DEFAULT_FLASK_SECRET_KEY = (
    "631bf6cadcd1409c9df19c51c9da4c211e9b817e7456585bb1068a35d5b3fbbd"
)
CSRF_EXEMPT_ENDPOINTS = {
    "receive_webhook",
    "ingest_companion",
    "auth.login",
}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
_failed_logins = defaultdict(deque)


def configure_auth(app):
    app.secret_key = get_env("FLASK_SECRET_KEY", DEFAULT_FLASK_SECRET_KEY)
    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=get_env("SESSION_COOKIE_SECURE", "0") == "1",
    )


def ai_login_required(view=None, *, api=False):
    def decorator(function):
        function.ai_auth_required = True
        function.ai_auth_api = api

        @wraps(function)
        def wrapped(*args, **kwargs):
            return function(*args, **kwargs)

        wrapped.ai_auth_required = True
        wrapped.ai_auth_api = api
        return wrapped

    return decorator(view) if view is not None else decorator


def ai_is_authenticated():
    return session.get("ai_authenticated") is True


def current_username():
    if not ai_is_authenticated():
        return None
    return session.get("ai_username")


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
    return forwarded.split(",", 1)[0].strip() or request.remote_addr or "unknown"


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
        return url_for("query.query_database")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return url_for("query.query_database")
    return value


def _validate_csrf():
    expected = session.get("csrf_token", "")
    supplied = request.form.get("csrf_token") or request.headers.get(
        "X-CSRF-Token", ""
    )
    if not expected or not hmac.compare_digest(expected, supplied):
        abort(400, description="Invalid CSRF token")


@auth_bp.before_app_request
def enforce_request_security():
    if request.endpoint is None:
        return None

    view = current_app.view_functions.get(request.endpoint)
    if getattr(view, "ai_auth_required", False) and not ai_is_authenticated():
        if getattr(view, "ai_auth_api", False):
            return (
                jsonify(
                    {
                        "error": "ai_authentication_required",
                        "message": "AI mode requires login.",
                        "login_url": url_for("auth.login"),
                    }
                ),
                401,
            )
        return redirect(
            url_for("auth.login", next=request.full_path.rstrip("?"))
        )

    if (
        request.method == "POST"
        and request.endpoint not in CSRF_EXEMPT_ENDPOINTS
    ):
        _validate_csrf()

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
        "csrf_token": csrf_token,
        "ai_authenticated": ai_is_authenticated(),
        "authenticated_user": current_username(),
    }


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    next_url = _safe_next_url(request.values.get("next"))

    if request.method == "POST":
        _validate_csrf()
        client_key = _client_key()
        if _is_rate_limited(client_key):
            error = "Too many failed attempts. Try again in 15 minutes."
        else:
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            username_ok = hmac.compare_digest(username, DEFAULT_AI_USERNAME)
            password_ok = check_password_hash(DEFAULT_AI_PASSWORD_HASH, password)
            if username_ok and password_ok:
                _failed_logins.pop(client_key, None)
                session.clear()
                session["ai_authenticated"] = True
                session["ai_username"] = DEFAULT_AI_USERNAME
                session["csrf_token"] = secrets.token_urlsafe(32)
                session.permanent = True
                return redirect(next_url)

            _record_failed_login(client_key)
            error = "Invalid username or password."

    return render_template(
        "login.html",
        error=error,
        next_url=next_url,
    )


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard.dashboard"))
