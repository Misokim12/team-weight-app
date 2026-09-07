import base64
import csv
import io
import json
import os
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (
    Flask, Response, flash, jsonify, redirect, render_template,
    request, session, url_for
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from pywebpush import webpush, WebPushException
except ImportError:
    webpush = None
    WebPushException = Exception

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "CHANGE_ME")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///weight_app_v2.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:coach@example.com")


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    team = db.Column(db.String(80), default="")
    event = db.Column(db.String(80), default="")
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    weights = db.relationship(
        "WeightEntry", backref="student", lazy=True, cascade="all, delete-orphan"
    )
    pushes = db.relationship(
        "PushSubscription", backref="user", lazy=True, cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class WeightEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    entry_date = db.Column(db.Date, nullable=False)
    slot = db.Column(db.String(20), nullable=False)  # morning / evening
    weight_kg = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "entry_date", "slot", name="uq_student_date_slot"
        ),
    )


class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    endpoint = db.Column(db.Text, nullable=False, unique=True)
    subscription_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


@app.context_processor
def inject_user():
    return {"current_user": current_user(), "today": date.today()}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or user.role != "admin":
            flash("관리자 권한이 필요합니다.", "error")
            return redirect(url_for("index"))
        return view(*args, **kwargs)
    return wrapped


def parse_date(value, fallback):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return fallback


def parse_weight(raw):
    try:
        value = float(raw)
        if not 20 <= value <= 250:
            raise ValueError
        return round(value, 2)
    except (TypeError, ValueError):
        return None


def get_range():
    end = parse_date(request.args.get("end"), date.today())
    start = parse_date(
        request.args.get("start"), end - timedelta(days=13)
    )
    if start > end:
        start, end = end, start
    return start, end


