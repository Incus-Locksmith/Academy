import os
from datetime import datetime
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import (
    Flask,
    flash,
    redirect,
    render_template_string,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "change-this-before-production",
)

database_url = os.environ.get("DATABASE_URL", "sqlite:///locksmith_quiz.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = (
    int(os.environ.get("MAX_UPLOAD_MB", "100")) * 1024 * 1024
)

# Prefer a Render persistent disk when one is attached.
# If /var/data is not writable yet, fall back to temporary storage so the
# application can still deploy. Files in temporary storage will not survive
# a restart or redeploy.
preferred_upload_folder = Path(
    os.environ.get("UPLOAD_FOLDER", "/var/data/academy_uploads")
)

try:
    preferred_upload_folder.mkdir(parents=True, exist_ok=True)
    UPLOAD_FOLDER = preferred_upload_folder
except OSError:
    UPLOAD_FOLDER = Path("/tmp/academy_uploads")
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

db = SQLAlchemy(app)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")
PASS_MARK = int(os.environ.get("PASS_MARK", "80"))

ALLOWED_EXTENSIONS = {
    "pdf",
    "ppt",
    "pptx",
    "doc",
    "docx",
    "jpg",
    "jpeg",
    "png",
    "webp",
    "gif",
    "mp3",
    "mp4",
    "m4a",
    "wav",
}

RESOURCE_CATEGORIES = [
    ("presentation", "Presentation"),
    ("document", "Document"),
    ("sample_call", "Sample Call"),
    ("lock_image", "Lock Image"),
    ("other", "Other"),
]


# ---------------------------------------------------------------------------
# Database models
# ---------------------------------------------------------------------------

class Module(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)

    questions = db.relationship(
        "Question",
        backref="module",
        lazy=True,
        cascade="all, delete-orphan",
    )

    resources = db.relationship(
        "Resource",
        backref="module",
        lazy=True,
    )


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(
        db.Integer,
        db.ForeignKey("module.id"),
        nullable=False,
    )
    text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.Text, nullable=False)
    option_b = db.Column(db.Text, nullable=False)
    option_c = db.Column(db.Text, nullable=False)
    option_d = db.Column(db.Text, nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)
    explanation = db.Column(db.Text, nullable=False)


class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(120), nullable=False)
    student_email = db.Column(db.String(200), nullable=False)
    module_id = db.Column(
        db.Integer,
        db.ForeignKey("module.id"),
        nullable=False,
    )
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    percentage = db.Column(db.Integer, nullable=False)
    passed = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    module = db.relationship("Module")


