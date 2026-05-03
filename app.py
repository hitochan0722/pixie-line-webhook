from flask import Flask, request, jsonify, render_template
import os, csv, requests
from datetime import datetime

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or os.getenv("CHANNEL_ACCESS_TOKEN")
TEACHER_GROUP_ID = os.getenv("TEACHER_GROUP_ID")
STUDENTS_FILE = "students.csv"

pickup_queue = []
pickup_records = {}

# ========================
# LINE 工具
# ========================

def line_headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

def reply_to_line(reply_token, text):
    if not reply_token:
        return
    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=line_headers(),
        json={
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}]
        }
    )

def push_to_line(to, messages):
    if not to:
        return

    requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers=line_headers(),
        json={
            "to": to,
            "messages": messages
        }
    )

# ========================
# 學生資料
# ========================

def load_students():
    if not os.path.exists(STUDENTS_FILE):
        return []

    with open(STUDENTS_FILE, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def get_student_name(student):
    return (
        student.get("學生姓名")
        or student.get("student_name")
        or ""
    ).strip()

def find_student(text, user_id):
    students = load_students()

    for s in students:
        name = get_student_name(s)

        parent_id = (
            s.get("parent_user_id")
            or s.get("家長LINE_ID")
            or ""
        ).strip()

        if parent_id and parent_id == user_id:
            return s

        if name and name in text:
            return s

    return None

# ========================
# 接送系統
# ========================

def add_pickup(student_name, parent_user_id):
    now = datetime.now().strftime("%H:%M:%S")

    record_id = f"{student_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    item = {
        "id": record_id,
        "student_name": student_name,
        "parent_user_id": parent_user_id,
        "time": now,
        "played": False
    }

    pickup_queue.append(item)
    pickup_records[record_id] = item

    return item

def notify_teacher(item):

    student_name = item["student_name"]
    record_id = item["id"]

    message = {
        "type": "template",
        "altText": f"{student_name} 接送通知",
        "template": {
            "type": "buttons",
            "title": "接送通知",
            "text": f"{student_name} 家長已到",
            "actions": [
                {"type": "postback", "label": "收拾書包", "data": f"action=packing&id={record_id}"},
                {"type": "postback", "label": "5–10分鐘", "data": f"action=wait&id={record_id}"},
                {"type": "postback", "label": "已下樓", "data": f"action=down&id={record_id}"},
                {"type": "postback", "label": "取消", "data": f"action=cancel&id={record_id}"}
            ]
        }
    }

    push_to_line(TEACHER_GROUP_ID, [message])

# ========================
# LINE webhook
# ========================

@app.route("/callback", methods=["POST"])
def callback():

    body = request.get_json()

    events = body.get("events", [])

    for event in events:

        event_type = event.get("type")
        reply_token = event.get("replyToken")

        source = event.get("source", {})
        user_id = source.get("userId")

        if event_type == "message":

            message = event.get("message", {})
            text = message.get("text", "").strip()

            if text.startswith("接"):

                student = find_student(text, user_id)

                if not student:
                    reply_to_line(
                        reply_token,
                        "請輸入：接＋學生姓名"
                    )
                    continue

                student_name = get_student_name(student)

                item = add_pickup(student_name, user_id)

                notify_teacher(item)

                reply_to_line(
                    reply_token,
                    f"已收到 {student_name} 接送通知"
                )

    return "OK"

# ========================
# API
# ========================

@app.route("/api/pickup")
def api_pickup():

    new_items = []

    for item in pickup_queue:
        if not item.get("played"):
            new_items.append(item)
            item["played"] = True

    return jsonify(new_items)

# ========================
# 頁面 routes
# ========================

@app.route("/")
def home():
    return "PIXIE PICKUP SYSTEM RUNNING"

@app.route("/parent")
def parent_page():
    return render_template("parent.html")

@app.route("/parent/pickup")
def parent_pickup_page():
    return render_template("pickup.html")

@app.route("/parent/leave")
def parent_leave_page():
    return render_template("leave.html")

@app.route("/parent/attendance")
def parent_attendance_page():
    return render_template("attendance.html")

@app.route("/contact")
def contact_page():
    return render_template("contact.html")

@app.route("/new-student")
def new_student():
    return render_template("new-student.html")

# ========================
# 新生問班送出
# ========================

@app.route("/new-student-submit", methods=["POST"])
def new_student_submit():

    student_name = request.form.get("student_name", "")
    school = request.form.get("school", "")
    learning_experience = request.form.get("learning_experience", "")
    parent_name = request.form.get("parent_name", "")
    phone = request.form.get("phone", "")

    data = {
        "form_type": "new_student",
        "student_name": student_name,
        "school": school,
        "learning_experience": learning_experience,
        "parent_name": parent_name,
        "phone": phone,
        "source": "新生入口"
    }

    # 傳 Google Sheet

    gas_url = os.getenv("NEW_STUDENT_GAS_URL")

    if gas_url:
        try:
            requests.post(gas_url, json=data, timeout=10)
        except Exception as e:
            print("Sheet 寫入失敗:", e)

    # 傳 LINE 群組

    message = f"""📩 新生問班資料

學生姓名：{student_name}
就讀學校：{school}
學習經歷：{learning_experience}
家長姓名：{parent_name}
電話：{phone}"""

    push_to_line(
        TEACHER_GROUP_ID,
        [{"type": "text", "text": message}]
    )

    return """
    <html>
    <body style="font-family:Arial; text-align:center; padding:40px;">
      <h2>資料已送出</h2>
      <p>謝謝您填寫問班資料，老師會盡快與您聯繫。</p>
    </body>
    </html>
    """

@app.route("/version")
def version():
    return "PIXIE PICKUP EMBEDDED BOARD VERSION"

# ========================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