@app.route("/manifest.webmanifest")
def manifest():
    return jsonify({
        "name": "선수 체중관리",
        "short_name": "체중관리",
        "description": "학생선수 아침·저녁 체중 기록 및 지도자 관리",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#f5f7fb",
        "theme_color": "#172033",
        "icons": [
            {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


@app.route("/service-worker.js")
def service_worker():
    return Response(
        render_template("service-worker.js"),
        mimetype="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.route("/offline")
def offline():
    return render_template("offline.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username, active=True).first()
        if user and user.check_password(password):
            session.clear()
            session["user_id"] = user.id
            return redirect(url_for("index"))
        flash("아이디 또는 비밀번호가 올바르지 않습니다.", "error")
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    user = current_user()
    if user.role == "admin":
        return redirect(url_for("admin_dashboard"))

    entries = (
        WeightEntry.query.filter_by(student_id=user.id)
        .order_by(WeightEntry.entry_date.desc(), WeightEntry.slot.desc())
        .limit(20)
        .all()
    )
    today_entries = {
        e.slot: e for e in WeightEntry.query.filter_by(
            student_id=user.id, entry_date=date.today()
        ).all()
    }
    return render_template(
        "student.html",
        entries=entries,
        today_entries=today_entries,
        vapid_public_key=VAPID_PUBLIC_KEY,
    )


@app.post("/weight")
@login_required
def save_weight():
    user = current_user()
    if user.role != "student":
        return redirect(url_for("admin_dashboard"))

    slot = request.form.get("slot")
    if slot not in ("morning", "evening"):
        flash("측정 구분이 올바르지 않습니다.", "error")
        return redirect(url_for("index"))

    weight = parse_weight(request.form.get("weight_kg"))
    if weight is None:
        flash("체중은 20~250kg 범위에서 입력해 주세요.", "error")
        return redirect(url_for("index"))

    today = date.today()
    entry = WeightEntry.query.filter_by(
        student_id=user.id, entry_date=today, slot=slot
    ).first()

    if entry:
        entry.weight_kg = weight
        entry.updated_at = datetime.utcnow()
    else:
        db.session.add(
            WeightEntry(
                student_id=user.id,
                entry_date=today,
                slot=slot,
                weight_kg=weight,
            )
        )
    db.session.commit()
    flash("체중 기록이 저장되었습니다.", "success")
    return redirect(url_for("index"))


@app.post("/api/push/subscribe")
@login_required
def push_subscribe():
    if not VAPID_PUBLIC_KEY:
        return jsonify({"ok": False, "message": "VAPID 키가 서버에 설정되지 않았습니다."}), 503

    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")
    if not endpoint:
        return jsonify({"ok": False, "message": "잘못된 구독 정보입니다."}), 400

    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing:
        existing.user_id = current_user().id
        existing.subscription_json = json.dumps(data)
    else:
        db.session.add(
            PushSubscription(
                user_id=current_user().id,
                endpoint=endpoint,
                subscription_json=json.dumps(data),
            )
        )
    db.session.commit()
    return jsonify({"ok": True})


@app.post("/api/push/unsubscribe")
@login_required
def push_unsubscribe():
    endpoint = (request.get_json(silent=True) or {}).get("endpoint")
    if endpoint:
        PushSubscription.query.filter_by(
            user_id=current_user().id, endpoint=endpoint
        ).delete()
        db.session.commit()
    return jsonify({"ok": True})


def send_push_to_user(user, title, body, url="/"):
    if not webpush or not VAPID_PRIVATE_KEY:
        return 0

    sent = 0
    subscriptions = PushSubscription.query.filter_by(user_id=user.id).all()
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=json.loads(sub.subscription_json),
                data=json.dumps({"title": title, "body": body, "url": url}),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
            )
            sent += 1
        except WebPushException:
            db.session.delete(sub)
        except Exception:
            db.session.delete(sub)
    db.session.commit()
    return sent


@app.route("/admin")
@admin_required
def admin_dashboard():
    start, end = get_range()
    selected_id = request.args.get("student_id", type=int)
    students = (
        User.query.filter_by(role="student", active=True)
        .order_by(User.name)
        .all()
    )

    entries = (
        WeightEntry.query.join(User)
        .filter(
            WeightEntry.entry_date.between(start, end),
            User.role == "student",
            User.active.is_(True),
        )
        .order_by(WeightEntry.entry_date.desc(), User.name, WeightEntry.slot)
        .all()
    )

    stats = []
    for student in students:
        own = [e for e in entries if e.student_id == student.id]
        values = [e.weight_kg for e in own]
        morning = [e.weight_kg for e in own if e.slot == "morning"]
        evening = [e.weight_kg for e in own if e.slot == "evening"]
        expected = (end - start).days + 1
        days_recorded = len({e.entry_date for e in own})
        stats.append({
            "student": student,
            "count": len(values),
            "expected": expected * 2,
            "completion": round((len(values) / (expected * 2)) * 100) if expected else 0,
            "days_recorded": days_recorded,
            "avg": round(sum(values) / len(values), 2) if values else None,
            "morning_avg": round(sum(morning) / len(morning), 2) if morning else None,
            "evening_avg": round(sum(evening) / len(evening), 2) if evening else None,
        })

    return render_template(
        "admin.html",
        students=students,
        entries=entries,
        stats=stats,
        start=start,
        end=end,
        selected_id=selected_id,
    )


@app.get("/api/admin/chart")
@admin_required
def admin_chart():
    start, end = get_range()
    student_id = request.args.get("student_id", type=int)
    if not student_id:
        return jsonify({"labels": [], "morning": [], "evening": []})

    student = User.query.filter_by(id=student_id, role="student").first()
    if not student:
        return jsonify({"labels": [], "morning": [], "evening": []}), 404

    rows = WeightEntry.query.filter(
        WeightEntry.student_id == student_id,
        WeightEntry.entry_date.between(start, end),
    ).all()
    by_key = {(e.entry_date, e.slot): e.weight_kg for e in rows}

    labels, morning, evening = [], [], []
    cursor = start
    while cursor <= end:
        labels.append(cursor.strftime("%m/%d"))
        morning.append(by_key.get((cursor, "morning")))
        evening.append(by_key.get((cursor, "evening")))
        cursor += timedelta(days=1)

    return jsonify({
        "student": student.name,
        "labels": labels,
        "morning": morning,
        "evening": evening,
    })


@app.post("/admin/student")
@admin_required
def create_student():
    name = request.form.get("name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    team = request.form.get("team", "").strip()
    event = request.form.get("event", "").strip()

    if not name or not username or len(password) < 6:
        flash("이름/아이디를 입력하고 비밀번호는 6자 이상으로 설정하세요.", "error")
        return redirect(url_for("admin_dashboard"))

    if User.query.filter_by(username=username).first():
        flash("이미 사용 중인 아이디입니다.", "error")
        return redirect(url_for("admin_dashboard"))

    student = User(
        name=name, username=username, team=team, event=event, role="student"
    )
    student.set_password(password)
    db.session.add(student)
    db.session.commit()

    flash(f"{name} 선수 계정이 생성되었습니다.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/student/<int:student_id>/edit")
@admin_required
def edit_student(student_id):
    student = db.session.get(User, student_id)
    if not student or student.role != "student":
        flash("선수를 찾을 수 없습니다.", "error")
        return redirect(url_for("admin_dashboard"))

    student.name = request.form.get("name", student.name).strip()
    student.team = request.form.get("team", student.team).strip()
    student.event = request.form.get("event", student.event).strip()
    new_password = request.form.get("password", "")
    if new_password:
        if len(new_password) < 6:
            flash("새 비밀번호는 6자 이상이어야 합니다.", "error")
            return redirect(url_for("admin_dashboard"))
        student.set_password(new_password)
    db.session.commit()
    flash("선수 정보가 수정되었습니다.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/student/<int:student_id>/toggle")
@admin_required
def toggle_student(student_id):
    student = db.session.get(User, student_id)
    if not student or student.role != "student":
        flash("선수를 찾을 수 없습니다.", "error")
        return redirect(url_for("admin_dashboard"))
    student.active = not student.active
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.get("/admin/export.csv")
@admin_required
def export_csv():
    start, end = get_range()
    rows = (
        WeightEntry.query.join(User)
        .filter(
            WeightEntry.entry_date.between(start, end),
            User.role == "student",
        )
        .order_by(WeightEntry.entry_date, User.name, WeightEntry.slot)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "선수", "아이디", "팀", "종목", "날짜",
        "구분", "체중(kg)", "저장시각"
    ])
    for e in rows:
        writer.writerow([
            e.student.name, e.student.username, e.student.team,
            e.student.event, e.entry_date.isoformat(),
            "아침" if e.slot == "morning" else "저녁",
            e.weight_kg, e.updated_at.strftime("%Y-%m-%d %H:%M"),
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=weight_{start}_{end}.csv"
        },
    )


@app.cli.command("init-db")
def init_db():
    db.create_all()
    admin_username = os.environ.get("ADMIN_USERNAME", "coach")
    admin_password = os.environ.get("ADMIN_PASSWORD", "CHANGE_ME_NOW")

    if User.query.filter_by(username=admin_username).first():
        print("DB가 이미 초기화되어 있습니다.")
        return

    admin = User(
        name="지도자",
        username=admin_username,
        role="admin",
    )
    admin.set_password(admin_password)
    db.session.add(admin)
    db.session.commit()
    print(f"관리자 생성 완료: {admin_username}")


@app.cli.command("send-reminders")
def send_reminders():
    """현재 시간대에 맞춰 미기록 선수에게 푸시 알림을 보냅니다.
    운영 서버에서는 cron/스케줄러로 1분~5분 간격 실행을 권장합니다.
    """
    now = datetime.now()
    # 기본 알림 시각: 08:00 / 20:00. 환경변수로 변경 가능.
    morning_hm = os.environ.get("MORNING_REMINDER", "08:00")
    evening_hm = os.environ.get("EVENING_REMINDER", "20:00")
    current_hm = now.strftime("%H:%M")

    slot = "morning" if current_hm == morning_hm else (
        "evening" if current_hm == evening_hm else None
    )
    if not slot:
        print("현재 알림 시각이 아닙니다.")
        return

    students = User.query.filter_by(role="student", active=True).all()
    title = "체중 기록 알림"
    label = "아침" if slot == "morning" else "저녁"

    sent = 0
    for student in students:
        exists = WeightEntry.query.filter_by(
            student_id=student.id, entry_date=date.today(), slot=slot
        ).first()
        if not exists:
            sent += send_push_to_user(
                student,
                title,
                f"{student.name} 선수, 오늘 {label} 체중을 기록해 주세요.",
                "/",
            )
    print(f"{label} 미기록 알림 발송: {sent}건")


@app.cli.command("generate-vapid")
def generate_vapid():
    try:
        from py_vapid import Vapid
    except ImportError:
        print("먼저 pip install py-vapid 를 실행하세요.")
        return
    v = Vapid()
    v.generate_keys()
    private = base64.urlsafe_b64encode(v.private_key.private_numbers().private_value.to_bytes(32, "big")).decode().rstrip("=")
    public = base64.urlsafe_b64encode(
        v.public_key.public_bytes_raw()
    ).decode().rstrip("=")
    print("VAPID_PUBLIC_KEY=" + public)
    print("VAPID_PRIVATE_KEY=" + private)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    user = current_user()
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if not user.check_password(current_pw):
            flash("현재 비밀번호가 올바르지 않습니다.", "error")
            return redirect(url_for("change_password"))

        if len(new_pw) < 6:
            flash("새 비밀번호는 6자 이상이어야 합니다.", "error")
            return redirect(url_for("change_password"))

        if new_pw != confirm_pw:
            flash("새 비밀번호 확인이 일치하지 않습니다.", "error")
            return redirect(url_for("change_password"))

        user.set_password(new_pw)
        db.session.commit()
        flash("비밀번호가 성공적으로 변경되었습니다.", "success")
        return redirect(url_for("index"))

    return render_template("change_password.html")
    
