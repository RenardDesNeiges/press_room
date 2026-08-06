"""Flask webapp for the press-room.

Serves a login page; once authenticated, renders the latest (or a historical)
issue for the logged-in user from the database. Page assets (page.css, page.js)
and the editorial MP3 are served from the database/templates.
"""

from __future__ import annotations

import html
import io
import json
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from src import db as database
from config import DEFAULT_TEMPLATE_DIR, SECRET_KEY
from src.gen_static_page import (
    build_html,
    format_date_fr,
    format_datetime_fr,
    get_french_weekday,
)


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(DEFAULT_TEMPLATE_DIR))
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

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        username = session.get("username")
        if not username:
            return redirect(url_for("login"))
        user = database.get_user(username)
        if user is None:
            session.clear()
            return redirect(url_for("login"))

        if request.method == "POST":
            action = request.form.get("action")
            if action == "save_feeds":
                if _save_feeds(user["id"], request.form.get("feeds_json", "")):
                    flash("Flux RSS enregistrés.")
                else:
                    flash("Erreur lors de l'enregistrement des flux RSS.")
            elif action == "save_interests":
                database.set_user_file(
                    user["id"], "readers_interests.md", request.form.get("interests", "")
                )
                flash("Préférences de lecture enregistrées.")
            elif action == "save_credentials":
                flash(_save_credentials(user, session, request.form))
            return redirect(url_for("settings"))

        publications = _load_feeds(user["id"])
        interests = database.get_user_file(user["id"], "readers_interests.md") or ""
        runs = []
        for issue in database.list_issues(user["id"]):
            try:
                when = format_datetime_fr(_parse_run_at(issue))
            except ValueError:
                when = issue["run_at"]
            runs.append({"day": issue["day"], "run_at": when})
        return render_template(
            "settings.html",
            username=username,
            publications=publications,
            interests=interests,
            runs=runs,
        )

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
        f'<a class="top-bar-link" href="{url_for("settings")}">Paramètres</a>'
        f'<span class="top-bar-user">{html.escape(username)}</span>'
        f'<a class="top-bar-logout" href="{url_for("logout")}">Déconnexion</a>'
    )

    day_menu = _build_day_menu(user["id"], current_day=issue["day"])

    html_content = build_html(
        entries,
        editorial=editorial,
        headline=title,
        weekday=get_french_weekday(),
        generated_at=generated_at,
        user_info=user_info,
        day_menu=day_menu,
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


def _build_day_menu(user_id: int, current_day: str) -> str:
    """Build the dropdown menu listing issues from the last 7 days (at most).

    Each item links to the issue for that day. The currently displayed day is
    marked with the ``is-current`` class.
    """
    cutoff = (datetime.now() - timedelta(days=7)).date().isoformat()
    items = []
    for issue in database.list_issues(user_id):
        if issue["day"] < cutoff:
            continue
        label = format_date_fr(datetime.fromisoformat(issue["day"]))
        cls = "is-current" if issue["day"] == current_day else ""
        items.append(
            f'<a class="day-menu-item {cls}" href="/?day={issue["day"]}">{label}</a>'
        )
    if not items:
        return ""
    return '<span class="day-menu-heading">Éditions des 7 derniers jours</span>' + "".join(items)


def _load_feeds(user_id: int) -> list[dict]:
    """Return the publications list from the user's feeds.yml, normalized for the editor.

    A ``notes`` field that looks like a feed URL is treated as a single feed.
    """
    content = database.get_user_file(user_id, "feeds.yml")
    if not content:
        return []
    data = yaml.safe_load(content) or {}
    publications = []
    for pub in data.get("publications", []) or []:
        urls = [u for u in (pub.get("feeds") or []) if u]
        if not urls:
            note = pub.get("notes")
            if isinstance(note, str) and note.startswith("http"):
                urls = [note]
        publications.append(
            {
                "name": pub.get("name") or "",
                "lang": pub.get("lang") or "",
                "feeds": urls,
            }
        )
    return publications


def _save_feeds(user_id: int, feeds_json: str) -> bool:
    """Parse the editor's JSON payload and write it back as feeds.yml."""
    try:
        raw = json.loads(feeds_json)
    except (ValueError, TypeError):
        return False
    publications = []
    for pub in raw or []:
        if not isinstance(pub, dict):
            continue
        name = str(pub.get("name") or "").strip()
        if not name:
            continue
        entry = {"name": name}
        lang = str(pub.get("lang") or "").strip()
        if lang:
            entry["lang"] = lang
        urls = [str(u).strip() for u in (pub.get("feeds") or []) if str(u).strip()]
        if urls:
            entry["feeds"] = urls
        publications.append(entry)
    yaml_text = yaml.safe_dump(
        {"publications": publications}, allow_unicode=True, sort_keys=False
    )
    database.set_user_file(user_id, "feeds.yml", yaml_text)
    return True


def _save_credentials(user, session, form) -> str:
    """Change the username/password. Returns a user-facing message."""
    new_username = str(form.get("new_username") or "").strip()
    new_password = form.get("new_password") or ""
    new_password2 = form.get("new_password2") or ""
    if new_username != user["username"] and database.get_user(new_username):
        return "Ce nom d'utilisateur est déjà pris."
    if new_password and new_password != new_password2:
        return "Les mots de passe ne correspondent pas."
    if new_username != user["username"]:
        database.update_username(user["id"], new_username)
        session["username"] = new_username
    if new_password:
        database.update_password(user["id"], new_password)
    return "Identifiants mis à jour."


if __name__ == "__main__":
    database.init_db()
    create_app().run(host="0.0.0.0", port=8080, debug=True)