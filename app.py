import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask, flash, redirect, render_template_string,
    request, session, url_for
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-before-production")

database_url = os.environ.get("DATABASE_URL", "sqlite:///locksmith_quiz.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")
PASS_MARK = int(os.environ.get("PASS_MARK", "80"))


class Module(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    questions = db.relationship(
        "Question", backref="module", lazy=True,
        cascade="all, delete-orphan"
    )


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey("module.id"), nullable=False)
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
    module_id = db.Column(db.Integer, db.ForeignKey("module.id"), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    percentage = db.Column(db.Integer, nullable=False)
    passed = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    module = db.relationship("Module")


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
            --white: #ffffff;
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
        header a { color: white; text-decoration: none; }
        .brand { font-size: 1.25rem; font-weight: 700; }
        nav a { margin-left: 16px; font-size: .95rem; }
        .wrap { max-width: 1050px; margin: 0 auto; }
        main { padding: 32px 20px 60px; }
        .hero {
            background: white;
            border-radius: 16px;
            padding: 34px;
            box-shadow: 0 8px 26px rgba(20,40,61,.08);
            margin-bottom: 24px;
        }
        h1, h2, h3 { color: var(--navy); line-height: 1.2; }
        h1 { margin-top: 0; font-size: 2rem; }
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
        .module-number {
            display: inline-block;
            background: var(--navy);
            color: white;
            border-radius: 999px;
            padding: 5px 10px;
            font-size: .8rem;
            margin-bottom: 10px;
        }
        label { display: block; font-weight: 700; margin: 14px 0 6px; }
        input[type=text], input[type=email], input[type=password] {
            width: 100%;
            padding: 12px;
            border: 1px solid #c7d2d9;
            border-radius: 8px;
            font-size: 1rem;
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
        th { background: var(--navy); color: white; }
        .pill {
            display: inline-block;
            padding: 4px 9px;
            border-radius: 999px;
            font-size: .82rem;
            font-weight: 700;
        }
        .pill.pass { background: #dff3e8; }
        .pill.fail { background: #f7dddd; }
        footer {
            color: #6e7a83;
            text-align: center;
            padding: 24px;
            font-size: .9rem;
        }
        @media (max-width: 650px) {
            header .wrap { display: block; }
            nav { margin-top: 10px; }
            nav a { margin: 0 12px 0 0; }
            .hero { padding: 24px; }
            table { font-size: .88rem; }
            th, td { padding: 8px; }
        }
    </style>
</head>
<body>
<header>
    <div class="wrap">
        <a class="brand" href="{{ url_for('home') }}">Locksmith Call Handler Academy</a>
        <nav>
            <a href="{{ url_for('home') }}">Student Area</a>
            <a href="{{ url_for('admin_login') }}">Manager Results</a>
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
<footer>Training supports live-call readiness. Final approval remains with the trainer or manager.</footer>
</body>
</html>
"""


def page(title, content, **context):
    body = render_template_string(content, **context)
    return render_template_string(BASE_HTML, title=title, content=body)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/", methods=["GET", "POST"])
def home():
    modules = Module.query.order_by(Module.position).all()
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
        <p>This assessment checks your understanding of customer calls, locksmith services, pricing, location capture, dispatch and escalation.</p>
        <p class="muted">Enter your details to begin. Your results will be saved for your trainer.</p>
        <form method="post">
            <label for="student_name">Full name</label>
            <input id="student_name" name="student_name" type="text"
                   value="{{ session.get('student_name', '') }}" required>
            <label for="student_email">Email address</label>
            <input id="student_email" name="student_email" type="email"
                   value="{{ session.get('student_email', '') }}" required>
            <button class="btn" type="submit">Start training assessment</button>
        </form>
    </section>
    <div class="grid">
        {% for module in modules %}
        <article class="card">
            <span class="module-number">Module {{ module.position }}</span>
            <h3>{{ module.title }}</h3>
            <p>{{ module.description }}</p>
            <p class="muted">{{ module.questions|length }} questions</p>
        </article>
        {% endfor %}
    </div>
    """
    return page("Welcome", content, modules=modules, session=session)


@app.route("/modules")
def modules():
    if not session.get("student_name"):
        flash("Enter your details before starting.")
        return redirect(url_for("home"))

    modules = Module.query.order_by(Module.position).all()
    attempts = Attempt.query.filter_by(
        student_email=session["student_email"]
    ).order_by(Attempt.created_at.desc()).all()

    latest_by_module = {}
    for attempt in attempts:
        latest_by_module.setdefault(attempt.module_id, attempt)

    content = """
    <section class="hero">
        <h1>Welcome, {{ session['student_name'] }}</h1>
        <p>Select a module below. The pass mark is {{ pass_mark }}%.</p>
        <a class="btn light" href="{{ url_for('change_student') }}">Change student</a>
    </section>
    <div class="grid">
        {% for module in modules %}
        <article class="card">
            <span class="module-number">Module {{ module.position }}</span>
            <h3>{{ module.title }}</h3>
            <p>{{ module.description }}</p>
            {% if module.id in latest %}
                {% set result = latest[module.id] %}
                <p>Latest result:
                    <span class="pill {{ 'pass' if result.passed else 'fail' }}">
                        {{ result.percentage }}% — {{ 'Passed' if result.passed else 'Review needed' }}
                    </span>
                </p>
            {% else %}
                <p class="muted">Not attempted yet</p>
            {% endif %}
            <a class="btn" href="{{ url_for('take_quiz', module_id=module.id) }}">
                {{ 'Retake module' if module.id in latest else 'Start module' }}
            </a>
        </article>
        {% endfor %}
    </div>
    """
    return page(
        "Modules", content, modules=modules,
        latest=latest_by_module, pass_mark=PASS_MARK, session=session
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

    module = Module.query.get_or_404(module_id)
    questions = Question.query.filter_by(module_id=module.id).order_by(Question.id).all()

    if request.method == "POST":
        score = 0
        review = []
        for question in questions:
            selected = request.form.get(f"question_{question.id}", "")
            correct = selected == question.correct_option
            if correct:
                score += 1
            options = {
                "A": question.option_a,
                "B": question.option_b,
                "C": question.option_c,
                "D": question.option_d,
            }
            review.append({
                "question": question,
                "selected": selected,
                "selected_text": options.get(selected, "No answer selected"),
                "correct_text": options[question.correct_option],
                "correct": correct,
            })

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
            <p>You answered {{ score }} of {{ total }} questions correctly.</p>
            {% if passed %}
                <p>You have passed this knowledge check. This contributes to, but does not replace, trainer sign-off.</p>
            {% else %}
                <p>Review the explanations below, then retake the module. The pass mark is {{ pass_mark }}%.</p>
            {% endif %}
            <a class="btn" href="{{ url_for('modules') }}">Return to modules</a>
            <a class="btn secondary" href="{{ url_for('take_quiz', module_id=module.id) }}">Retake</a>
        </section>
        <h2>Answer review</h2>
        {% for item in review %}
        <div class="review {{ 'correct' if item.correct else 'incorrect' }}">
            <h3>{{ loop.index }}. {{ item.question.text }}</h3>
            <p><strong>Your answer:</strong> {{ item.selected_text }}</p>
            {% if not item.correct %}
                <p><strong>Correct answer:</strong> {{ item.correct_text }}</p>
            {% endif %}
            <p class="muted">{{ item.question.explanation }}</p>
        </div>
        {% endfor %}
        """
        return page(
            "Results", result_content, module=module, percentage=percentage,
            passed=passed, score=score, total=total, review=review,
            pass_mark=PASS_MARK
        )

    quiz_content = """
    <section class="hero">
        <span class="module-number">Module {{ module.position }}</span>
        <h1>{{ module.title }}</h1>
        <p>{{ module.description }}</p>
        <p class="muted">Choose one answer for every question, then submit your assessment.</p>
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
                <input type="radio" name="question_{{ question.id }}" value="{{ letter }}" required>
                <strong>{{ letter }}.</strong> {{ option }}
            </label>
            {% endfor %}
        </section>
        {% endfor %}
        <button class="btn" type="submit">Submit assessment</button>
    </form>
    """
    return page("Quiz", quiz_content, module=module, questions=questions)


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect manager password.")

    content = """
    <section class="hero">
        <h1>Manager access</h1>
        <p>Enter the manager password to view student results.</p>
        <form method="post">
            <label for="password">Password</label>
            <input id="password" name="password" type="password" required>
            <button class="btn" type="submit">Open results dashboard</button>
        </form>
    </section>
    """
    return page("Manager Login", content)


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    attempts = Attempt.query.order_by(Attempt.created_at.desc()).all()

    total_attempts = len(attempts)
    unique_students = db.session.query(
        func.count(func.distinct(Attempt.student_email))
    ).scalar() or 0
    passes = sum(1 for attempt in attempts if attempt.passed)
    pass_rate = round((passes / total_attempts) * 100) if total_attempts else 0

    content = """
    <section class="hero">
        <h1>Student results</h1>
        <p>Review module attempts and identify students who need further coaching.</p>
        <div class="grid">
            <div class="card"><h3>{{ unique_students }}</h3><p>Students</p></div>
            <div class="card"><h3>{{ total_attempts }}</h3><p>Total attempts</p></div>
            <div class="card"><h3>{{ pass_rate }}%</h3><p>Attempt pass rate</p></div>
        </div>
        <a class="btn light" href="{{ url_for('admin_logout') }}">Log out</a>
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
                <td>{{ attempt.created_at.strftime('%d %b %Y %H:%M') }}</td>
                <td>{{ attempt.student_name }}</td>
                <td>{{ attempt.student_email }}</td>
                <td>{{ attempt.module.title }}</td>
                <td>{{ attempt.score }}/{{ attempt.total }} ({{ attempt.percentage }}%)</td>
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
        <div class="card"><p>No student attempts have been recorded yet.</p></div>
    {% endif %}
    """
    return page(
        "Manager Dashboard", content, attempts=attempts,
        unique_students=unique_students, total_attempts=total_attempts,
        pass_rate=pass_rate
    )


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("home"))


@app.route("/health")
def health():
    return {"status": "ok"}, 200


def seed_data():
    if Module.query.count() > 0:
        return

    modules_data = [
        {
            "title": "Call Foundations",
            "description": "Customer type, problem identification, location capture and booking structure.",
            "position": 1,
            "questions": [
                {
                    "text": "What is the first key distinction to establish about the caller?",
                    "options": [
                        "Whether they have used a locksmith before",
                        "Whether they are a homeowner, tenant, landlord or business",
                        "Whether they are calling from a mobile",
                        "Whether they can pay in cash",
                    ],
                    "correct": "B",
                    "explanation": "The caller type affects authority, payment responsibility and the questions the agent must ask."
                },
                {
                    "text": "A business is booking a locksmith. What additional question must be asked?",
                    "options": [
                        "How many staff work there?",
                        "Who will be responsible for paying the bill?",
                        "How long the company has traded?",
                        "Whether the manager is on site?",
                    ],
                    "correct": "B",
                    "explanation": "Payment responsibility must be clear before the job is dispatched."
                },
                {
                    "text": "Which location detail is essential for dispatch?",
                    "options": [
                        "The nearest supermarket",
                        "The borough only",
                        "The full postcode",
                        "The customer's work address",
                    ],
                    "correct": "C",
                    "explanation": "The full postcode is essential for checking coverage, choosing a technician and quoting a realistic ETA."
                },
                {
                    "text": "After explaining the service and starting price, what should the agent do?",
                    "options": [
                        "Wait silently for the customer",
                        "End the call",
                        "Clearly ask whether the customer wants to book",
                        "Transfer every call to a manager",
                    ],
                    "correct": "C",
                    "explanation": "Every suitable enquiry should include a clear and professional booking attempt."
                },
                {
                    "text": "Which is the best final step before ending a booked call?",
                    "options": [
                        "Repeat only the price",
                        "Confirm the customer, address, problem, ETA, price and payment details",
                        "Tell the customer to call back later",
                        "Ask the technician to collect the details",
                    ],
                    "correct": "B",
                    "explanation": "A concise confirmation reduces mistakes and gives the technician complete information."
                },
            ]
        },
        {
            "title": "Services and Lock Knowledge",
            "description": "Common enquiries, services offered, excluded work and safe use of terminology.",
            "position": 2,
            "questions": [
                {
                    "text": "Which enquiry is within the service list?",
                    "options": [
                        "Changing a safe combination",
                        "Replacing a building access-control system",
                        "Installing a key safe",
                        "Programming an electronic entry fob",
                    ],
                    "correct": "C",
                    "explanation": "Key safe installation is offered. Safe combinations, access control and fob systems are not."
                },
                {
                    "text": "A customer cannot identify their lock. What should the agent do?",
                    "options": [
                        "Guess the most common lock type",
                        "Refuse the booking",
                        "Record what the customer can see and avoid guessing",
                        "Promise that no replacement will be needed",
                    ],
                    "correct": "C",
                    "explanation": "Clear description is safer than an incorrect diagnosis. The technician can assess the lock on arrival."
                },
                {
                    "text": "What is the difference between 'locked out' and 'locked in'?",
                    "options": [
                        "There is no difference",
                        "Locked out means outside without access; locked in means unable to exit",
                        "Locked out applies only to businesses",
                        "Locked in always means a key is broken",
                    ],
                    "correct": "B",
                    "explanation": "The distinction affects urgency, safety questions and dispatch notes."
                },
                {
                    "text": "Which brand may commonly be mentioned on a locksmith call?",
                    "options": [
                        "Banham",
                        "Bosch dishwasher",
                        "Dyson",
                        "Samsung television",
                    ],
                    "correct": "A",
                    "explanation": "Banham is one of the lock brands agents may hear, alongside Yale, Ingersoll, Chubb and Assa Abloy."
                },
                {
                    "text": "What is the agent's responsibility regarding lock diagnosis?",
                    "options": [
                        "Provide a guaranteed technical diagnosis",
                        "Understand enough to ask useful questions and record accurate notes",
                        "Tell the customer how to dismantle the lock",
                        "Guarantee the exact replacement part",
                    ],
                    "correct": "B",
                    "explanation": "Call handlers gather information; technicians diagnose and complete the physical work."
                },
            ]
        },
        {
            "title": "Pricing, ETA and Escalation",
            "description": "Correct wording, realistic expectations, vulnerable situations and difficult calls.",
            "position": 3,
            "questions": [
                {
                    "text": "How should the agent describe a starting price?",
                    "options": [
                        "As a guaranteed final total",
                        "As the minimum price, with final cost depending on assessment and work required",
                        "As an optional charge",
                        "As the technician's travel cost only",
                    ],
                    "correct": "B",
                    "explanation": "The agent should explain the starting price accurately without promising a final figure they cannot guarantee."
                },
                {
                    "text": "What should an ETA be based on?",
                    "options": [
                        "The shortest time the customer wants to hear",
                        "A standard promise of 15 minutes",
                        "Technician location, traffic, river crossings and workload",
                        "The customer's postcode district alone",
                    ],
                    "correct": "C",
                    "explanation": "London travel varies significantly. The nearest technician by distance is not always the quickest."
                },
                {
                    "text": "A child is locked inside a property. What is the best response?",
                    "options": [
                        "Treat it as an ordinary pricing enquiry",
                        "Recognise the vulnerability and escalate or prioritise according to procedure",
                        "Ask the customer to call tomorrow",
                        "Promise an exact arrival time without checking",
                    ],
                    "correct": "B",
                    "explanation": "Vulnerable-person situations require careful questioning, urgency and escalation according to company procedure."
                },
                {
                    "text": "A caller cannot show that they have permission to enter a property. What should the agent do?",
                    "options": [
                        "Dispatch without mentioning it",
                        "Ignore the issue if they sound confident",
                        "Escalate the concern and do not make unsafe assumptions",
                        "Tell them how to force entry",
                    ],
                    "correct": "C",
                    "explanation": "Authority and ownership concerns must be escalated rather than ignored."
                },
                {
                    "text": "What is the best approach when the agent does not know an answer?",
                    "options": [
                        "Guess confidently",
                        "Make a promise and correct it later",
                        "Ask for support or escalate",
                        "End the call immediately",
                    ],
                    "correct": "C",
                    "explanation": "A good agent follows the process and seeks support instead of giving inaccurate information."
                },
            ]
        }
    ]

    for module_data in modules_data:
        module = Module(
            title=module_data["title"],
            description=module_data["description"],
            position=module_data["position"],
        )
        db.session.add(module)
        db.session.flush()

        for q in module_data["questions"]:
            db.session.add(Question(
                module_id=module.id,
                text=q["text"],
                option_a=q["options"][0],
                option_b=q["options"][1],
                option_c=q["options"][2],
                option_d=q["options"][3],
                correct_option=q["correct"],
                explanation=q["explanation"],
            ))

    db.session.commit()


with app.app_context():
    db.create_all()
    seed_data()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
