"""CSRF protection, authentication decorators and redirect safety."""
import functools
import hmac
import secrets
from urllib.parse import urlparse

from flask import abort, flash, g, redirect, request, session, url_for


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(32)
    return session["_csrf"]


def verify_csrf():
    """Reject any state-changing request that lacks the per-session CSRF token."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRFToken", "")
        expected = session.get("_csrf", "")
        if not expected or not hmac.compare_digest(str(sent), expected):
            abort(400, description="Security token missing or expired. Please reload the page and try again.")


def safe_next(target):
    """Only allow same-site relative redirects after login."""
    if not target:
        return None
    parts = urlparse(target)
    if parts.netloc or parts.scheme or not target.startswith("/") or target.startswith("//"):
        return None
    return target


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @functools.wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator
