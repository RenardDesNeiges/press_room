"""Flask webapp for the press-room.

Serves a login page; once authenticated, renders the latest (or a historical)
issue for the logged-in user from the database. Page assets (page.css, page.js)
and the editorial MP3 are served from the database/templates.
"""

from __future__ import annotations

import functools
import html
import io
import json
import logging
import os
import random
import threading
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

from src.config import (
    DATA_DIR,
    DEFAULT_TEMPLATE_DIR,
    SCHEDULE_ENABLED,
    SCHEDULE_USERS,
    schedule_clock,
    setup_secret_key,
)
from src import db as database
from src.scheduler import start_daily
from src.run_pipeline import run_for_user
from src.gen_static_page import (
    build_html,
    format_date_fr,
    format_datetime_fr,
    get_french_weekday,
)


logger = logging.getLogger(__name__)

_PIPELINE_RUNNING: set[str] = set()
_PIPELINE_LOCK = threading.Lock()


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(DEFAULT_TEMPLATE_DIR))
    app.secret_key = setup_secret_key()

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if database.verify_user(username, password):
                session["username"] = username
                return redirect(url_for("index"))
            return render_template("login.html", error="Identifiants incorrects.")
        return render_template("login.html", photo=random_feed_photo())

    # @app.route("/signup", methods=["GET", "POST"])
    # def signup():
    #     if request.method == "POST":
    #         username = request.form.get("username", "").strip()
    #         password = request.form.get("password", "")
    #         if not username or not password:
    #             return render_template(
    #                 "signup.html", error="Nom d'utilisateur et mot de passe requis."
    #             )
    #         if len(password) < 4:
    #             return render_template(
    #                 "signup.html", error="Mot de passe trop court (4 caractères minimum)."
    #             )
    #         if database.get_user(username):
    #             return render_template(
    #                 "signup.html", error="Ce nom d'utilisateur est déjà pris."
    #             )
    #         user_id = database.create_user(username, password)
    #         database.seed_default_files(user_id)
    #         session["username"] = username
    #         flash("Compte créé. Bienvenue !")
    #         return redirect(url_for("settings"))
    #     return render_template("signup.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        username = session.get("username")
        if not username:
            return redirect(url_for("login"))
        user = database.get_user(username)
        if user is None:
            session.clear()
            return redirect(url_for("login"))
        if database.latest_issue(user["id"]) is None:
            return _onboarding_page(user)
        day = request.args.get("day")
        page_html = render_issue(username, day)
        return render_template("reader.html", page_html=page_html)

    @app.route("/setup", methods=["POST"])
    def setup():
        username = session.get("username")
        if not username:
            return redirect(url_for("login"))
        user = database.get_user(username)
        if user is None:
            session.clear()
            return redirect(url_for("login"))
        if _is_pipeline_running(username):
            flash("Préparation de l'édition déjà en cours.")
            return redirect(url_for("index"))
        database.set_user_file(
            user["id"], "readers_interests.md", request.form.get("interests", "")
        )
        if not _save_feeds(user["id"], request.form.get("feeds_json", "")):
            flash("Erreur lors de l'enregistrement des flux RSS.")
            return redirect(url_for("index"))
        _start_onboarding_pipeline(username)
        return redirect(url_for("index"))

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

    @app.route("/settings/feeds.yml")
    def feeds_download():
        """Download the user's raw feeds.yml (keeps per-feed flags like today_only)."""
        username = session.get("username")
        if not username:
            abort(401)
        user = database.get_user(username)
        content = database.get_user_file(user["id"], "feeds.yml")
        if not content:
            abort(404)
        return send_file(
            io.BytesIO(content.encode("utf-8")),
            as_attachment=True,
            download_name="feeds.yml",
            mimetype="application/x-yaml",
        )

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
            elif action == "save_editorial_minutes":
                try:
                    minutes = int(request.form.get("editorial_minutes", "5"))
                except ValueError:
                    minutes = 5
                database.set_editorial_minutes(user["id"], minutes)
                flash("Durée de l'éditorial enregistrée.")
            elif action == "save_excluded_domains":
                domains = request.form.get("excluded_domains", "")
                database.set_excluded_domains(
                    user["id"], [d for d in domains.splitlines() if d.strip()]
                )
                flash("Domaines exclus enregistrés.")
            elif action == "save_filter_mode":
                mode = request.form.get("filter_mode", "24h")
                database.set_filter_mode(user["id"], mode)
                flash("Filtre des articles enregistré.")
            elif action == "upload_feeds":
                upload = request.files.get("feeds_file")
                if upload and upload.filename:
                    content = upload.stream.read().decode("utf-8", errors="replace")
                    flash(_upload_feeds(user["id"], content))
                else:
                    flash("Aucun fichier envoyé.")
            return redirect(url_for("settings"))

        publications = _load_feeds(user["id"])
        interests = database.get_user_file(user["id"], "readers_interests.md") or ""
        editorial_minutes = database.get_editorial_minutes(user["id"])
        excluded_domains = "\n".join(database.get_excluded_domains(user["id"]))
        filter_mode = database.get_filter_mode(user["id"])
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
            is_admin=database.user_is_admin(user),
            publications=publications,
            interests=interests,
            editorial_minutes=editorial_minutes,
            excluded_domains=excluded_domains,
            filter_mode=filter_mode,
            runs=runs,
        )

    @app.route("/admin")
    @require_admin
    def admin(user):
        """Admin panel: list users, add/remove accounts, browse pipeline data."""
        return render_template(
            "admin.html",
            username=user["username"],
            users=database.list_users_with_counts(),
        )

    @app.route("/admin/users", methods=["POST"])
    @require_admin
    def admin_add_user(user):
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Nom d'utilisateur et mot de passe requis.")
        elif len(password) < 4:
            flash("Mot de passe trop court (4 caractères minimum).")
        elif database.get_user(username):
            flash("Ce nom d'utilisateur est déjà pris.")
        else:
            user_id = database.create_user(username, password)
            database.seed_default_files(user_id)
            flash(f"Utilisateur « {username} » créé.")
        return redirect(url_for("admin"))

    @app.route("/admin/users/delete", methods=["POST"])
    @require_admin
    def admin_delete_user(user):
        username = request.form.get("username", "").strip()
        if username == user["username"]:
            flash("Impossible de supprimer votre propre compte.")
        elif database.delete_user(username):
            flash(f"Utilisateur « {username} » supprimé.")
        else:
            flash("Utilisateur inconnu.")
        return redirect(url_for("admin"))

    @app.route("/admin/data")
    @require_admin
    def admin_data(user):
        """Pipeline inspector: pick user + day, then display a stage's content."""
        users = database.list_users()
        selected_user = None
        if users:
            uid = request.args.get("user_id", type=int)
            selected_user = next((u for u in users if u["id"] == uid), users[0])

        issues = database.list_issues(selected_user["id"]) if selected_user else []
        selected_issue = None
        day_arg = request.args.get("day")
        for issue in issues:
            if issue["day"] == day_arg:
                selected_issue = issue
                break
        if selected_issue is None and issues:
            selected_issue = issues[0]

        run_at = _format_run_at(selected_issue) if selected_issue else None
        available_stages = _available_stages(selected_user, selected_issue)

        pipeline_version = _pipeline_version_of(selected_issue)
        pipeline = layout_pipeline_graph(pipeline_version)

        stage = request.args.get("stage")
        if stage not in ADMIN_STAGE_KEYS and stage != "readers":
            stage = "prepared_entries"
        content, is_audio = _pipeline_stage_content(
            selected_user, selected_issue, stage
        )
        news_tree = None
        if stage == "news_summary" and content is not None:
            news_tree = _news_summary_tree(content)

        entries = None
        entry_columns: list[str] = []
        visible_columns: set[str] | None = None
        if selected_issue is not None and stage == "prepared_entries":
            entries = database.get_prepared_entries(selected_issue["id"])
            if entries:
                seen: set[str] = set()
                for entry in entries:
                    for key in entry:
                        if key not in seen:
                            seen.add(key)
                            entry_columns.append(key)
                raw_cols = request.args.getlist("cols")
                if raw_cols:
                    visible_columns = {c for c in raw_cols if c in entry_columns}
                else:
                    visible_columns = set(DEFAULT_ENTRY_COLUMNS)

        return render_template(
            "admin_data.html",
            username=user["username"],
            users=users,
            selected_user=selected_user,
            issues=issues,
            day=selected_issue["day"] if selected_issue else None,
            run_at=run_at,
            pipeline_version=pipeline_version,
            pipeline=pipeline,
            available=available_stages,
            stage=stage,
            content=content,
            is_audio=is_audio,
            news_tree=news_tree,
            entries=entries,
            entry_columns=entry_columns,
            visible_columns=visible_columns,
        )

    @app.route("/admin/data/<int:user_id>/<day>/<stage>")
    @require_admin
    def admin_artifact(user, user_id, day, stage):
        """Stream a stored pipeline item: inline MP3 (or download) / raw text."""
        issue = database.get_issue(user_id, day)
        if issue is None:
            abort(404)
        content = database.get_artifact(issue["id"], stage)
        if content is None:
            abort(404)
        download = request.args.get("download") == "1"
        if stage == "editorial_mp3":
            return send_file(
                io.BytesIO(content),
                mimetype="audio/mpeg",
                as_attachment=download,
                download_name=f"{user_id}-{day}-editorial.mp3",
            )
        return send_file(io.BytesIO(content), mimetype="text/plain; charset=utf-8")

    _maybe_start_scheduler(app)

    return app


