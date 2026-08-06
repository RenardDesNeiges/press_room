"""Flask webapp for the press-room.

Serves a login page; once authenticated, renders the latest (or a historical)
issue for the logged-in user from the database. Page assets (page.css, page.js)
and the editorial MP3 are served from the database/templates.
"""

from __future__ import annotations

import html
import io
from datetime import datetime
from pathlib import Path

import yaml
from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

import db as database
from config import DEFAULT_TEMPLATE_DIR, SECRET_KEY
from gen_static_page import build_html, format_datetime_fr, get_french_weekday


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = SECRET_KEY

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if database.verify_user(username, password):
                session["username"] = username
                return redirect(url_for("index"))
            return render_template("login.html", error="Identifiants incorrects.")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        username = session.get("username")
        if not username:
            return redirect(url_for("login"))
        day = request.args.get("day")
        page_html = render_issue(username, day)
        return render_template("reader.html", page_html=page_html)

    @app.route("/audio/<day>/editorial.mp3")
    def audio(day: str):
        username = session.get("username")
        if not username:
            abort(401)
        user = database.get_user(username)
        issue = database.latest_issue(user["id"])
        if issue is None or issue["day"] != day:
            abort(404)
        content = database.get_artifact(issue["id"], "editorial_mp3")
        if content is None:
            abort(404)
        return send_file(
            io.BytesIO(content), mimetype="audio/mpeg", as_attachment=False
        )

    @app.route("/page.css")
    def page_css():
        return send_file(DEFAULT_TEMPLATE_DIR / "page.css", mimetype="text/css")

    @app.route("/page.js")
    def page_js():
        return send_file(DEFAULT_TEMPLATE_DIR / "page.js", mimetype="text/javascript")

    return app


def render_issue(username: str, day: str | None = None) -> str:
    """Build the newspaper HTML for a user's issue (latest or by day)."""
    user = database.get_user(username)
    if user is None:
        abort(404)

    issue = None
    for candidate in database.list_issues(user["id"]):
        if day is None or candidate["day"] == day:
            issue = candidate
            break
    if issue is None:
        return "<p>Aucune édition pour ce jour. Lancez le pipeline.</p>"

    prepared = database.get_artifact(issue["id"], "prepared_entries")
    parsed = database.get_artifact(issue["id"], "parsed_entries")
    raw = prepared or parsed
    if raw is None:
        return "<p>Aucune donnée pour cette édition. Lancez le pipeline.</p>"

    data = yaml.safe_load(raw)
    entries = data.get("entries", [])
    editorial = data.get("editorial")
    title = data.get("title")

    generated_at = format_datetime_fr(_parse_run_at(issue))

    user_info = (
        f'<span class="top-bar-user">{html.escape(username)}</span>'
        f'<a class="top-bar-logout" href="{url_for("logout")}">Déconnexion</a>'
    )

    html_content = build_html(
        entries,
        editorial=editorial,
        headline=title,
        weekday=get_french_weekday(),
        generated_at=generated_at,
        user_info=user_info,
    )

    # Rewire asset and audio URLs to the Flask routes for this issue.
    html_content = html_content.replace('src="data/editorial.mp3"', f'src="/audio/{issue["day"]}/editorial.mp3"')
    html_content = html_content.replace('href="page.css"', 'href="/page.css"')
    html_content = html_content.replace('src="page.js"', 'src="/page.js"')

    return html_content


def _parse_run_at(issue) -> datetime:
    """Return the pipeline run time for an issue (fallback: now)."""
    run_at = issue["run_at"]
    if not run_at:
        return datetime.now()
    try:
        return datetime.fromisoformat(run_at)
    except ValueError:
        return datetime.now()


if __name__ == "__main__":
    database.init_db()
    create_app().run(host="0.0.0.0", port=8080, debug=True)