class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    external_url = db.Column(db.Text, nullable=False, default="")
    stored_filename = db.Column(db.String(255), nullable=False, default="")
    original_filename = db.Column(db.String(255), nullable=False, default="")
    module_id = db.Column(
        db.Integer,
        db.ForeignKey("module.id"),
        nullable=True,
    )
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class GlossaryEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(150), nullable=False, unique=True)
    definition = db.Column(db.Text, nullable=False)
    example = db.Column(db.Text, nullable=False, default="")
    active = db.Column(db.Boolean, nullable=False, default=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class PriceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_type = db.Column(db.String(180), nullable=False)
    starting_price = db.Column(db.String(100), nullable=False)
    vat_note = db.Column(db.String(120), nullable=False, default="")
    eta = db.Column(db.String(120), nullable=False, default="")
    wording = db.Column(db.Text, nullable=False, default="")
    internal_notes = db.Column(db.Text, nullable=False, default="")
    active = db.Column(db.Boolean, nullable=False, default=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class JobType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    caller_wording = db.Column(db.Text, nullable=False, default="")
    questions_to_ask = db.Column(db.Text, nullable=False, default="")
    starting_price = db.Column(db.String(120), nullable=False, default="")
    eta = db.Column(db.String(120), nullable=False, default="")
    photos_needed = db.Column(db.String(120), nullable=False, default="")
    escalation = db.Column(db.Text, nullable=False, default="")
    services_not_offered = db.Column(db.Text, nullable=False, default="")
    booking_notes = db.Column(db.Text, nullable=False, default="")
    active = db.Column(db.Boolean, nullable=False, default=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


# ---------------------------------------------------------------------------
# Shared templates and helpers
# ---------------------------------------------------------------------------

BASE_HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ title }} | Locksmith Academy</title>
    <style>
        :root {
            --navy: #14283d;
            --blue: #27648a;
            --pale: #eef4f7;
            --green: #2e7d5b;
            --red: #a63d40;
            --gold: #d8a93b;
            --ink: #24313b;
            --border: #d7e0e5;
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            font-family: Arial, Helvetica, sans-serif;
            background: var(--pale);
            color: var(--ink);
            line-height: 1.5;
        }

        header {
            background: var(--navy);
            color: white;
            padding: 18px 24px;
        }

        header .wrap {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 18px;
        }

        header a {
            color: white;
            text-decoration: none;
        }

        .brand {
            font-size: 1.25rem;
            font-weight: 700;
        }

        nav a {
            margin-left: 16px;
            font-size: .95rem;
        }

        .wrap {
            max-width: 1160px;
            margin: 0 auto;
        }

        main {
            padding: 32px 20px 60px;
        }

        .hero {
            background: white;
            border-radius: 16px;
            padding: 34px;
            box-shadow: 0 8px 26px rgba(20,40,61,.08);
            margin-bottom: 24px;
        }

        h1, h2, h3 {
            color: var(--navy);
            line-height: 1.2;
        }

        h1 {
            margin-top: 0;
            font-size: 2rem;
        }

        .muted { color: #65727c; }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 18px;
        }

        .card {
            background: white;
            border-radius: 14px;
            padding: 22px;
            box-shadow: 0 6px 20px rgba(20,40,61,.07);
        }

        .module-number,
        .category-pill {
            display: inline-block;
            background: var(--navy);
            color: white;
            border-radius: 999px;
            padding: 5px 10px;
            font-size: .8rem;
            margin-bottom: 10px;
        }

        .category-pill {
            background: var(--blue);
        }

        label {
            display: block;
            font-weight: 700;
            margin: 14px 0 6px;
        }

        input[type=text],
        input[type=email],
        input[type=password],
        input[type=number],
        input[type=url],
        input[type=file],
        textarea,
        select {
            width: 100%;
            padding: 12px;
            border: 1px solid #c7d2d9;
            border-radius: 8px;
            font-size: 1rem;
            font-family: inherit;
            background: white;
        }

        textarea {
            min-height: 105px;
            resize: vertical;
        }

        .btn {
            display: inline-block;
            border: 0;
            border-radius: 9px;
            background: var(--blue);
            color: white;
            padding: 12px 18px;
            font-weight: 700;
            text-decoration: none;
            cursor: pointer;
            margin-top: 14px;
        }

        .btn.secondary { background: var(--navy); }
        .btn.light { background: #dce8ee; color: var(--navy); }
        .btn.danger { background: var(--red); }

        .btn.small {
            padding: 8px 12px;
            font-size: .9rem;
            margin-top: 0;
        }

        .actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            align-items: center;
        }

        .question {
            background: white;
            border-radius: 14px;
            padding: 22px;
            margin-bottom: 18px;
            box-shadow: 0 5px 18px rgba(20,40,61,.06);
        }

        .option {
            display: block;
            border: 1px solid #d4dde2;
            border-radius: 9px;
            padding: 11px 12px;
            margin: 9px 0;
            font-weight: 400;
            cursor: pointer;
        }

        .option:hover { background: #f5f8fa; }

        .alert {
            background: #fff6d9;
            border-left: 5px solid var(--gold);
            padding: 12px 15px;
            margin-bottom: 18px;
            border-radius: 7px;
        }

        .result {
            text-align: center;
            padding: 34px;
        }

        .score {
            font-size: 3rem;
            font-weight: 800;
            color: var(--navy);
            margin: 8px 0;
        }

        .pass { color: var(--green); font-weight: 700; }
        .fail { color: var(--red); font-weight: 700; }

        .review {
            background: white;
            border-radius: 12px;
            padding: 18px;
            margin: 12px 0;
        }

        .correct { border-left: 5px solid var(--green); }
        .incorrect { border-left: 5px solid var(--red); }

        table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 12px;
            overflow: hidden;
        }

        th, td {
            text-align: left;
            padding: 12px;
            border-bottom: 1px solid #e5ecef;
            vertical-align: top;
        }

        th {
            background: var(--navy);
            color: white;
        }

        .pill {
            display: inline-block;
            padding: 4px 9px;
            border-radius: 999px;
            font-size: .82rem;
            font-weight: 700;
        }

        .pill.pass { background: #dff3e8; }
        .pill.fail { background: #f7dddd; }

        .admin-tabs {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 22px;
        }

        .admin-tabs a {
            background: white;
            color: var(--navy);
            border: 1px solid var(--border);
            border-radius: 9px;
            padding: 10px 14px;
            text-decoration: none;
            font-weight: 700;
        }

        .admin-tabs a.active {
            background: var(--navy);
            color: white;
        }

        .resource-media {
            width: 100%;
            max-height: 360px;
            border-radius: 10px;
            background: #111;
        }

        .resource-image {
            width: 100%;
            max-height: 340px;
            object-fit: contain;
            border-radius: 10px;
            background: #f5f7f8;
        }

        .searchbar {
            display: grid;
            grid-template-columns: 1fr 220px auto;
            gap: 10px;
            align-items: end;
        }

        .detail-list dt {
            font-weight: 700;
            color: var(--navy);
            margin-top: 10px;
        }

        .detail-list dd {
            margin: 2px 0 0;
            white-space: pre-line;
        }

        footer {
            color: #6e7a83;
            text-align: center;
            padding: 24px;
            font-size: .9rem;
        }

        @media (max-width: 760px) {
            header .wrap { display: block; }
            nav { margin-top: 10px; }
            nav a { margin: 0 12px 0 0; }
            .hero { padding: 24px; }
            .searchbar { grid-template-columns: 1fr; }
            table { font-size: .88rem; }
            th, td { padding: 8px; }
        }
    </style>
</head>

<body>
<header>
    <div class="wrap">
        <a class="brand" href="{{ url_for('home') }}">
            Locksmith Call Handler Academy
        </a>

        <nav>
            <a href="{{ url_for('home') }}">Student Area</a>
            <a href="{{ url_for('library_home') }}">Resource Library</a>
            <a href="{{ url_for('admin_login') }}">Manager Area</a>
        </nav>
    </div>
</header>

<main class="wrap">
    {% with messages = get_flashed_messages() %}
        {% if messages %}
            {% for message in messages %}
                <div class="alert">{{ message }}</div>
            {% endfor %}
        {% endif %}
    {% endwith %}

    {{ content|safe }}
</main>

<footer>
    Training supports live-call readiness. Final approval remains with the trainer or manager.
</footer>
</body>
</html>
"""


ADMIN_TABS = """
<div class="admin-tabs">
    <a class="{{ 'active' if active_tab == 'results' else '' }}"
       href="{{ url_for('admin_dashboard') }}">Student Results</a>

    <a class="{{ 'active' if active_tab == 'questions' else '' }}"
       href="{{ url_for('admin_questions') }}">Manage Questions</a>

    <a class="{{ 'active' if active_tab == 'modules' else '' }}"
       href="{{ url_for('admin_modules') }}">Manage Modules</a>

    <a class="{{ 'active' if active_tab == 'resources' else '' }}"
       href="{{ url_for('admin_resources') }}">Manage Resources</a>

    <a class="{{ 'active' if active_tab == 'glossary' else '' }}"
       href="{{ url_for('admin_glossary') }}">Glossary</a>

    <a class="{{ 'active' if active_tab == 'prices' else '' }}"
       href="{{ url_for('admin_prices') }}">Price List</a>

    <a class="{{ 'active' if active_tab == 'jobtypes' else '' }}"
       href="{{ url_for('admin_job_types') }}">Job Types</a>

    <a href="{{ url_for('admin_logout') }}">Log out</a>
</div>
"""


def page(title, content, **context):
    body = render_template_string(content, **context)
    return render_template_string(
        BASE_HTML,
        title=title,
        content=body,
    )


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def save_uploaded_file(file_obj):
    if not file_obj or not file_obj.filename:
        return "", ""

    if not allowed_file(file_obj.filename):
        raise ValueError("That file type is not supported.")

    original = secure_filename(file_obj.filename)
    extension = original.rsplit(".", 1)[1].lower()
    stored = f"{uuid4().hex}.{extension}"
    file_obj.save(UPLOAD_FOLDER / stored)

    return stored, original


def delete_stored_file(stored_filename):
    if not stored_filename:
        return

    path = UPLOAD_FOLDER / stored_filename
    if path.exists() and path.is_file():
        path.unlink()


def get_resource_url(resource):
    if resource.stored_filename:
        return url_for(
            "uploaded_file",
            filename=resource.stored_filename,
        )

    return resource.external_url


@app.errorhandler(413)
def upload_too_large(_error):
    flash(
        "The uploaded file is too large. "
        "Increase MAX_UPLOAD_MB in Render or use a smaller file."
    )
    return redirect(request.referrer or url_for("admin_resources"))


# ---------------------------------------------------------------------------
# Student quiz routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET", "POST"])
def home():
    modules = Module.query.order_by(Module.position, Module.id).all()

    if request.method == "POST":
        name = request.form.get("student_name", "").strip()
        email = request.form.get("student_email", "").strip().lower()

        if not name or not email:
            flash("Please enter both your name and email address.")
        else:
            session["student_name"] = name
            session["student_email"] = email
            return redirect(url_for("modules"))

    content = """
    <section class="hero">
        <h1>From novice to ready for supported live calls</h1>

        <p>
            This Academy combines quizzes with presentations, sample calls,
            lock images, terminology, pricing and job guidance.
        </p>

        <a class="btn secondary" href="{{ url_for('library_home') }}">
            Open Resource Library
        </a>

        <hr style="margin:28px 0;border:0;border-top:1px solid #e1e8eb;">

        <form method="post">
            <label for="student_name">Full name</label>
            <input
                id="student_name"
                name="student_name"
                type="text"
                value="{{ session.get('student_name', '') }}"
                required
            >

            <label for="student_email">Email address</label>
            <input
                id="student_email"
                name="student_email"
                type="email"
                value="{{ session.get('student_email', '') }}"
                required
            >

            <button class="btn" type="submit">
                Start training assessment
            </button>
        </form>
    </section>

    <div class="grid">
        {% for module in modules %}
            <article class="card">
                <span class="module-number">
                    Module {{ module.position }}
                </span>

                <h3>{{ module.title }}</h3>
                <p>{{ module.description }}</p>
                <p class="muted">{{ module.questions|length }} questions</p>
            </article>
        {% endfor %}
    </div>
    """

    return page(
        "Welcome",
        content,
        modules=modules,
        session=session,
    )


@app.route("/modules")
def modules():
    if not session.get("student_name"):
        flash("Enter your details before starting.")
        return redirect(url_for("home"))

    module_list = Module.query.order_by(Module.position, Module.id).all()

    attempts = Attempt.query.filter_by(
        student_email=session["student_email"],
    ).order_by(Attempt.created_at.desc()).all()

    latest_by_module = {}
    for attempt in attempts:
        latest_by_module.setdefault(attempt.module_id, attempt)

    content = """
    <section class="hero">
        <h1>Welcome, {{ session['student_name'] }}</h1>
        <p>Select a module below. The pass mark is {{ pass_mark }}%.</p>

        <div class="actions">
            <a class="btn light" href="{{ url_for('change_student') }}">
                Change student
            </a>

            <a class="btn secondary" href="{{ url_for('library_home') }}">
                Open Resource Library
            </a>
        </div>
    </section>

    <div class="grid">
        {% for module in modules %}
            <article class="card">
                <span class="module-number">
                    Module {{ module.position }}
                </span>

                <h3>{{ module.title }}</h3>
                <p>{{ module.description }}</p>

                {% if module.questions|length == 0 %}
                    <p class="muted">
                        This module does not yet contain any questions.
                    </p>
                {% elif module.id in latest %}
                    {% set result = latest[module.id] %}
                    <p>
                        Latest result:
                        <span class="pill {{ 'pass' if result.passed else 'fail' }}">
                            {{ result.percentage }}% —
                            {{ 'Passed' if result.passed else 'Review needed' }}
                        </span>
                    </p>
                {% else %}
                    <p class="muted">Not attempted yet</p>
                {% endif %}

                {% if module.questions|length > 0 %}
                    <a
                        class="btn"
                        href="{{ url_for('take_quiz', module_id=module.id) }}"
                    >
                        {{ 'Retake module' if module.id in latest else 'Start module' }}
                    </a>
                {% endif %}
            </article>
        {% endfor %}
    </div>
    """

    return page(
        "Modules",
        content,
        modules=module_list,
        latest=latest_by_module,
        pass_mark=PASS_MARK,
        session=session,
    )


@app.route("/change-student")
def change_student():
    session.pop("student_name", None)
    session.pop("student_email", None)
    return redirect(url_for("home"))


@app.route("/quiz/<int:module_id>", methods=["GET", "POST"])
def take_quiz(module_id):
    if not session.get("student_name"):
        flash("Enter your details before starting.")
        return redirect(url_for("home"))

    module = db.session.get(Module, module_id)

    if not module:
        flash("That module could not be found.")
        return redirect(url_for("modules"))

    questions = Question.query.filter_by(
        module_id=module.id,
    ).order_by(Question.id).all()

    if not questions:
        flash("This module does not contain any questions yet.")
        return redirect(url_for("modules"))

    if request.method == "POST":
        score = 0
        review = []

        for question in questions:
            selected = request.form.get(
                f"question_{question.id}",
                "",
            )

            correct = selected == question.correct_option
            if correct:
                score += 1

            options = {
                "A": question.option_a,
                "B": question.option_b,
                "C": question.option_c,
                "D": question.option_d,
            }

            review.append(
                {
                    "question": question,
                    "selected_text": options.get(
                        selected,
                        "No answer selected",
                    ),
                    "correct_text": options[question.correct_option],
                    "correct": correct,
                }
            )

        total = len(questions)
        percentage = round((score / total) * 100) if total else 0
        passed = percentage >= PASS_MARK

        attempt = Attempt(
            student_name=session["student_name"],
            student_email=session["student_email"],
            module_id=module.id,
            score=score,
            total=total,
            percentage=percentage,
            passed=passed,
        )

        db.session.add(attempt)
        db.session.commit()

        result_content = """
        <section class="hero result">
            <h1>{{ module.title }}</h1>
            <div class="score">{{ percentage }}%</div>

            <p class="{{ 'pass' if passed else 'fail' }}">
                {{ 'Passed' if passed else 'Review needed' }}
            </p>

            <p>
                You answered {{ score }} of {{ total }} questions correctly.
            </p>

            <a class="btn" href="{{ url_for('modules') }}">
                Return to modules
            </a>

            <a
                class="btn secondary"
                href="{{ url_for('take_quiz', module_id=module.id) }}"
            >
                Retake
            </a>
        </section>

        <h2>Answer review</h2>

        {% for item in review %}
            <div class="review {{ 'correct' if item.correct else 'incorrect' }}">
                <h3>{{ loop.index }}. {{ item.question.text }}</h3>

                <p>
                    <strong>Your answer:</strong>
                    {{ item.selected_text }}
                </p>

                {% if not item.correct %}
                    <p>
                        <strong>Correct answer:</strong>
                        {{ item.correct_text }}
                    </p>
                {% endif %}

                <p class="muted">
                    {{ item.question.explanation }}
                </p>
            </div>
        {% endfor %}
        """

        return page(
            "Results",
            result_content,
            module=module,
            percentage=percentage,
            passed=passed,
            score=score,
            total=total,
            review=review,
        )

    quiz_content = """
    <section class="hero">
        <span class="module-number">
            Module {{ module.position }}
        </span>

        <h1>{{ module.title }}</h1>
        <p>{{ module.description }}</p>
    </section>

    <form method="post">
        {% for question in questions %}
            <section class="question">
                <h3>{{ loop.index }}. {{ question.text }}</h3>

                {% for letter, option in [
                    ('A', question.option_a),
                    ('B', question.option_b),
                    ('C', question.option_c),
                    ('D', question.option_d)
                ] %}
                    <label class="option">
                        <input
                            type="radio"
                            name="question_{{ question.id }}"
                            value="{{ letter }}"
                            required
                        >
                        <strong>{{ letter }}.</strong>
                        {{ option }}
                    </label>
                {% endfor %}
            </section>
        {% endfor %}

        <button class="btn" type="submit">
            Submit assessment
        </button>
    </form>
    """

    return page(
        "Quiz",
        quiz_content,
        module=module,
        questions=questions,
    )


# ---------------------------------------------------------------------------
# Student Resource Library
# ---------------------------------------------------------------------------

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(
        UPLOAD_FOLDER,
        filename,
        as_attachment=False,
    )


@app.route("/library")
def library_home():
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    resources_query = Resource.query.filter_by(active=True)

    if query:
        like = f"%{query}%"
        resources_query = resources_query.filter(
            or_(
                Resource.title.ilike(like),
                Resource.description.ilike(like),
            )
        )

    if category:
        resources_query = resources_query.filter_by(
            category=category,
        )

    resources = resources_query.order_by(
        Resource.category,
        Resource.title,
    ).all()

    glossary_count = GlossaryEntry.query.filter_by(active=True).count()
    price_count = PriceItem.query.filter_by(active=True).count()
    job_type_count = JobType.query.filter_by(active=True).count()

    content = """
    <section class="hero">
        <h1>Resource Library</h1>

        <p>
            Search presentations, documents, sample calls and lock images,
            or open the glossary, price list and job-type guide.
        </p>

        <form method="get" class="searchbar">
            <div>
                <label for="q">Search</label>
                <input
                    id="q"
                    name="q"
                    type="text"
                    value="{{ query }}"
                    placeholder="Try: euro cylinder, locked out, pricing"
                >
            </div>

            <div>
                <label for="category">Category</label>
                <select id="category" name="category">
                    <option value="">All categories</option>

                    {% for value, label in categories %}
                        <option
                            value="{{ value }}"
                            {% if category == value %}selected{% endif %}
                        >
                            {{ label }}
                        </option>
                    {% endfor %}
                </select>
            </div>

            <button class="btn" type="submit">
                Search
            </button>
        </form>
    </section>

    <div class="grid" style="margin-bottom:24px;">
        <a
            class="card"
            href="{{ url_for('glossary') }}"
            style="text-decoration:none;color:inherit;"
        >
            <h3>Glossary</h3>
            <p>Search terms, meanings and examples.</p>
            <p class="muted">{{ glossary_count }} active entries</p>
        </a>

        <a
            class="card"
            href="{{ url_for('price_list') }}"
            style="text-decoration:none;color:inherit;"
        >
            <h3>Price List</h3>
            <p>Current starting prices and approved wording.</p>
            <p class="muted">{{ price_count }} active prices</p>
        </a>

        <a
            class="card"
            href="{{ url_for('job_types') }}"
            style="text-decoration:none;color:inherit;"
        >
            <h3>Job Types</h3>
            <p>What to ask, what to record and when to escalate.</p>
            <p class="muted">{{ job_type_count }} active job types</p>
        </a>
    </div>

    <h2>Library resources</h2>

    {% if resources %}
        <div class="grid">
            {% for resource in resources %}
                <article class="card">
                    <span class="category-pill">
                        {{ category_labels.get(
                            resource.category,
                            resource.category
                        ) }}
                    </span>

                    <h3>{{ resource.title }}</h3>

                    {% if resource.module %}
                        <p class="muted">
                            Module {{ resource.module.position }} —
                            {{ resource.module.title }}
                        </p>
                    {% endif %}

                    <p>{{ resource.description }}</p>

                    <a
                        class="btn"
                        href="{{ url_for(
                            'resource_detail',
                            resource_id=resource.id
                        ) }}"
                    >
                        Open resource
                    </a>
                </article>
            {% endfor %}
        </div>
    {% else %}
        <div class="card">
            <p>No matching resources were found.</p>
        </div>
    {% endif %}
    """

    return page(
        "Resource Library",
        content,
        resources=resources,
        query=query,
        category=category,
        categories=RESOURCE_CATEGORIES,
        category_labels=dict(RESOURCE_CATEGORIES),
        glossary_count=glossary_count,
        price_count=price_count,
        job_type_count=job_type_count,
    )


@app.route("/library/resource/<int:resource_id>")
def resource_detail(resource_id):
    resource = db.session.get(Resource, resource_id)

    if not resource or not resource.active:
        flash("That resource could not be found.")
        return redirect(url_for("library_home"))

    file_url = get_resource_url(resource)
    extension = ""

    source_name = resource.original_filename or resource.external_url
    if "." in source_name:
        extension = (
            source_name.rsplit(".", 1)[1]
            .lower()
            .split("?")[0]
        )

    content = """
    <section class="hero">
        <span class="category-pill">
            {{ category_labels.get(
                resource.category,
                resource.category
            ) }}
        </span>

        <h1>{{ resource.title }}</h1>

        {% if resource.module %}
            <p class="muted">
                Module {{ resource.module.position }} —
                {{ resource.module.title }}
            </p>
        {% endif %}

        <p>{{ resource.description }}</p>

        {% if file_url %}
            {% if extension in ['mp3', 'm4a', 'wav'] %}
                <audio controls class="resource-media">
                    <source src="{{ file_url }}">
                    Your browser does not support audio playback.
                </audio>

            {% elif extension == 'mp4' %}
                <video controls class="resource-media">
                    <source src="{{ file_url }}">
                    Your browser does not support video playback.
                </video>

            {% elif extension in ['jpg', 'jpeg', 'png', 'webp', 'gif'] %}
                <img
                    class="resource-image"
                    src="{{ file_url }}"
                    alt="{{ resource.title }}"
                >

            {% else %}
                <a
                    class="btn"
                    href="{{ file_url }}"
                    target="_blank"
                    rel="noopener"
                >
                    Open or download file
                </a>
            {% endif %}
        {% else %}
            <div class="alert">
                No file or external link has been added yet.
            </div>
        {% endif %}

        <div class="actions">
            <a
                class="btn light"
                href="{{ url_for('library_home') }}"
            >
                Back to library
            </a>
        </div>
    </section>
    """

    return page(
        resource.title,
        content,
        resource=resource,
        file_url=file_url,
        extension=extension,
        category_labels=dict(RESOURCE_CATEGORIES),
    )


@app.route("/glossary")
def glossary():
    query = request.args.get("q", "").strip()
    entries_query = GlossaryEntry.query.filter_by(active=True)

    if query:
        like = f"%{query}%"
        entries_query = entries_query.filter(
            or_(
                GlossaryEntry.term.ilike(like),
                GlossaryEntry.definition.ilike(like),
                GlossaryEntry.example.ilike(like),
            )
        )

    entries = entries_query.order_by(
        GlossaryEntry.term,
    ).all()

    content = """
    <section class="hero">
        <h1>Glossary</h1>

        <form method="get">
            <label for="q">Search terms</label>
            <input
                id="q"
                name="q"
                type="text"
                value="{{ query }}"
                placeholder="Try: locked in, recall, fresh installation"
            >

            <button class="btn" type="submit">
                Search
            </button>
        </form>
    </section>

    {% for entry in entries %}
        <article class="card" style="margin-bottom:16px;">
            <h2>{{ entry.term }}</h2>
            <p>{{ entry.definition }}</p>

            {% if entry.example %}
                <p class="muted">
                    <strong>Example:</strong>
                    {{ entry.example }}
                </p>
            {% endif %}
        </article>
    {% else %}
        <div class="card">
            <p>No matching glossary entries were found.</p>
        </div>
    {% endfor %}
    """

    return page(
        "Glossary",
        content,
        entries=entries,
        query=query,
    )


@app.route("/prices")
def price_list():
    prices = PriceItem.query.filter_by(active=True).order_by(
        PriceItem.job_type,
    ).all()

    content = """
    <section class="hero">
        <h1>Current Price List</h1>
        <p>
            Use the approved starting-price wording.
            Final cost may depend on assessment and work required.
        </p>
    </section>

    {% if prices %}
        <div style="overflow-x:auto">
            <table>
                <thead>
                    <tr>
                        <th>Job type</th>
                        <th>Starting price</th>
                        <th>VAT</th>
                        <th>ETA</th>
                        <th>Approved wording</th>
                    </tr>
                </thead>

                <tbody>
                    {% for item in prices %}
                        <tr>
                            <td><strong>{{ item.job_type }}</strong></td>
                            <td>{{ item.starting_price }}</td>
                            <td>{{ item.vat_note }}</td>
                            <td>{{ item.eta }}</td>
                            <td>{{ item.wording }}</td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    {% else %}
        <div class="card">
            <p>No active prices have been added yet.</p>
        </div>
    {% endif %}
    """

    return page(
        "Price List",
        content,
        prices=prices,
    )


@app.route("/job-types")
def job_types():
    items = JobType.query.filter_by(active=True).order_by(
        JobType.title,
    ).all()

    content = """
    <section class="hero">
        <h1>Job Type Guide</h1>
        <p>
            Open a job type to see caller wording, questions,
            pricing guidance, escalation rules and booking notes.
        </p>
    </section>

    <div class="grid">
        {% for item in items %}
            <article class="card">
                <h3>{{ item.title }}</h3>
                <p>{{ item.description }}</p>

                {% if item.starting_price %}
                    <p>
                        <strong>Starting price:</strong>
                        {{ item.starting_price }}
                    </p>
                {% endif %}

                <a
                    class="btn"
                    href="{{ url_for(
                        'job_type_detail',
                        job_type_id=item.id
                    ) }}"
                >
                    Open guide
                </a>
            </article>
        {% else %}
            <div class="card">
                <p>No job types have been added yet.</p>
            </div>
        {% endfor %}
    </div>
    """

    return page(
        "Job Types",
        content,
        items=items,
    )


@app.route("/job-types/<int:job_type_id>")
def job_type_detail(job_type_id):
    item = db.session.get(JobType, job_type_id)

    if not item or not item.active:
        flash("That job type could not be found.")
        return redirect(url_for("job_types"))

    content = """
    <section class="hero">
        <h1>{{ item.title }}</h1>
        <p>{{ item.description }}</p>

        <dl class="detail-list">
            {% if item.caller_wording %}
                <dt>What callers may say</dt>
                <dd>{{ item.caller_wording }}</dd>
            {% endif %}

            {% if item.questions_to_ask %}
                <dt>Questions to ask</dt>
                <dd>{{ item.questions_to_ask }}</dd>
            {% endif %}

            {% if item.starting_price %}
                <dt>Starting price</dt>
                <dd>{{ item.starting_price }}</dd>
            {% endif %}

            {% if item.eta %}
                <dt>ETA guidance</dt>
                <dd>{{ item.eta }}</dd>
            {% endif %}

            {% if item.photos_needed %}
                <dt>Are photos needed?</dt>
                <dd>{{ item.photos_needed }}</dd>
            {% endif %}

            {% if item.escalation %}
                <dt>Escalation</dt>
                <dd>{{ item.escalation }}</dd>
            {% endif %}

            {% if item.services_not_offered %}
                <dt>Services not offered</dt>
                <dd>{{ item.services_not_offered }}</dd>
            {% endif %}

            {% if item.booking_notes %}
                <dt>Example booking notes</dt>
                <dd>{{ item.booking_notes }}</dd>
            {% endif %}
        </dl>

        <a
            class="btn light"
            href="{{ url_for('job_types') }}"
        >
            Back to job types
        </a>
    </section>
    """

    return page(
        item.title,
        content,
        item=item,
    )


# ---------------------------------------------------------------------------
# Manager login and dashboard
# ---------------------------------------------------------------------------

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        password = request.form.get("password", "")

        if password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))

        flash("Incorrect manager password.")

    content = """
    <section class="hero">
        <h1>Manager access</h1>

        <form method="post">
            <label for="password">Password</label>

            <input
                id="password"
                name="password"
                type="password"
                required
            >

            <button class="btn" type="submit">
                Open manager area
            </button>
        </form>
    </section>
    """

    return page(
        "Manager Login",
        content,
    )


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    attempts = Attempt.query.order_by(
        Attempt.created_at.desc(),
    ).all()

    total_attempts = len(attempts)

    unique_students = db.session.query(
        func.count(func.distinct(Attempt.student_email))
    ).scalar() or 0

    passes = sum(
        1
        for attempt in attempts
        if attempt.passed
    )

    pass_rate = (
        round((passes / total_attempts) * 100)
        if total_attempts
        else 0
    )

    content = ADMIN_TABS + """
    <section class="hero">
        <h1>Student results</h1>

        <div class="grid">
            <div class="card">
                <h3>{{ unique_students }}</h3>
                <p>Students</p>
            </div>

            <div class="card">
                <h3>{{ total_attempts }}</h3>
                <p>Total attempts</p>
            </div>

            <div class="card">
                <h3>{{ pass_rate }}%</h3>
                <p>Attempt pass rate</p>
            </div>
        </div>
    </section>

    {% if attempts %}
        <div style="overflow-x:auto">
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Student</th>
                        <th>Email</th>
                        <th>Module</th>
                        <th>Score</th>
                        <th>Result</th>
                    </tr>
                </thead>

                <tbody>
                    {% for attempt in attempts %}
                        <tr>
                            <td>
                                {{ attempt.created_at.strftime(
                                    '%d %b %Y %H:%M'
                                ) }}
                            </td>
                            <td>{{ attempt.student_name }}</td>
                            <td>{{ attempt.student_email }}</td>
                            <td>{{ attempt.module.title }}</td>
                            <td>
                                {{ attempt.score }}/{{ attempt.total }}
                                ({{ attempt.percentage }}%)
                            </td>
                            <td>
                                <span class="pill {{ 'pass' if attempt.passed else 'fail' }}">
                                    {{ 'Passed' if attempt.passed else 'Review needed' }}
                                </span>
                            </td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    {% else %}
        <div class="card">
            <p>No student attempts have been recorded yet.</p>
        </div>
    {% endif %}
    """

    return page(
        "Manager Dashboard",
        content,
        attempts=attempts,
        unique_students=unique_students,
        total_attempts=total_attempts,
        pass_rate=pass_rate,
        active_tab="results",
    )


# ---------------------------------------------------------------------------
# Question manager
# ---------------------------------------------------------------------------

QUESTION_FORM = """
{{ admin_tabs|safe }}

<section class="hero">
    <h1>{{ heading }}</h1>

    <form method="post">
        <label for="module_id">Module</label>
        <select id="module_id" name="module_id" required>
            <option value="">Choose a module</option>

            {% for module in modules %}
                <option
                    value="{{ module.id }}"
                    {% if values.module_id|string == module.id|string %}
                        selected
                    {% endif %}
                >
                    Module {{ module.position }} — {{ module.title }}
                </option>
            {% endfor %}
        </select>

        <label for="text">Question</label>
        <textarea id="text" name="text" required>{{ values.text }}</textarea>

        <label for="option_a">Answer A</label>
        <textarea id="option_a" name="option_a" required>{{ values.option_a }}</textarea>

        <label for="option_b">Answer B</label>
        <textarea id="option_b" name="option_b" required>{{ values.option_b }}</textarea>

        <label for="option_c">Answer C</label>
        <textarea id="option_c" name="option_c" required>{{ values.option_c }}</textarea>

        <label for="option_d">Answer D</label>
        <textarea id="option_d" name="option_d" required>{{ values.option_d }}</textarea>

        <label for="correct_option">Correct answer</label>
        <select
            id="correct_option"
            name="correct_option"
            required
        >
            <option value="">Choose</option>

            {% for letter in ['A', 'B', 'C', 'D'] %}
                <option
                    value="{{ letter }}"
                    {% if values.correct_option == letter %}
                        selected
                    {% endif %}
                >
                    {{ letter }}
                </option>
            {% endfor %}
        </select>

        <label for="explanation">Explanation</label>
        <textarea
            id="explanation"
            name="explanation"
            required
        >{{ values.explanation }}</textarea>

        <button class="btn" type="submit">
            {{ submit_label }}
        </button>
    </form>