def require_admin(view):
    """Flask decorator: only a logged-in admin may call the view.

    The authenticated users row is passed as the first positional argument.
    Not logged in -> redirect to login; non-admin -> HTTP 403.
    """
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        username = session.get("username")
        if not username:
            return redirect(url_for("login"))
        user = database.get_user(username)
        if user is None:
            session.clear()
            return redirect(url_for("login"))
        if not database.user_is_admin(user):
            abort(403)
        return view(user, *args, **kwargs)
    return wrapped


def _maybe_start_scheduler(app: Flask) -> None:
    """Start the daily pipeline thread if config.yml enables it.

    Under Flask's debug reloader the module is executed twice (watcher + child);
    only the child (WERKZEUG_RUN_MAIN) should start the scheduler.
    """
    if not (SCHEDULE_ENABLED and SCHEDULE_USERS):
        return
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    hour, minute = schedule_clock()
    start_daily(list(SCHEDULE_USERS), hour, minute)


def _is_pipeline_running(username: str) -> bool:
    with _PIPELINE_LOCK:
        return username in _PIPELINE_RUNNING


def _start_onboarding_pipeline(username: str) -> None:
    """Run the pipeline for a user in a background thread, marking them running."""
    def work() -> None:
        try:
            run_for_user(username)
        except (SystemExit, Exception):
            logger.exception("Onboarding pipeline failed for '%s'", username)
        finally:
            with _PIPELINE_LOCK:
                _PIPELINE_RUNNING.discard(username)

    with _PIPELINE_LOCK:
        _PIPELINE_RUNNING.add(username)
    threading.Thread(target=work, name=f"onboarding-{username}", daemon=True).start()


