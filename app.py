import os
import csv
import json
import requests
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

STUDENTS_FILE = "students.csv"

pickup_queue = []


# =========================
# 讀取學生名單
# =========================
def load_students():
    students = []

    if not os.path.exists(STUDENTS_FILE):
        print("找不到 students.csv")
        return students

    with open(STUDENTS_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            name = (
                row.get("學生姓名")
                or row.get("name")
                or row.get("student_name")
                or ""
            ).strip()

            if name:
                students.append({
                    "student_id": row.get("student_id", "").strip(),
                    "name": name,
                    "english_name": row.get("英文姓名", "").strip(),
                    "grade": row.get("年級", "").strip(),
                    "class": row.get("班級", "").strip(),
                    "parent_name": row.get("家長姓名", "").strip(),
                    "line_name": row.get("家長LINE名稱", "").strip(),
                    "pickup_method": row.get("接送方式", "").strip(),
                    "note": row.get("備註", "").strip(),
                })

    return students


# =========================
# LINE 主動推播
# =========================
def push_to_line(user_id, message):
    if not CHANNEL_ACCESS_TOKEN:
        print("缺少 LINE_CHANNEL_ACCESS_TOKEN")
        return

    url = "https://api.line.me/v2/bot/message/push"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
    }

    data = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    r = requests.post(url, headers=headers, data=json.dumps(data))
    print("LINE push status:", r.status_code, r.text)


# =========================
# 首頁
# =========================
@app.route("/")
def home():
    return "PiXiE 接送系統運作中"


# =========================
# 叫號板頁面
# =========================
@app.route("/board")
def board():
    return render_template("board.html")


# =========================
# 給叫號板抓目前接送名單
# =========================
@app.route("/api/queue")
def api_queue():
    return jsonify(pickup_queue)


# =========================
# 老師按叫號
# =========================
@app.route("/api/call/<int:index>", methods=["POST"])
def call_student(index):
    if index < 0 or index >= len(pickup_queue):
        return jsonify({
            "success": False,
            "message": "沒有這個號碼"
        })

    item = pickup_queue[index]
    student_name = item["student_name"]
    user_id = item["user_id"]

    message = f"老師已叫號：{student_name}，請準備到門口接送。"

    if user_id:
        push_to_line(user_id, message)

    pickup_queue.pop(index)

    return jsonify({
        "success": True,
        "student_name": student_name,
        "message": message
    })


# =========================
# 清空接送名單
# =========================
@app.route("/api/clear", methods=["POST"])
def clear_queue():
    pickup_queue.clear()
    return jsonify({
        "success": True,
        "message": "已清空接送名單"
    })


# =========================
# LINE Webhook
# =========================
@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json()
    print("收到 LINE webhook：", body)

    if not body:
        return "OK"

    events = body.get("events", [])

    students = load_students()

    for event in events:
        if event.get("type") != "message":
            continue

        message = event.get("message", {})
        if message.get("type") != "text":
            continue

        text = message.get("text", "").strip()

        source = event.get("source", {})
        user_id = source.get("userId", "")

        # =========================
        # 家長傳「接學生姓名」
        # 只加入接送名單
        # 不自動回覆任何訊息
        # =========================
        if "接" in text:
            matched_student = None

            for student in students:
                if student["name"] in text:
                    matched_student = student
                    break

            if matched_student:
                already_exists = any(
                    item["student_name"] == matched_student["name"]
                    for item in pickup_queue
                )

                if not already_exists:
                    pickup_queue.append({
                        "student_name": matched_student["name"],
                        "english_name": matched_student.get("english_name", ""),
                        "user_id": user_id,
                        "text": text
                    })

                    print(f"已加入接送名單：{matched_student['name']}")
                else:
                    print(f"重複接送通知，已略過：{matched_student['name']}")

            else:
                print("有接送關鍵字，但找不到學生姓名：", text)

        # 其他訊息一律不回覆
        # 不寫 reply_to_line
        # 不寫「已收到接送通知」

    return "OK"


# =========================
# 啟動
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