</section>
"""


def question_form_values(question=None):
    if request.method == "POST":
        return {
            "module_id": request.form.get("module_id", "").strip(),
            "text": request.form.get("text", "").strip(),
            "option_a": request.form.get("option_a", "").strip(),
            "option_b": request.form.get("option_b", "").strip(),
            "option_c": request.form.get("option_c", "").strip(),
            "option_d": request.form.get("option_d", "").strip(),
            "correct_option": request.form.get(
                "correct_option",
                "",
            ).strip().upper(),
            "explanation": request.form.get(
                "explanation",
                "",
            ).strip(),
        }

    if question:
        return {
            "module_id": str(question.module_id),
            "text": question.text,
            "option_a": question.option_a,
            "option_b": question.option_b,
            "option_c": question.option_c,
            "option_d": question.option_d,
            "correct_option": question.correct_option,
            "explanation": question.explanation,
        }

    return {
        "module_id": "",
        "text": "",
        "option_a": "",
        "option_b": "",
        "option_c": "",
        "option_d": "",
        "correct_option": "",
        "explanation": "",
    }


@app.route("/admin/questions")
@admin_required
def admin_questions():
    modules = Module.query.order_by(
        Module.position,
        Module.id,
    ).all()

    content = ADMIN_TABS + """
    <section class="hero">
        <h1>Manage questions</h1>

        <a
            class="btn"
            href="{{ url_for('admin_add_question') }}"
        >
            Add new question
        </a>
    </section>

    {% for module in modules %}
        <section class="card" style="margin-bottom:22px;">
            <span class="module-number">
                Module {{ module.position }}
            </span>

            <h2>{{ module.title }}</h2>

            {% if module.questions %}
                <div style="overflow-x:auto">
                    <table>
                        <thead>
                            <tr>
                                <th>Question</th>
                                <th>Correct</th>
                                <th>Actions</th>
                            </tr>
                        </thead>

                        <tbody>
                            {% for question in module.questions|sort(attribute='id') %}
                                <tr>
                                    <td>{{ question.text }}</td>
                                    <td>{{ question.correct_option }}</td>
                                    <td>
                                        <div class="actions">
                                            <a
                                                class="btn small"
                                                href="{{ url_for(
                                                    'admin_edit_question',
                                                    question_id=question.id
                                                ) }}"
                                            >
                                                Edit
                                            </a>

                                            <form
                                                method="post"
                                                action="{{ url_for(
                                                    'admin_delete_question',
                                                    question_id=question.id
                                                ) }}"
                                                onsubmit="return confirm(
                                                    'Delete this question?'
                                                );"
                                            >
                                                <button
                                                    class="btn small danger"
                                                    type="submit"
                                                >
                                                    Delete
                                                </button>
                                            </form>
                                        </div>
                                    </td>
                                </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            {% else %}
                <p>No questions have been added.</p>
            {% endif %}
        </section>
    {% endfor %}
    """

    return page(
        "Manage Questions",
        content,
        modules=modules,
        active_tab="questions",
    )


@app.route("/admin/questions/add", methods=["GET", "POST"])
@admin_required
def admin_add_question():
    modules = Module.query.order_by(
        Module.position,
        Module.id,
    ).all()

    values = question_form_values()

    if request.method == "POST":
        if not all(values.values()):
            flash("Please complete every field.")
        elif values["correct_option"] not in {"A", "B", "C", "D"}:
            flash("Correct answer must be A, B, C or D.")
        else:
            question = Question(
                module_id=int(values["module_id"]),
                text=values["text"],
                option_a=values["option_a"],
                option_b=values["option_b"],
                option_c=values["option_c"],
                option_d=values["option_d"],
                correct_option=values["correct_option"],
                explanation=values["explanation"],
            )

            db.session.add(question)
            db.session.commit()

            flash("Question added.")
            return redirect(url_for("admin_questions"))

    return page(
        "Add Question",
        QUESTION_FORM,
        admin_tabs=render_template_string(
            ADMIN_TABS,
            active_tab="questions",
        ),
        heading="Add question",
        submit_label="Add question",
        modules=modules,
        values=values,
    )


@app.route(
    "/admin/questions/<int:question_id>/edit",
    methods=["GET", "POST"],
)
@admin_required
def admin_edit_question(question_id):
    question = db.session.get(Question, question_id)

    if not question:
        flash("Question not found.")
        return redirect(url_for("admin_questions"))

    modules = Module.query.order_by(
        Module.position,
        Module.id,
    ).all()

    values = question_form_values(question)

    if request.method == "POST":
        if not all(values.values()):
            flash("Please complete every field.")
        elif values["correct_option"] not in {"A", "B", "C", "D"}:
            flash("Correct answer must be A, B, C or D.")
        else:
            question.module_id = int(values["module_id"])
            question.text = values["text"]
            question.option_a = values["option_a"]
            question.option_b = values["option_b"]
            question.option_c = values["option_c"]
            question.option_d = values["option_d"]
            question.correct_option = values["correct_option"]
            question.explanation = values["explanation"]

            db.session.commit()

            flash("Question updated.")
            return redirect(url_for("admin_questions"))

    return page(
        "Edit Question",
        QUESTION_FORM,
        admin_tabs=render_template_string(
            ADMIN_TABS,
            active_tab="questions",
        ),
        heading="Edit question",
        submit_label="Save changes",
        modules=modules,
        values=values,
    )


@app.route(
    "/admin/questions/<int:question_id>/delete",
    methods=["POST"],
)
@admin_required
def admin_delete_question(question_id):
    question = db.session.get(Question, question_id)

    if question:
        db.session.delete(question)
        db.session.commit()
        flash("Question deleted.")

    return redirect(url_for("admin_questions"))


# ---------------------------------------------------------------------------
# Module manager
# ---------------------------------------------------------------------------

MODULE_FORM = """
{{ admin_tabs|safe }}