def _onboarding_page(user) -> str:
    """Home page for a user who has no issue yet (onboarding or in-progress)."""
    username = user["username"]
    if _is_pipeline_running(username):
        return render_template("onboarding_running.html", username=username)
    return render_template(
        "onboarding.html",
        username=username,
        is_admin=database.user_is_admin(user),
        publications=_load_feeds(user["id"]),
        interests=(
            database.get_user_file(user["id"], "readers_interests.md")
            or _default_user_file("readers_interests.md")
            or ""
        ),
    )


def _default_user_file(name: str) -> str | None:
    """Return the data/ template for a user file (feeds.yml, readers_interests.md)."""
    path = DATA_DIR / name
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


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

    table_entries = database.get_prepared_entries(issue["id"])
    if table_entries:
        data: dict = {"entries": table_entries}
    else:
        prepared = database.get_artifact(issue["id"], "prepared_entries")
        parsed = database.get_artifact(issue["id"], "parsed_entries")
        raw = prepared or parsed
        if raw is None:
            return "<p>Aucune donnée pour cette édition. Lancez le pipeline.</p>"
        data = yaml.safe_load(raw)

    entries = data.get("entries", [])
    editorial, title = _issue_editorial(issue, data)

    generated_at = format_datetime_fr(_parse_run_at(issue))

    user_info = (
        f'<a class="top-bar-link" href="{url_for("settings")}">Paramètres</a>'
        + (f'<a class="top-bar-link" href="{url_for("admin")}">Admin</a>' if database.user_is_admin(user) else "")
        + f'<span class="top-bar-user">{html.escape(username)}</span>'
        + f'<a class="top-bar-logout" href="{url_for("logout")}">Déconnexion</a>'
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
        excluded_domains=set(database.get_excluded_domains(user["id"])),
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


def _issue_editorial(issue, prepared_data: dict) -> tuple[str | None, str | None]:
    """Return (editorial, title) for an issue, in its stored pipeline layout.

    pipeline_version 1 stores the editorial text + headline in their own
    artifact row; older pipelines kept them inside ``prepared_entries``.
    """
    try:
        version = int(issue["pipeline_version"] or 0)
    except (KeyError, IndexError, TypeError, ValueError):
        version = 0
    if version >= 1:
        blob = database.get_artifact(issue["id"], "editorial")
        if blob is not None:
            try:
                ed = yaml.safe_load(blob.decode("utf-8", errors="replace")) or {}
            except yaml.YAMLError:
                ed = {}
            if ed.get("editorial") is not None or ed.get("title") is not None:
                return ed.get("editorial"), ed.get("title")
    return prepared_data.get("editorial"), prepared_data.get("title")


ADMIN_STAGES = [
    {"key": "feeds", "label": "feeds.yml"},
    {"key": "filtered_entries", "label": "filtered_entries"},
    {"key": "parsed_entries", "label": "parsed_entries"},
    {"key": "news_summary", "label": "news_summary"},
    {"key": "prepared_entries", "label": "prepared_entries"},
    {"key": "editorial", "label": "editorial"},
    {"key": "editorial_mp3", "label": "editorial_mp3"},
]
ADMIN_STAGE_KEYS = {s["key"] for s in ADMIN_STAGES}

PIPELINE_GRAPH_V0 = {
    "nodes": [
        {"key": "feeds", "label": "feeds.yml"},
        {"key": "filtered_entries", "label": "filtered_entries"},
        {"key": "parsed_entries", "label": "parsed_entries"},
        {"key": "prepared_entries", "label": "prepared_entries"},
        {"key": "editorial_mp3", "label": "editorial_mp3"},
        {"key": "readers", "label": "readers_interests.md"},
    ],
    "edges": [
        {"from": "feeds", "to": "filtered_entries"},
        {"from": "filtered_entries", "to": "parsed_entries"},
        {"from": "parsed_entries", "to": "prepared_entries"},
        {"from": "prepared_entries", "to": "editorial_mp3"},
        {"from": "readers", "to": "parsed_entries"},
        {"from": "readers", "to": "prepared_entries"},
    ],
}

PIPELINE_GRAPH_V1 = {
    "nodes": [
        {"key": "feeds", "label": "feeds.yml"},
        {"key": "filtered_entries", "label": "filtered_entries"},
        {"key": "parsed_entries", "label": "parsed_entries"},
        {"key": "prepared_entries", "label": "prepared_entries"},
        {"key": "news_summary", "label": "news_summary"},
        {"key": "editorial", "label": "editorial"},
        {"key": "editorial_mp3", "label": "editorial_mp3"},
        {"key": "readers", "label": "readers_interests.md"},
    ],
    "edges": [
        {"from": "feeds", "to": "filtered_entries"},
        {"from": "filtered_entries", "to": "parsed_entries"},
        {"from": "prepared_entries", "to": "news_summary"},
        {"from": "news_summary", "to": "editorial"},
        {"from": "editorial", "to": "editorial_mp3"},
        {"from": "parsed_entries", "to": "prepared_entries"},
        {"from": "readers", "to": "parsed_entries"},
        {"from": "readers", "to": "news_summary"},
        {"from": "readers", "to": "editorial"},
        {"from": "readers", "to": "prepared_entries"},
    ],
}

PIPELINE_GRAPHS = {0: PIPELINE_GRAPH_V0, 1: PIPELINE_GRAPH_V1}

DEFAULT_ENTRY_COLUMNS = ("EID", "title", "source", "rerank_reason")

_FLOW_NODE_W = 140
_FLOW_NODE_H = 50
_FLOW_COL_GAP = 90
_FLOW_ROW_GAP = 32
_FLOW_PAD_X = 18
_FLOW_PAD_Y = 18


def layout_pipeline_graph(version: int) -> dict:
    """Lay the pipeline graph out left-to-right into SVG-ready geometry."""
    graph = PIPELINE_GRAPHS.get(version, PIPELINE_GRAPH_V1)
    node_keys = [n["key"] for n in graph["nodes"]]

    successors: dict[str, list[str]] = {}
    predecessors: dict[str, list[str]] = {}
    for key in node_keys:
        successors[key] = []
        predecessors[key] = []
    for edge in graph["edges"]:
        frm, to = edge["from"], edge["to"]
        if frm in successors and to in successors:
            successors[frm].append(to)
            predecessors[to].append(frm)

    depth: dict[str, int] = {}
    for key in node_keys:
        incoming = predecessors[key]
        if not incoming:
            depth[key] = 0
        else:
            depth[key] = 1 + max(depth[p] for p in incoming if p in depth)

    columns: dict[int, list[str]] = {}
    for key in node_keys:
        columns.setdefault(depth[key], []).append(key)

    node_geo: dict[str, dict] = {}
    for col, keys in columns.items():
        for row, key in enumerate(keys):
            x = _FLOW_PAD_X + col * (_FLOW_NODE_W + _FLOW_COL_GAP)
            y = _FLOW_PAD_Y + row * (_FLOW_NODE_H + _FLOW_ROW_GAP)
            node_geo[key] = {"x": x, "y": y, "w": _FLOW_NODE_W, "h": _FLOW_NODE_H}

    max_col = max(depth.values(), default=0)
    max_rows = max(len(keys) for keys in columns.values() or [[]])
    width = _FLOW_PAD_X * 2 + max_col * (_FLOW_NODE_W + _FLOW_COL_GAP) + _FLOW_NODE_W
    height = (
        _FLOW_PAD_Y * 2
        + (max_rows - 1) * (_FLOW_NODE_H + _FLOW_ROW_GAP)
        + _FLOW_NODE_H
    )

    nodes = []
    for n in graph["nodes"]:
        key = n["key"]
        geo = node_geo[key]
        nodes.append(
            {
                "key": key,
                "label": n["label"],
                "x": geo["x"],
                "y": geo["y"],
                "w": geo["w"],
                "h": geo["h"],
            }
        )

    edges = []
    for edge in graph["edges"]:
        frm, to = edge["from"], edge["to"]
        if frm not in node_geo or to not in node_geo:
            continue
        fg, tg = node_geo[frm], node_geo[to]
        sx, sy = fg["x"] + fg["w"], fg["y"] + fg["h"] // 2
        tx, ty = tg["x"], tg["y"] + tg["h"] // 2
        if sx == tx:
            d = f"M {sx} {sy} L {tx} {ty}"
        else:
            dx = max(24, (tx - sx) // 2)
            d = f"M {sx} {sy} C {sx + dx} {sy}, {tx - dx} {ty}, {tx} {ty}"
        edges.append({"d": d, "dashed": edge["from"] == "readers"})

    return {"width": width, "height": height, "nodes": nodes, "edges": edges}


def _format_run_at(issue) -> str:
    """Format an issue's run_at in French (fallback: raw value)."""
    try:
        return format_datetime_fr(_parse_run_at(issue))
    except ValueError:
        return issue["run_at"] or ""


def _available_stages(selected_user, selected_issue) -> set[str]:
    """The pipeline elements that have stored content for the selection."""
    available: set[str] = set()
    if selected_user is None:
        return available
    if database.get_user_file(selected_user["id"], "feeds.yml"):
        available.add("feeds")
    if database.get_user_file(selected_user["id"], "readers_interests.md"):
        available.add("readers")
    if selected_issue is not None:
        for artifact in database.list_artifacts(selected_issue["id"]):
            available.add(artifact["stage"])
        if database.count_prepared_entries(selected_issue["id"]):
            available.add("prepared_entries")
    return available


def _pipeline_version_of(issue) -> int:
    """Return the pipeline version of an issue (0 for legacy issues)."""
    if issue is None:
        return 0
    try:
        return int(issue["pipeline_version"] or 0)
    except (KeyError, IndexError, TypeError, ValueError):
        return 0


def _pipeline_stage_content(selected_user, selected_issue, stage: str):
    """Return (content, is_audio) for one pipeline element of the selection.

    ``content`` is decoded text, or raw MP3 bytes when ``is_audio`` is True.
    """
    if selected_user is None or selected_issue is None:
        return None, False
    if stage == "feeds":
        return database.get_user_file(selected_user["id"], "feeds.yml"), False
    if stage == "readers":
        return (
            database.get_user_file(selected_user["id"], "readers_interests.md"),
            False,
        )
    if stage == "prepared_entries":
        entries = database.get_prepared_entries(selected_issue["id"])
        if entries:
            payload = {"entries": entries}
            return yaml.safe_dump(
                payload, allow_unicode=True, sort_keys=False, default_flow_style=False
            ), False
    blob = database.get_artifact(selected_issue["id"], stage)
    if blob is None:
        return None, False
    if stage == "editorial_mp3":
        return blob, True
    return blob.decode("utf-8", errors="replace"), False


def _strip_code_fences(text: str | None) -> str:
    """Remove a surrounding ```...``` markdown fence if present."""
    if not text:
        return ""
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def _news_summary_tree(content: str | None) -> dict | list | None:
    """Parse stored news_summary text (possibly markdown-fenced) into a JSON-safe structure.

    Returns a dict/list for the tree view, or None if the content is empty or
    not object/array YAML (so the caller falls back to the raw <pre> display).
    """
    text = _strip_code_fences(content).strip()
    if not text:
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, (dict, list)):
        return None
    # Normalize anything YAML turned into a non-JSON type (e.g. date) to strings.
    return json.loads(json.dumps(data, default=str))


def random_feed_photo() -> dict | None:
    """Return a random photo (with caption) from any user's stored issue, or None.

    Scans the prepared (or parsed) entries stored for all users and picks one
    entry with a media image at random.
    """
    photos = []
    for user in database.list_users():
        for issue in database.list_issues(user["id"]):
            entries = database.get_prepared_entries(issue["id"])
            if not entries:
                raw = database.get_artifact(issue["id"], "prepared_entries")
                if raw is None:
                    raw = database.get_artifact(issue["id"], "parsed_entries")
                if raw is None:
                    continue
                try:
                    data = yaml.safe_load(raw)
                except yaml.YAMLError:
                    continue
                entries = data.get("entries", []) or []
            for entry in entries:
                media = entry.get("media")
                if not media:
                    continue
                photos.append(
                    {
                        "image": media,
                        "title": entry.get("title") or "",
                        "subtitle": entry.get("summary") or entry.get("title") or "",
                        "source": entry.get("source") or "",
                    }
                )
    if not photos:
        return None
    return random.choice(photos)


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
    if content is None:
        content = _default_user_file("feeds.yml")
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
                "today_only": bool(pub.get("today_only")),
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
        if pub.get("today_only"):
            entry["today_only"] = True
        publications.append(entry)
    yaml_text = yaml.safe_dump(
        {"publications": publications}, allow_unicode=True, sort_keys=False
    )
    database.set_user_file(user_id, "feeds.yml", yaml_text)
    return True


def _upload_feeds(user_id: int, content: str) -> str:
    """Validate an uploaded feeds.yml and store it. Returns a user-facing message."""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError:
        return "Fichier YAML invalide."
    pubs = data.get("publications") if isinstance(data, dict) else None
    if not isinstance(pubs, list):
        return "Le fichier doit contenir une liste « publications »."
    database.set_user_file(user_id, "feeds.yml", content)
    return "feeds.yml importé."


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