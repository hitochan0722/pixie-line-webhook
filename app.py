from flask import Flask, request, jsonify
import os
import csv
import requests
from datetime import datetime

app = Flask(__name__)

print("===== PIXIE FINAL STABLE VERSION =====")

# 讀取正確 TOKEN（支援兩種名稱）
CHANNEL_ACCESS_TOKEN = (
    os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    or os.getenv("CHANNEL_ACCESS_TOKEN")
)

TEACHER_GROUP_ID = os.getenv("TEACHER_GROUP_ID")

STUDENTS_FILE = "students.csv"

pickup_queue = []
pickup_records = {}

# ===============================
# LINE 基本函式
# ===============================

def line_headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

def reply_to_line(reply_token, text):
    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=line_headers(),
        json={
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}]
        }
    )

def push_to_line(to, messages):
    print("PUSH TO:", to)

    res = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers=line_headers(),
        json={
            "to": to,
            "messages": messages
        }
    )

    print("PUSH STATUS:", res.status_code)
    print("PUSH RESPONSE:", res.text)

# ===============================
# 學生資料
# ===============================

def load_students():
    students = []

    if not os.path.exists(STUDENTS_FILE):
        return students

    with open(STUDENTS_FILE, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            students.append(row)

    return students

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
        )

        if parent_id == user_id:
            return s

        if name in text:
            return s

    return None

# ===============================
# 新增接送
# ===============================

def add_pickup(student_name, parent_id):

    now = datetime.now().strftime("%H:%M:%S")

    record_id = (
        student_name
        + "_"
        + datetime.now().strftime("%Y%m%d%H%M%S")
    )

    item = {
        "id": record_id,
        "student_name": student_name,
        "parent_user_id": parent_id,
        "time": now,
        "played": False
    }

    pickup_queue.append(item)
    pickup_records[record_id] = item

    return item

# ===============================
# 通知老師群
# ===============================

def notify_teacher(item):

    if not TEACHER_GROUP_ID:
        print("NO GROUP ID")
        return

    student_name = item["student_name"]
    record_id = item["id"]

    message = {
        "type": "template",
        "altText": "接送通知",
        "template": {
            "type": "buttons",
            "title": "接送通知",
            "text": f"{student_name} 家長已到\n系統已自動廣播3次",
            "actions": [
                {
                    "type": "postback",
                    "label": "收拾書包",
                    "data": f"action=packing&id={record_id}"
                },
                {
                    "type": "postback",
                    "label": "5–10分鐘",
                    "data": f"action=wait&id={record_id}"
                },
                {
                    "type": "postback",
                    "label": "已下樓",
                    "data": f"action=down&id={record_id}"
                },
                {
                    "type": "postback",
                    "label": "取消",
                    "data": f"action=cancel&id={record_id}"
                }
            ]
        }
    }

    push_to_line(TEACHER_GROUP_ID, [message])

# ===============================
# 老師回報
# ===============================

def handle_postback(event):

    reply_token = event["replyToken"]

    data = event["postback"]["data"]

    params = {}

    for p in data.split("&"):
        k, v = p.split("=")
        params[k] = v

    action = params["action"]
    record_id = params["id"]

    item = pickup_records.get(record_id)

    if not item:
        reply_to_line(reply_token, "找不到資料")
        return

    student_name = item["student_name"]
    parent_id = item["parent_user_id"]

    if action == "packing":
        msg = "正在收拾書包"

    elif action == "wait":
        msg = "約5–10分鐘"

    elif action == "down":
        msg = "已經下樓"

    elif action == "cancel":
        msg = "接送已取消"

    else:
        msg = "狀態更新"

    push_to_line(
        parent_id,
        [{"type": "text", "text":
         f"{student_name} {msg}"}]
    )

    reply_to_line(
        reply_token,
        f"已通知家長：{student_name} {msg}"
    )

# ===============================
# LINE webhook
# ===============================

@app.route("/callback", methods=["POST"])
def callback():

    body = request.get_json()

    events = body["events"]

    for event in events:

        if event["type"] == "message":

            text = (
                event["message"]
                .get("text", "")
            )

            reply_token = event["replyToken"]

            user_id = (
                event["source"]
                .get("userId")
            )

            if text.startswith("接"):

                student = find_student(
                    text,
                    user_id
                )

                if not student:

                    reply_to_line(
                        reply_token,
                        "找不到學生"
                    )
                    continue

                name = get_student_name(student)

                item = add_pickup(
                    name,
                    user_id
                )

                notify_teacher(item)

                reply_to_line(
                    reply_token,
                    f"已收到 {name} 接送通知"
                )

        elif event["type"] == "postback":

            handle_postback(event)

    return "OK"

# ===============================
# API
# ===============================

@app.route("/api/pickup")
def api_pickup():

    new_items = []

    for item in pickup_queue:

        if not item["played"]:

            new_items.append(item)

            item["played"] = True

    return jsonify(new_items)

# ===============================
# 測試
# ===============================

@app.route("/test-pickup")
def test_pickup():

    item = add_pickup(
        "賴灝宇",
        "test"
    )

    notify_teacher(item)

    return "TEST OK"

# ===============================
# 看板
# ===============================

@app.route("/board")
def board():

    return open("board.html").read()

# ===============================
# 啟動
# ===============================

@app.route("/")
def home():
    return "PIXIE FINAL RUNNING"

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