<section class="hero">
    <h1>{{ heading }}</h1>

    <form method="post">
        <label for="title">Module title</label>
        <input
            id="title"
            name="title"
            type="text"
            value="{{ values.title }}"
            required
        >

        <label for="description">Description</label>
        <textarea
            id="description"
            name="description"
            required
        >{{ values.description }}</textarea>

        <label for="position">Display position</label>
        <input
            id="position"
            name="position"
            type="number"
            min="1"
            value="{{ values.position }}"
            required
        >

        <button class="btn" type="submit">
            {{ submit_label }}
        </button>
    </form>
</section>
"""


@app.route("/admin/modules")
@admin_required
def admin_modules():
    modules = Module.query.order_by(
        Module.position,
        Module.id,
    ).all()

    content = ADMIN_TABS + """
    <section class="hero">
        <h1>Manage modules</h1>

        <a
            class="btn"
            href="{{ url_for('admin_add_module') }}"
        >
            Add new module
        </a>
    </section>

    <div class="grid">
        {% for module in modules %}
            <article class="card">
                <span class="module-number">
                    Module {{ module.position }}
                </span>

                <h3>{{ module.title }}</h3>
                <p>{{ module.description }}</p>

                <p class="muted">
                    {{ module.questions|length }} questions
                </p>

                <a
                    class="btn small"
                    href="{{ url_for(
                        'admin_edit_module',
                        module_id=module.id
                    ) }}"
                >
                    Edit module
                </a>
            </article>
        {% endfor %}
    </div>
    """

    return page(
        "Manage Modules",
        content,
        modules=modules,
        active_tab="modules",
    )


@app.route("/admin/modules/add", methods=["GET", "POST"])
@admin_required
def admin_add_module():
    next_position = (
        db.session.query(func.max(Module.position)).scalar() or 0
    ) + 1

    values = {
        "title": "",
        "description": "",
        "position": next_position,
    }

    if request.method == "POST":
        values = {
            "title": request.form.get("title", "").strip(),
            "description": request.form.get(
                "description",
                "",
            ).strip(),
            "position": request.form.get(
                "position",
                "",
            ).strip(),
        }

        if not all(values.values()):
            flash("Please complete every field.")
        else:
            try:
                position = int(values["position"])
            except ValueError:
                flash("Display position must be a number.")
            else:
                module = Module(
                    title=values["title"],
                    description=values["description"],
                    position=position,
                )

                db.session.add(module)
                db.session.commit()

                flash("Module added.")
                return redirect(url_for("admin_modules"))

    return page(
        "Add Module",
        MODULE_FORM,
        admin_tabs=render_template_string(
            ADMIN_TABS,
            active_tab="modules",
        ),
        heading="Add module",
        submit_label="Add module",
        values=values,
    )


@app.route(
    "/admin/modules/<int:module_id>/edit",
    methods=["GET", "POST"],
)
@admin_required
def admin_edit_module(module_id):
    module = db.session.get(Module, module_id)

    if not module:
        flash("Module not found.")
        return redirect(url_for("admin_modules"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        position_text = request.form.get("position", "").strip()

        if not title or not description or not position_text:
            flash("Please complete every field.")
        else:
            try:
                position = int(position_text)
            except ValueError:
                flash("Display position must be a number.")
            else:
                module.title = title
                module.description = description
                module.position = position

                db.session.commit()

                flash("Module updated.")
                return redirect(url_for("admin_modules"))

    values = {
        "title": module.title,
        "description": module.description,
        "position": module.position,
    }

    return page(
        "Edit Module",
        MODULE_FORM,
        admin_tabs=render_template_string(
            ADMIN_TABS,
            active_tab="modules",
        ),
        heading="Edit module",
        submit_label="Save changes",
        values=values,
    )


# ---------------------------------------------------------------------------
# Resource manager
# ---------------------------------------------------------------------------

RESOURCE_FORM = """
{{ admin_tabs|safe }}

<section class="hero">
    <h1>{{ heading }}</h1>

    <p class="muted">
        Upload a file or paste an external link.
        Uploaded files should be stored on a Render persistent disk.
    </p>

    <form method="post" enctype="multipart/form-data">
        <label for="category">Resource type</label>
        <select id="category" name="category" required>
            {% for value, label in categories %}
                <option
                    value="{{ value }}"
                    {% if values.category == value %}
                        selected
                    {% endif %}
                >
                    {{ label }}
                </option>
            {% endfor %}
        </select>

        <label for="title">Title</label>
        <input
            id="title"
            name="title"
            type="text"
            value="{{ values.title }}"
            required
        >

        <label for="description">Description</label>
        <textarea
            id="description"
            name="description"
        >{{ values.description }}</textarea>

        <label for="module_id">Module</label>
        <select id="module_id" name="module_id">
            <option value="">General library</option>

            {% for module in modules %}
                <option
                    value="{{ module.id }}"
                    {% if values.module_id|string == module.id|string %}
                        selected
                    {% endif %}
                >
                    Module {{ module.position }} — {{ module.title }}
                </option>
            {% endfor %}
        </select>

        <label for="external_url">External link</label>
        <input
            id="external_url"
            name="external_url"
            type="url"
            value="{{ values.external_url }}"
            placeholder="https://..."
        >

        <label for="upload">Upload file</label>
        <input
            id="upload"
            name="upload"
            type="file"
        >

        {% if current_filename %}
            <p class="muted">
                Current file: {{ current_filename }}
            </p>

            <label>
                <input
                    type="checkbox"
                    name="remove_file"
                    value="yes"
                >
                Remove current uploaded file
            </label>
        {% endif %}

        <label>
            <input
                type="checkbox"
                name="active"
                value="yes"
                {% if values.active %}checked{% endif %}
            >
            Visible to students
        </label>

        <button class="btn" type="submit">
            {{ submit_label }}
        </button>
    </form>
