"""
Online Quiz Application - Flask backend.

- Questions and results are stored in SQLite (quiz.db).
- The correct answers NEVER leave the server until the quiz is submitted.
- The score is calculated here on the server, not in JavaScript.
"""

import os
import secrets
import sqlite3
import time
from datetime import datetime

from flask import Flask, g, redirect, render_template, request, session, url_for

app = Flask(__name__)

# The secret key signs the session cookie. On a real server, set the
# SECRET_KEY environment variable instead of using this default.
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# DATABASE_PATH can be changed with an environment variable (used on Render).
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "quiz.db"))

QUIZ_TIME_LIMIT = 600  # 10 minutes, in seconds

# (question, option1, option2, option3, option4, correct option number 1-4)
SAMPLE_QUESTIONS = [
    ("What is the capital city of Australia?",
     "Sydney", "Melbourne", "Canberra", "Perth", 3),
    ("Which planet is known as the Red Planet?",
     "Venus", "Mars", "Jupiter", "Mercury", 2),
    ("Which is the largest ocean on Earth?",
     "Atlantic Ocean", "Indian Ocean", "Arctic Ocean", "Pacific Ocean", 4),
    ("Who wrote the play 'Romeo and Juliet'?",
     "Charles Dickens", "William Shakespeare", "Jane Austen", "Mark Twain", 2),
    ("What is the chemical symbol for gold?",
     "Au", "Ag", "Gd", "Go", 1),
    ("How many continents are there on Earth?",
     "5", "6", "7", "8", 3),
    ("Which is the largest mammal in the world?",
     "African Elephant", "Blue Whale", "Giraffe", "Hippopotamus", 2),
    ("What is the currency of Japan?",
     "Won", "Yuan", "Yen", "Ringgit", 3),
    ("Who painted the Mona Lisa?",
     "Vincent van Gogh", "Pablo Picasso", "Leonardo da Vinci", "Michelangelo", 3),
    ("Which is the fastest land animal?",
     "Cheetah", "Lion", "Horse", "Leopard", 1),
    ("Which gas do plants absorb from the air for photosynthesis?",
     "Oxygen", "Nitrogen", "Carbon dioxide", "Hydrogen", 3),
    ("What is the national animal of India?",
     "Lion", "Bengal Tiger", "Elephant", "Peacock", 2),
]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    """Open one database connection per request and reuse it."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row  # lets us read columns by name
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    """Close the connection automatically when the request ends."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the tables (if missing) and add the sample questions once."""
    folder = os.path.dirname(DATABASE)
    if folder:
        os.makedirs(folder, exist_ok=True)

    conn = sqlite3.connect(DATABASE)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            question       TEXT NOT NULL,
            option1        TEXT NOT NULL,
            option2        TEXT NOT NULL,
            option3        TEXT NOT NULL,
            option4        TEXT NOT NULL,
            correct_option INTEGER NOT NULL CHECK (correct_option BETWEEN 1 AND 4)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            total_questions   INTEGER NOT NULL,
            correct_answers   INTEGER NOT NULL,
            incorrect_answers INTEGER NOT NULL,
            score             INTEGER NOT NULL,
            percentage        REAL NOT NULL,
            completed_at      TEXT NOT NULL
        )
        """
    )

    # Insert the sample questions only if the table is empty.
    count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    if count == 0:
        conn.executemany(
            """
            INSERT INTO questions
                (question, option1, option2, option3, option4, correct_option)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            SAMPLE_QUESTIONS,
        )
    conn.commit()
    conn.close()


# Runs when the app starts (also when gunicorn imports it on Render).
init_db()


# ---------------------------------------------------------------------------
# Quiz helper
# ---------------------------------------------------------------------------
def create_quiz():
    """Start a fresh quiz: shuffle the question ids and remember the start time."""
    rows = get_db().execute("SELECT id FROM questions ORDER BY RANDOM()").fetchall()
    session.clear()  # forget any previous quiz or result
    session["quiz_ids"] = [row["id"] for row in rows]
    session["quiz_token"] = secrets.token_hex(8)  # identifies this attempt
    session["start_time"] = time.time()           # the timer is checked server-side too


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Home page."""
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start():
    """Create a new quiz and open the quiz page."""
    create_quiz()
    return redirect(url_for("quiz"))


@app.route("/quiz")
def quiz():
    """Show the quiz. Only question text and options are sent - no answers."""
    if "result_id" in session:          # quiz already submitted
        return redirect(url_for("result"))
    if "quiz_ids" not in session:       # no quiz started yet
        return redirect(url_for("index"))

    ids = session["quiz_ids"]
    placeholders = ",".join("?" * len(ids))  # e.g. "?,?,?" (still parameterized)
    rows = get_db().execute(
        f"""
        SELECT id, question, option1, option2, option3, option4
        FROM questions WHERE id IN ({placeholders})
        """,
        ids,
    ).fetchall()
    by_id = {row["id"]: row for row in rows}

    questions = []
    for qid in ids:  # keep the shuffled order
        row = by_id.get(qid)
        if row is None:
            continue
        questions.append({
            "id": row["id"],
            "question": row["question"],
            "options": [row["option1"], row["option2"], row["option3"], row["option4"]],
        })

    # Time left is calculated from the server's clock so refreshing doesn't reset it.
    elapsed = time.time() - session["start_time"]
    remaining = max(0, int(QUIZ_TIME_LIMIT - elapsed))

    quiz_data = {
        "questions": questions,
        "remaining_seconds": remaining,
        "quiz_token": session["quiz_token"],
    }
    return render_template("quiz.html", quiz_data=quiz_data)


@app.route("/submit", methods=["POST"])
def submit():
    """Validate the answers, calculate the score and save the result."""
    # Repeated submission (double click, back button): just show the old result.
    if "result_id" in session:
        return redirect(url_for("result"))
    if "quiz_ids" not in session:
        return redirect(url_for("index"))

    db = get_db()
    ids = session["quiz_ids"]
    placeholders = ",".join("?" * len(ids))
    rows = db.execute(
        f"SELECT id, correct_option FROM questions WHERE id IN ({placeholders})",
        ids,
    ).fetchall()

    total = len(rows)
    correct = 0
    for row in rows:
        # The browser sends fields named answer_<question id> with value 1-4.
        submitted = request.form.get(f"answer_{row['id']}", "").strip()
        # Ignore anything that is not a number from 1 to 4 (empty = unanswered).
        if submitted.isdigit() and 1 <= int(submitted) <= 4:
            if int(submitted) == row["correct_option"]:
                correct += 1

    # Unanswered questions are counted as incorrect.
    incorrect = total - correct
    percentage = round((correct / total) * 100, 2) if total else 0.0
    completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor = db.execute(
        """
        INSERT INTO results
            (total_questions, correct_answers, incorrect_answers,
             score, percentage, completed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (total, correct, incorrect, correct, percentage, completed_at),
    )
    db.commit()

    # Mark the quiz as finished so it cannot be submitted twice.
    session["result_id"] = cursor.lastrowid
    session.pop("quiz_ids", None)
    session.pop("start_time", None)
    return redirect(url_for("result"))


@app.route("/result")
def result():
    """Show the saved result of the finished quiz."""
    result_id = session.get("result_id")
    if result_id is None:
        return redirect(url_for("index"))

    row = get_db().execute(
        "SELECT * FROM results WHERE id = ?", (result_id,)
    ).fetchone()
    if row is None:
        return redirect(url_for("index"))
    data = dict(row)

    # Pick a message based on the percentage.
    pct = data["percentage"]
    if pct >= 80:
        title, message = "Excellent!", "Outstanding work. You really know your stuff."
    elif pct >= 60:
        title, message = "Good job!", "Nice score. A little more practice and you'll be perfect."
    elif pct >= 40:
        title, message = "Not bad!", "You're getting there. Try again to improve your score."
    else:
        title, message = "Keep practicing!", "Don't give up. Restart the quiz and try again."

    return render_template("result.html", result=data, title=title, message=message)


@app.route("/restart", methods=["POST"])
def restart():
    """Throw away the old attempt and begin a brand-new quiz."""
    create_quiz()
    return redirect(url_for("quiz"))


if __name__ == "__main__":
    # debug=True auto-reloads the server when you edit files (local use only).
    app.run(debug=True)
