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
        print("沒有 TEACHER_GROUP_ID，無法推送 LINE 群組")
        return

    if not CHANNEL_ACCESS_TOKEN:
        print("沒有 LINE CHANNEL ACCESS TOKEN，無法推送 LINE")
        return

    r = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers=line_headers(),
        json={
            "to": to,
            "messages": messages
        }
    )

    print("LINE push status:", r.status_code, r.text)

# ========================
# 學生資料
# ========================

def load_students():
    if not os.path.exists(STUDENTS_FILE):
        return []

    with open(STUDENTS_FILE, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def save_students(students):
    fieldnames = [
        "student_id",
        "學生姓名",
        "英文姓名",
        "年級",
        "班級",
        "家長ID1",
        "家長ID2",
        "家長姓名",
        "家長LINE名稱",
        "接送方式",
        "備註"
    ]

    with open(STUDENTS_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(students)

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

        parent_id_1 = s.get("家長ID1", "").strip()
        parent_id_2 = s.get("家長ID2", "").strip()

        if user_id and (user_id == parent_id_1 or user_id == parent_id_2):
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
                    reply_to_line(reply_token, "請輸入：接＋學生姓名")
                    continue

                student_name = get_student_name(student)

                item = add_pickup(student_name, user_id)
                notify_teacher(item)

                reply_to_line(reply_token, f"已收到 {student_name} 接送通知")

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

@app.route("/api/bind-student")
def api_bind_student():
    student_id = request.args.get("student_id", "").strip()

    students = load_students()

    for s in students:
        if s.get("student_id", "").strip() == student_id:
            return jsonify({
                "ok": True,
                "student_name": s.get("學生姓名", ""),
                "english_name": s.get("英文姓名", ""),
                "grade": s.get("年級", ""),
                "class_name": s.get("班級", "")
            })

    return jsonify({
        "ok": False,
        "message": "找不到學生資料，請聯絡老師。"
    })

@app.route("/api/bind-confirm", methods=["POST"])
def api_bind_confirm():
    data = request.get_json() or {}

    student_id = (
        data.get("student_id")
        or data.get("bind")
        or data.get("student")
        or ""
    ).strip()

    line_user_id = (
        data.get("line_user_id")
        or data.get("userId")
        or ""
    ).strip()

    print("收到綁定資料 student_id =", student_id)
    print("收到綁定資料 line_user_id =", line_user_id)

    if not student_id:
        return jsonify({
            "ok": False,
            "message": "缺少學生代碼，請重新開啟連結。"
        })

    if not line_user_id:
        return jsonify({
            "ok": False,
            "message": "無法取得 LINE 身分，請用 LINE 開啟連結。"
        })

    students = load_students()

    for s in students:
        sid = (
            s.get("student_id")
            or s.get("學生ID")
            or s.get("學生代碼")
            or ""
        ).strip()

        if sid == student_id:
            if "家長ID1" not in s:
                s["家長ID1"] = ""

            if "家長ID2" not in s:
                s["家長ID2"] = ""

            id1 = s.get("家長ID1", "").strip()
            id2 = s.get("家長ID2", "").strip()

            if line_user_id == id1 or line_user_id == id2:
                return jsonify({
                    "ok": True,
                    "message": "此家長已完成綁定。"
                })

            if not id1:
                s["家長ID1"] = line_user_id
                save_students(students)
                return jsonify({
                    "ok": True,
                    "message": "綁定成功！之後即可使用家長專區。"
                })

            if not id2:
                s["家長ID2"] = line_user_id
                save_students(students)
                return jsonify({
                    "ok": True,
                    "message": "綁定成功！之後即可使用家長專區。"
                })

            return jsonify({
                "ok": False,
                "message": "此學生已綁定兩位家長，請聯絡老師。"
            })

    return jsonify({
        "ok": False,
        "message": f"找不到學生代碼：{student_id}，請聯絡老師。"
    })

# ========================
# 頁面 routes
# ========================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/parent")
def parent_page():
    return render_template("parent.html")

@app.route("/new-parent")
def new_parent_page():
    return render_template("new-parent.html")

@app.route("/bind")
def bind_page():
    return render_template("bind.html")

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

@app.route("/parent/new-student")
def parent_new_student_page():
    return render_template("new-student.html")

# ========================
# 新生問班送出
# ========================

@app.route("/parent/new-student-submit", methods=["POST"])
def parent_new_student_submit():
    student_name = request.form.get("student_name", "").strip()
    school = request.form.get("school", "").strip()
    learning_experience = request.form.get("learning_experience", "").strip()
    parent_name = request.form.get("parent_name", "").strip()
    phone = request.form.get("phone", "").strip()

    data = {
        "form_type": "new_student",
        "student_name": student_name,
        "school": school,
        "learning_experience": learning_experience,
        "parent_name": parent_name,
        "phone": phone,
        "source": "新生入口",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    gas_url = os.getenv("NEW_STUDENT_GAS_URL")

    if gas_url:
        try:
            r = requests.post(gas_url, json=data, timeout=10)
            print("新生 Sheet status:", r.status_code, r.text)
        except Exception as e:
            print("新生 Sheet 寫入失敗:", e)
    else:
        print("沒有設定 NEW_STUDENT_GAS_URL，所以沒有寫入 Sheet")

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
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family:'Microsoft JhengHei',Arial; text-align:center; padding:40px; background:#fff7ef;">
      <div style="background:white; border-radius:22px; padding:30px 20px; max-width:480px; margin:0 auto; box-shadow:0 8px 24px rgba(0,0,0,0.08);">
        <h2 style="color:#e28a4f;">資料已送出</h2>
        <p style="font-size:18px; line-height:1.7;">謝謝您填寫問班資料，老師會盡快與您聯繫。</p>
        <a href="/new-parent" style="display:inline-block; margin-top:18px; background:#e28a4f; color:white; padding:12px 22px; border-radius:16px; text-decoration:none; font-weight:bold;">回新生專區</a>
      </div>
    </body>
    </html>
    """

@app.route("/version")
def version():
    return "PIXIE PICKUP + NEW STUDENT + BIND VERSION"

# ========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