</section>
"""


def resource_form_values(resource=None):
    if request.method == "POST":
        return {
            "category": request.form.get(
                "category",
                "other",
            ),
            "title": request.form.get(
                "title",
                "",
            ).strip(),
            "description": request.form.get(
                "description",
                "",
            ).strip(),
            "module_id": request.form.get(
                "module_id",
                "",
            ).strip(),
            "external_url": request.form.get(
                "external_url",
                "",
            ).strip(),
            "active": request.form.get("active") == "yes",
        }

    return {
        "category": (
            resource.category
            if resource
            else "presentation"
        ),
        "title": resource.title if resource else "",
        "description": resource.description if resource else "",
        "module_id": (
            str(resource.module_id)
            if resource and resource.module_id
            else ""
        ),
        "external_url": (
            resource.external_url
            if resource
            else ""
        ),
        "active": (
            resource.active
            if resource
            else True
        ),
    }


@app.route("/admin/resources")
@admin_required
def admin_resources():
    resources = Resource.query.order_by(
        Resource.category,
        Resource.title,
    ).all()

    content = ADMIN_TABS + """
    <section class="hero">
        <h1>Manage resources</h1>

        <p>
            Add presentations, PDFs, sample calls,
            lock images and other Academy material.
        </p>

        <a
            class="btn"
            href="{{ url_for('admin_add_resource') }}"
        >
            Add resource
        </a>
    </section>

    {% if resources %}
        <div style="overflow-x:auto">
            <table>
                <thead>
                    <tr>
                        <th>Type</th>
                        <th>Title</th>
                        <th>Module</th>
                        <th>File or link</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>

                <tbody>
                    {% for resource in resources %}
                        <tr>
                            <td>
                                {{ category_labels.get(
                                    resource.category,
                                    resource.category
                                ) }}
                            </td>

                            <td>{{ resource.title }}</td>

                            <td>
                                {{ resource.module.title
                                   if resource.module
                                   else 'General' }}
                            </td>

                            <td>
                                {{ resource.original_filename
                                   or resource.external_url
                                   or 'Not added' }}
                            </td>

                            <td>
                                {{ 'Active'
                                   if resource.active
                                   else 'Hidden' }}
                            </td>

                            <td>
                                <div class="actions">
                                    <a
                                        class="btn small"
                                        href="{{ url_for(
                                            'admin_edit_resource',
                                            resource_id=resource.id
                                        ) }}"
                                    >
                                        Edit
                                    </a>

                                    <form
                                        method="post"
                                        action="{{ url_for(
                                            'admin_delete_resource',
                                            resource_id=resource.id
                                        ) }}"
                                        onsubmit="return confirm(
                                            'Delete this resource?'
                                        );"
                                    >
                                        <button
                                            class="btn small danger"
                                            type="submit"
                                        >
                                            Delete
                                        </button>
                                    </form>
                                </div>
                            </td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    {% else %}
        <div class="card">
            <p>No resources have been added yet.</p>
        </div>
    {% endif %}
    """

    return page(
        "Manage Resources",
        content,
        resources=resources,
        category_labels=dict(RESOURCE_CATEGORIES),
        active_tab="resources",
    )


@app.route("/admin/resources/add", methods=["GET", "POST"])
@admin_required
def admin_add_resource():
    modules = Module.query.order_by(
        Module.position,
        Module.id,
    ).all()

    values = resource_form_values()

    if request.method == "POST":
        if not values["title"]:
            flash("Please enter a title.")
        else:
            upload = request.files.get("upload")

            try:
                stored_filename, original_filename = (
                    save_uploaded_file(upload)
                )
            except ValueError as exc:
                flash(str(exc))
            else:
                resource = Resource(
                    category=values["category"],
                    title=values["title"],
                    description=values["description"],
                    external_url=values["external_url"],
                    stored_filename=stored_filename,
                    original_filename=original_filename,
                    module_id=(
                        int(values["module_id"])
                        if values["module_id"]
                        else None
                    ),
                    active=values["active"],
                )

                db.session.add(resource)
                db.session.commit()

                flash("Resource added.")
                return redirect(url_for("admin_resources"))

    return page(
        "Add Resource",
        RESOURCE_FORM,
        admin_tabs=render_template_string(
            ADMIN_TABS,
            active_tab="resources",
        ),
        heading="Add resource",
        submit_label="Add resource",
        categories=RESOURCE_CATEGORIES,
        modules=modules,
        values=values,
        current_filename="",
    )


@app.route(
    "/admin/resources/<int:resource_id>/edit",
    methods=["GET", "POST"],
)
@admin_required
def admin_edit_resource(resource_id):
    resource = db.session.get(Resource, resource_id)

    if not resource:
        flash("Resource not found.")
        return redirect(url_for("admin_resources"))

    modules = Module.query.order_by(
        Module.position,
        Module.id,
    ).all()

    values = resource_form_values(resource)

    if request.method == "POST":
        if not values["title"]:
            flash("Please enter a title.")
        else:
            upload = request.files.get("upload")
            remove_file = (
                request.form.get("remove_file") == "yes"
            )

            try:
                new_stored, new_original = save_uploaded_file(upload)
            except ValueError as exc:
                flash(str(exc))
            else:
                if remove_file:
                    delete_stored_file(resource.stored_filename)
                    resource.stored_filename = ""
                    resource.original_filename = ""

                if new_stored:
                    delete_stored_file(resource.stored_filename)
                    resource.stored_filename = new_stored
                    resource.original_filename = new_original

                resource.category = values["category"]
                resource.title = values["title"]
                resource.description = values["description"]
                resource.external_url = values["external_url"]
                resource.module_id = (
                    int(values["module_id"])
                    if values["module_id"]
                    else None
                )
                resource.active = values["active"]

                db.session.commit()

                flash("Resource updated.")
                return redirect(url_for("admin_resources"))

    return page(
        "Edit Resource",
        RESOURCE_FORM,
        admin_tabs=render_template_string(
            ADMIN_TABS,
            active_tab="resources",
        ),
        heading="Edit resource",
        submit_label="Save changes",
        categories=RESOURCE_CATEGORIES,
        modules=modules,
        values=values,
        current_filename=resource.original_filename,
    )


@app.route(
    "/admin/resources/<int:resource_id>/delete",
    methods=["POST"],
)
@admin_required
def admin_delete_resource(resource_id):
    resource = db.session.get(Resource, resource_id)

    if resource:
        delete_stored_file(resource.stored_filename)
        db.session.delete(resource)
        db.session.commit()
        flash("Resource deleted.")

    return redirect(url_for("admin_resources"))


# ---------------------------------------------------------------------------
# Glossary manager
# ---------------------------------------------------------------------------

GLOSSARY_FORM = """
{{ admin_tabs|safe }}

<section class="hero">
    <h1>{{ heading }}</h1>

    <form method="post">
        <label for="term">Term</label>
        <input
            id="term"
            name="term"
            type="text"
            value="{{ values.term }}"
            required
        >

        <label for="definition">Definition</label>
        <textarea
            id="definition"
            name="definition"
            required
        >{{ values.definition }}</textarea>

        <label for="example">Example</label>
        <textarea
            id="example"
            name="example"
        >{{ values.example }}</textarea>

        <label>
            <input
                type="checkbox"
                name="active"
                value="yes"
                {% if values.active %}checked{% endif %}
            >
            Visible to students
        </label>

        <button class="btn" type="submit">
            {{ submit_label }}
        </button>
    </form>
</section>
"""


@app.route("/admin/glossary")
@admin_required
def admin_glossary():
    entries = GlossaryEntry.query.order_by(
        GlossaryEntry.term,
    ).all()

    content = ADMIN_TABS + """
    <section class="hero">
        <h1>Manage glossary</h1>

        <a
            class="btn"
            href="{{ url_for('admin_add_glossary') }}"
        >
            Add glossary entry
        </a>
    </section>

    {% if entries %}
        <div style="overflow-x:auto">
            <table>
                <thead>
                    <tr>
                        <th>Term</th>
                        <th>Definition</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>

                <tbody>
                    {% for entry in entries %}
                        <tr>
                            <td><strong>{{ entry.term }}</strong></td>
                            <td>{{ entry.definition }}</td>
                            <td>
                                {{ 'Active'
                                   if entry.active
                                   else 'Hidden' }}
                            </td>
                            <td>
                                <div class="actions">
                                    <a
                                        class="btn small"
                                        href="{{ url_for(
                                            'admin_edit_glossary',
                                            entry_id=entry.id
                                        ) }}"
                                    >
                                        Edit
                                    </a>

                                    <form
                                        method="post"
                                        action="{{ url_for(
                                            'admin_delete_glossary',
                                            entry_id=entry.id
                                        ) }}"
                                        onsubmit="return confirm(
                                            'Delete this glossary entry?'
                                        );"
                                    >
                                        <button
                                            class="btn small danger"
                                            type="submit"
                                        >
                                            Delete
                                        </button>
                                    </form>
                                </div>
                            </td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    {% else %}
        <div class="card">
            <p>No glossary entries have been added yet.</p>
        </div>
    {% endif %}
    """

    return page(
        "Manage Glossary",
        content,
        entries=entries,
        active_tab="glossary",
    )


@app.route("/admin/glossary/add", methods=["GET", "POST"])
@admin_required
def admin_add_glossary():
    values = {
        "term": "",
        "definition": "",
        "example": "",
        "active": True,
    }

    if request.method == "POST":
        values = {
            "term": request.form.get("term", "").strip(),
            "definition": request.form.get(
                "definition",
                "",
            ).strip(),
            "example": request.form.get(
                "example",
                "",
            ).strip(),
            "active": request.form.get("active") == "yes",
        }

        if not values["term"] or not values["definition"]:
            flash("Term and definition are required.")
        elif GlossaryEntry.query.filter(
            func.lower(GlossaryEntry.term)
            == values["term"].lower()
        ).first():
            flash("That glossary term already exists.")
        else:
            db.session.add(GlossaryEntry(**values))
            db.session.commit()

            flash("Glossary entry added.")
            return redirect(url_for("admin_glossary"))

    return page(
        "Add Glossary Entry",
        GLOSSARY_FORM,
        admin_tabs=render_template_string(
            ADMIN_TABS,
            active_tab="glossary",
        ),
        heading="Add glossary entry",
        submit_label="Add entry",
        values=values,
    )


@app.route(
    "/admin/glossary/<int:entry_id>/edit",
    methods=["GET", "POST"],
)
@admin_required
def admin_edit_glossary(entry_id):
    entry = db.session.get(GlossaryEntry, entry_id)

    if not entry:
        flash("Glossary entry not found.")
        return redirect(url_for("admin_glossary"))

    if request.method == "POST":
        term = request.form.get("term", "").strip()
        definition = request.form.get(
            "definition",
            "",
        ).strip()

        if not term or not definition:
            flash("Term and definition are required.")
        else:
            duplicate = GlossaryEntry.query.filter(
                func.lower(GlossaryEntry.term) == term.lower(),
                GlossaryEntry.id != entry.id,
            ).first()

            if duplicate:
                flash("That glossary term already exists.")
            else:
                entry.term = term
                entry.definition = definition
                entry.example = request.form.get(
                    "example",
                    "",
                ).strip()
                entry.active = (
                    request.form.get("active") == "yes"
                )

                db.session.commit()

                flash("Glossary entry updated.")
                return redirect(url_for("admin_glossary"))

    values = {
        "term": entry.term,
        "definition": entry.definition,
        "example": entry.example,
        "active": entry.active,
    }

    return page(
        "Edit Glossary Entry",
        GLOSSARY_FORM,
        admin_tabs=render_template_string(
            ADMIN_TABS,
            active_tab="glossary",
        ),
        heading="Edit glossary entry",
        submit_label="Save changes",
        values=values,
    )


@app.route(
    "/admin/glossary/<int:entry_id>/delete",
    methods=["POST"],
)
@admin_required
def admin_delete_glossary(entry_id):
    entry = db.session.get(GlossaryEntry, entry_id)

    if entry:
        db.session.delete(entry)
        db.session.commit()
        flash("Glossary entry deleted.")

    return redirect(url_for("admin_glossary"))


# ---------------------------------------------------------------------------
# Price manager
# ---------------------------------------------------------------------------

PRICE_FORM = """
{{ admin_tabs|safe }}

<section class="hero">
    <h1>{{ heading }}</h1>

    <form method="post">
        <label for="job_type">Job type</label>
        <input
            id="job_type"
            name="job_type"
            type="text"
            value="{{ values.job_type }}"
            required
        >

        <label for="starting_price">Starting price</label>
        <input
            id="starting_price"
            name="starting_price"
            type="text"
            value="{{ values.starting_price }}"
            required
        >

        <label for="vat_note">VAT note</label>
        <input
            id="vat_note"
            name="vat_note"
            type="text"
            value="{{ values.vat_note }}"
        >

        <label for="eta">ETA guidance</label>
        <input
            id="eta"
            name="eta"
            type="text"
            value="{{ values.eta }}"
        >

        <label for="wording">Approved customer wording</label>
        <textarea
            id="wording"
            name="wording"
        >{{ values.wording }}</textarea>

        <label for="internal_notes">Internal manager notes</label>
        <textarea
            id="internal_notes"
            name="internal_notes"
        >{{ values.internal_notes }}</textarea>

        <label>
            <input
                type="checkbox"
                name="active"
                value="yes"
                {% if values.active %}checked{% endif %}
            >
            Visible to students
        </label>

        <button class="btn" type="submit">
            {{ submit_label }}
        </button>
    </form>
</section>
"""


def price_form_values(item=None):
    if request.method == "POST":
        return {
            "job_type": request.form.get(
                "job_type",
                "",
            ).strip(),
            "starting_price": request.form.get(
                "starting_price",
                "",
            ).strip(),
            "vat_note": request.form.get(
                "vat_note",
                "",
            ).strip(),
            "eta": request.form.get(
                "eta",
                "",
            ).strip(),
            "wording": request.form.get(
                "wording",
                "",
            ).strip(),
            "internal_notes": request.form.get(
                "internal_notes",
                "",
            ).strip(),
            "active": request.form.get("active") == "yes",
        }

    return {
        "job_type": item.job_type if item else "",
        "starting_price": item.starting_price if item else "",
        "vat_note": item.vat_note if item else "",
        "eta": item.eta if item else "",
        "wording": item.wording if item else "",
        "internal_notes": item.internal_notes if item else "",
        "active": item.active if item else True,
    }


@app.route("/admin/prices")
@admin_required
def admin_prices():
    items = PriceItem.query.order_by(
        PriceItem.job_type,
    ).all()

    content = ADMIN_TABS + """
    <section class="hero">
        <h1>Manage price list</h1>

        <a
            class="btn"
            href="{{ url_for('admin_add_price') }}"
        >
            Add price
        </a>
    </section>

    {% if items %}
        <div style="overflow-x:auto">
            <table>
                <thead>
                    <tr>
                        <th>Job type</th>
                        <th>Starting price</th>
                        <th>VAT</th>
                        <th>ETA</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>

                <tbody>
                    {% for item in items %}
                        <tr>
                            <td>{{ item.job_type }}</td>
                            <td>{{ item.starting_price }}</td>
                            <td>{{ item.vat_note }}</td>
                            <td>{{ item.eta }}</td>
                            <td>
                                {{ 'Active'
                                   if item.active
                                   else 'Hidden' }}
                            </td>
                            <td>
                                <div class="actions">
                                    <a
                                        class="btn small"
                                        href="{{ url_for(
                                            'admin_edit_price',
                                            price_id=item.id
                                        ) }}"
                                    >
                                        Edit
                                    </a>

                                    <form
                                        method="post"
                                        action="{{ url_for(
                                            'admin_delete_price',
                                            price_id=item.id
                                        ) }}"
                                        onsubmit="return confirm(
                                            'Delete this price?'
                                        );"
                                    >
                                        <button
                                            class="btn small danger"
                                            type="submit"
                                        >
                                            Delete
                                        </button>
                                    </form>
                                </div>
                            </td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    {% else %}
        <div class="card">
            <p>No price entries have been added yet.</p>
        </div>
    {% endif %}
    """

    return page(
        "Manage Prices",
        content,
        items=items,
        active_tab="prices",
    )


@app.route("/admin/prices/add", methods=["GET", "POST"])
@admin_required
def admin_add_price():
    values = price_form_values()

    if request.method == "POST":
        if not values["job_type"] or not values["starting_price"]:
            flash("Job type and starting price are required.")
        else:
            db.session.add(PriceItem(**values))
            db.session.commit()

            flash("Price added.")
            return redirect(url_for("admin_prices"))

    return page(
        "Add Price",
        PRICE_FORM,
        admin_tabs=render_template_string(
            ADMIN_TABS,
            active_tab="prices",
        ),
        heading="Add price",
        submit_label="Add price",
        values=values,
    )


@app.route(
    "/admin/prices/<int:price_id>/edit",
    methods=["GET", "POST"],
)
@admin_required
def admin_edit_price(price_id):
    item = db.session.get(PriceItem, price_id)

    if not item:
        flash("Price not found.")
        return redirect(url_for("admin_prices"))

    values = price_form_values(item)

    if request.method == "POST":
        if not values["job_type"] or not values["starting_price"]:
            flash("Job type and starting price are required.")
        else:
            for field, value in values.items():
                setattr(item, field, value)

            db.session.commit()

            flash("Price updated.")
            return redirect(url_for("admin_prices"))

    return page(
        "Edit Price",
        PRICE_FORM,
        admin_tabs=render_template_string(
            ADMIN_TABS,
            active_tab="prices",
        ),
        heading="Edit price",
        submit_label="Save changes",
        values=values,
    )


@app.route(
    "/admin/prices/<int:price_id>/delete",
    methods=["POST"],
)
@admin_required
def admin_delete_price(price_id):
    item = db.session.get(PriceItem, price_id)

    if item:
        db.session.delete(item)
        db.session.commit()
        flash("Price deleted.")

    return redirect(url_for("admin_prices"))


# ---------------------------------------------------------------------------
# Job type manager
# ---------------------------------------------------------------------------

JOB_TYPE_FORM = """
{{ admin_tabs|safe }}

<section class="hero">
    <h1>{{ heading }}</h1>

    <form method="post">
        <label for="title">Job type title</label>
        <input
            id="title"
            name="title"
            type="text"
            value="{{ values.title }}"
            required
        >

        <label for="description">Description</label>
        <textarea
            id="description"
            name="description"
            required
        >{{ values.description }}</textarea>

        <label for="caller_wording">What callers may say</label>
        <textarea
            id="caller_wording"
            name="caller_wording"
        >{{ values.caller_wording }}</textarea>

        <label for="questions_to_ask">Questions to ask</label>
        <textarea
            id="questions_to_ask"
            name="questions_to_ask"
        >{{ values.questions_to_ask }}</textarea>

        <label for="starting_price">Starting price</label>
        <input
            id="starting_price"
            name="starting_price"
            type="text"
            value="{{ values.starting_price }}"
        >

        <label for="eta">ETA guidance</label>
        <input
            id="eta"
            name="eta"
            type="text"
            value="{{ values.eta }}"
        >

        <label for="photos_needed">Are photos needed?</label>
        <input
            id="photos_needed"
            name="photos_needed"
            type="text"
            value="{{ values.photos_needed }}"
        >

        <label for="escalation">Escalation guidance</label>
        <textarea
            id="escalation"
            name="escalation"
        >{{ values.escalation }}</textarea>

        <label for="services_not_offered">Services not offered</label>
        <textarea
            id="services_not_offered"
            name="services_not_offered"
        >{{ values.services_not_offered }}</textarea>

        <label for="booking_notes">Example booking notes</label>
        <textarea
            id="booking_notes"
            name="booking_notes"
        >{{ values.booking_notes }}</textarea>

        <label>
            <input
                type="checkbox"
                name="active"
                value="yes"
                {% if values.active %}checked{% endif %}
            >
            Visible to students
        </label>

        <button class="btn" type="submit">
            {{ submit_label }}
        </button>
    </form>
</section>
"""


JOB_TYPE_FIELDS = [
    "title",
    "description",
    "caller_wording",
    "questions_to_ask",
    "starting_price",
    "eta",
    "photos_needed",
    "escalation",
    "services_not_offered",
    "booking_notes",
]


def job_type_form_values(item=None):
    if request.method == "POST":
        values = {
            field: request.form.get(field, "").strip()
            for field in JOB_TYPE_FIELDS
        }
        values["active"] = request.form.get("active") == "yes"
        return values

    values = {
        field: getattr(item, field) if item else ""
        for field in JOB_TYPE_FIELDS
    }
    values["active"] = item.active if item else True

    return values


@app.route("/admin/job-types")
@admin_required
def admin_job_types():
    items = JobType.query.order_by(
        JobType.title,
    ).all()

    content = ADMIN_TABS + """
    <section class="hero">
        <h1>Manage job types</h1>

        <a
            class="btn"
            href="{{ url_for('admin_add_job_type') }}"
        >
            Add job type
        </a>
    </section>

    <div class="grid">
        {% for item in items %}
            <article class="card">
                <h3>{{ item.title }}</h3>
                <p>{{ item.description }}</p>

                <p class="muted">
                    {{ 'Active'
                       if item.active
                       else 'Hidden' }}
                </p>

                <div class="actions">
                    <a
                        class="btn small"
                        href="{{ url_for(
                            'admin_edit_job_type',
                            job_type_id=item.id
                        ) }}"
                    >
                        Edit
                    </a>

                    <form
                        method="post"
                        action="{{ url_for(
                            'admin_delete_job_type',
                            job_type_id=item.id
                        ) }}"
                        onsubmit="return confirm(
                            'Delete this job type?'
                        );"
                    >
                        <button
                            class="btn small danger"
                            type="submit"
                        >
                            Delete
                        </button>
                    </form>
                </div>
            </article>
        {% else %}
            <div class="card">
                <p>No job types have been added yet.</p>
            </div>
        {% endfor %}
    </div>
    """

    return page(
        "Manage Job Types",
        content,
        items=items,
        active_tab="jobtypes",
    )


@app.route("/admin/job-types/add", methods=["GET", "POST"])
@admin_required
def admin_add_job_type():
    values = job_type_form_values()

    if request.method == "POST":
        if not values["title"] or not values["description"]:
            flash("Title and description are required.")
        else:
            db.session.add(JobType(**values))
            db.session.commit()

            flash("Job type added.")
            return redirect(url_for("admin_job_types"))

    return page(
        "Add Job Type",
        JOB_TYPE_FORM,
        admin_tabs=render_template_string(
            ADMIN_TABS,
            active_tab="jobtypes",
        ),
        heading="Add job type",
        submit_label="Add job type",
        values=values,
    )


@app.route(
    "/admin/job-types/<int:job_type_id>/edit",
    methods=["GET", "POST"],
)
@admin_required
def admin_edit_job_type(job_type_id):
    item = db.session.get(JobType, job_type_id)

    if not item:
        flash("Job type not found.")
        return redirect(url_for("admin_job_types"))

    values = job_type_form_values(item)

    if request.method == "POST":
        if not values["title"] or not values["description"]:
            flash("Title and description are required.")
        else:
            for field, value in values.items():
                setattr(item, field, value)

            db.session.commit()

            flash("Job type updated.")
            return redirect(url_for("admin_job_types"))

    return page(
        "Edit Job Type",
        JOB_TYPE_FORM,
        admin_tabs=render_template_string(
            ADMIN_TABS,
            active_tab="jobtypes",
        ),
        heading="Edit job type",
        submit_label="Save changes",
        values=values,
    )


@app.route(
    "/admin/job-types/<int:job_type_id>/delete",
    methods=["POST"],
)
@admin_required
def admin_delete_job_type(job_type_id):
    item = db.session.get(JobType, job_type_id)

    if item:
        db.session.delete(item)
        db.session.commit()
        flash("Job type deleted.")

    return redirect(url_for("admin_job_types"))


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("home"))


@app.route("/health")
def health():
    return {"status": "ok"}, 200


# ---------------------------------------------------------------------------
# Initial quiz seed data
# ---------------------------------------------------------------------------

def seed_data():
    if Module.query.count() > 0:
        return

    modules_data = [
        {
            "title": "Call Foundations",
            "description": (
                "Customer type, problem identification, "
                "location capture and booking structure."
            ),
            "position": 1,
            "questions": [
                {
                    "text": (
                        "What is the first key distinction "
                        "to establish about the caller?"
                    ),
                    "options": [
                        "Whether they have used a locksmith before",
                        (
                            "Whether they are a homeowner, tenant, "
                            "landlord or business"
                        ),
                        "Whether they are calling from a mobile",
                        "Whether they can pay in cash",
                    ],
                    "correct": "B",
                    "explanation": (
                        "The caller type affects authority, payment "
                        "responsibility and the questions the agent must ask."
                    ),
                },
                {
                    "text": (
                        "A business is booking a locksmith. "
                        "What additional question must be asked?"
                    ),
                    "options": [
                        "How many staff work there?",
                        "Who will be responsible for paying the bill?",
                        "How long the company has traded?",
                        "Whether the manager is on site?",
                    ],
                    "correct": "B",
                    "explanation": (
                        "Payment responsibility must be clear "
                        "before dispatch."
                    ),
                },
                {
                    "text": (
                        "Which location detail is essential for dispatch?"
                    ),
                    "options": [
                        "The nearest supermarket",
                        "The borough only",
                        "The full postcode",
                        "The customer's work address",
                    ],
                    "correct": "C",
                    "explanation": (
                        "The full postcode is essential for "
                        "technician selection and ETA."
                    ),
                },
                {
                    "text": (
                        "After explaining the service and starting price, "
                        "what should the agent do?"
                    ),
                    "options": [
                        "Wait silently",
                        "End the call",
                        (
                            "Clearly ask whether the customer "
                            "wants to book"
                        ),
                        "Transfer every call",
                    ],
                    "correct": "C",
                    "explanation": (
                        "Every suitable enquiry should include "
                        "a clear booking attempt."
                    ),
                },
                {
                    "text": (
                        "Which is the best final step before "
                        "ending a booked call?"
                    ),
                    "options": [
                        "Repeat only the price",
                        (
                            "Confirm customer, address, problem, "
                            "ETA, price and payment details"
                        ),
                        "Tell the customer to call later",
                        (
                            "Ask the technician to collect "
                            "the details"
                        ),
                    ],
                    "correct": "B",
                    "explanation": (
                        "A concise confirmation reduces errors."
                    ),
                },
            ],
        },
        {
            "title": "Services and Lock Knowledge",
            "description": (
                "Common enquiries, services offered, excluded work "
                "and safe use of terminology."
            ),
            "position": 2,
            "questions": [
                {
                    "text": (
                        "Which enquiry is within the service list?"
                    ),
                    "options": [
                        "Changing a safe combination",
                        "Replacing access control",
                        "Installing a key safe",
                        "Programming a fob",
                    ],
                    "correct": "C",
                    "explanation": (
                        "Key safe installation is offered."
                    ),
                },
                {
                    "text": (
                        "A customer cannot identify their lock. "
                        "What should the agent do?"
                    ),
                    "options": [
                        "Guess",
                        "Refuse the booking",
                        (
                            "Record what the customer can see "
                            "and avoid guessing"
                        ),
                        "Promise no replacement is needed",
                    ],
                    "correct": "C",
                    "explanation": (
                        "Description is safer than incorrect diagnosis."
                    ),
                },
                {
                    "text": (
                        "What is the difference between "
                        "locked out and locked in?"
                    ),
                    "options": [
                        "There is no difference",
                        (
                            "Locked out means outside without access; "
                            "locked in means unable to exit"
                        ),
                        "Locked out applies only to businesses",
                        "Locked in always means a broken key",
                    ],
                    "correct": "B",
                    "explanation": (
                        "The distinction affects urgency and safety."
                    ),
                },
                {
                    "text": (
                        "Which brand may be mentioned "
                        "on a locksmith call?"
                    ),
                    "options": [
                        "Banham",
                        "Bosch dishwasher",
                        "Dyson",
                        "Samsung television",
                    ],
                    "correct": "A",
                    "explanation": (
                        "Banham is a lock brand."
                    ),
                },
                {
                    "text": (
                        "What is the agent's responsibility "
                        "regarding lock diagnosis?"
                    ),
                    "options": [
                        "Guarantee a diagnosis",
                        (
                            "Ask useful questions and record "
                            "accurate notes"
                        ),
                        (
                            "Tell the customer how to dismantle "
                            "the lock"
                        ),
                        "Guarantee the replacement part",
                    ],
                    "correct": "B",
                    "explanation": (
                        "Technicians diagnose; agents gather information."
                    ),
                },
            ],
        },
        {
            "title": "Pricing, ETA and Escalation",
            "description": (
                "Correct wording, realistic expectations, vulnerable "
                "situations and difficult calls."
            ),
            "position": 3,
            "questions": [
                {
                    "text": (
                        "How should the agent describe a starting price?"
                    ),
                    "options": [
                        "As a guaranteed final total",
                        (
                            "As the minimum price, with final cost "
                            "depending on work required"
                        ),
                        "As an optional charge",
                        "As travel cost only",
                    ],
                    "correct": "B",
                    "explanation": (
                        "Do not promise a final figure that "
                        "cannot be guaranteed."
                    ),
                },
                {
                    "text": "What should an ETA be based on?",
                    "options": [
                        "What the customer wants to hear",
                        "A fixed 15 minutes",
                        (
                            "Technician location, traffic, river "
                            "crossings and workload"
                        ),
                        "Postcode district alone",
                    ],
                    "correct": "C",
                    "explanation": (
                        "London travel varies significantly."
                    ),
                },
                {
                    "text": (
                        "A child is locked inside a property. "
                        "What is the best response?"
                    ),
                    "options": [
                        "Treat it normally",
                        (
                            "Recognise vulnerability and "
                            "escalate or prioritise"
                        ),
                        "Ask them to call tomorrow",
                        "Promise an exact arrival time",
                    ],
                    "correct": "B",
                    "explanation": (
                        "Vulnerable-person situations require "
                        "urgency and escalation."
                    ),
                },
                {
                    "text": (
                        "A caller cannot show permission to enter "
                        "a property. What should the agent do?"
                    ),
                    "options": [
                        "Dispatch anyway",
                        "Ignore it",
                        "Escalate the concern",
                        "Tell them how to force entry",
                    ],
                    "correct": "C",
                    "explanation": (
                        "Authority concerns must be escalated."
                    ),
                },
                {
                    "text": (
                        "What should an agent do when they "
                        "do not know an answer?"
                    ),
                    "options": [
                        "Guess",
                        "Make a promise",
                        "Ask for support or escalate",
                        "End the call",
                    ],
                    "correct": "C",
                    "explanation": (
                        "Seek support rather than provide "
                        "inaccurate information."
                    ),
                },
            ],
        },
    ]

    for module_data in modules_data:
        module = Module(
            title=module_data["title"],
            description=module_data["description"],
            position=module_data["position"],
        )

        db.session.add(module)
        db.session.flush()

        for question_data in module_data["questions"]:
            db.session.add(
                Question(
                    module_id=module.id,
                    text=question_data["text"],
                    option_a=question_data["options"][0],
                    option_b=question_data["options"][1],
                    option_c=question_data["options"][2],
                    option_d=question_data["options"][3],
                    correct_option=question_data["correct"],
                    explanation=question_data["explanation"],
                )
            )

    db.session.commit()


with app.app_context():
    db.create_all()
    seed_data()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True,
    )
