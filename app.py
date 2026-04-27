import os
import csv
import json
import requests
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
TEACHER_GROUP_ID = os.getenv("TEACHER_GROUP_ID", "")

STUDENTS_FILE = "students.csv"
pickup_queue = []


def load_students():
    students = []

    if not os.path.exists(STUDENTS_FILE):
        print("❌ 找不到 students.csv")
        return students

    with open(STUDENTS_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            name = row.get("學生姓名", "").strip()
            english_name = row.get("英文姓名", "").strip()
            class_name = row.get("班級", "").strip()

            if name:
                students.append({
                    "name": name,
                    "english_name": english_name,
                    "class_name": class_name
                })

    print(f"📋 載入學生數量：{len(students)}")
    return students


def push_to_line(to_id, message):
    print("📤 準備發送 LINE")
    print("to_id:", to_id)
    print("message:", message)

    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("❌ 沒有 LINE_CHANNEL_ACCESS_TOKEN")
        return False

    if not to_id:
        print("❌ 沒有 to_id")
        return False

    url = "https://api.line.me/v2/bot/message/push"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }

    data = {
        "to": to_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    r = requests.post(url, headers=headers, data=json.dumps(data))

    print("📨 LINE push status:", r.status_code)
    print("📨 LINE push response:", r.text)

    return r.status_code == 200


@app.route("/")
def home():
    return "PiXiE 接送系統 V12 運作中"


@app.route("/board")
def board():
    return render_template("board.html")


@app.route("/api/queue")
def api_queue():
    return jsonify(pickup_queue)


@app.route("/api/call/<int:index>", methods=["POST"])
def call_student(index):
    print("🔔 收到叫號")

    if index < 0 or index >= len(pickup_queue):
        print("❌ index 錯誤")
        return jsonify({"success": False, "message": "index error"})

    item = pickup_queue[index]

    student_name = item["student_name"]
    user_id = item["user_id"]

    print("👦 叫號學生:", student_name)
    print("🆔 家長 user_id:", user_id)

    parent_message = f"老師已叫號：{student_name}，請準備到門口接送。"

    if user_id:
        push_to_line(user_id, parent_message)
    else:
        print("❌ 沒有家長 user_id，無法通知家長")

    pickup_queue.pop(index)

    return jsonify({
        "success": True,
        "student_name": student_name
    })


@app.route("/api/clear", methods=["POST"])
def clear_queue():
    pickup_queue.clear()
    print("🧹 已清空 queue")
    return jsonify({"success": True})


@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json()

    print("📩 收到 LINE webhook")
    print(json.dumps(body, ensure_ascii=False))

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
        group_id = source.get("groupId", "")
        source_type = source.get("type", "")

        print("📨 收到訊息:", text)
        print("來源類型:", source_type)
        print("🆔 user_id:", user_id)
        print("👥 group_id:", group_id)

        # 家長私訊官方帳號：「接學生姓名」
        # 只加入看板 + 通知老師群組
        # 不回覆家長
        if "接" in text:
            matched_student = None

            for student in students:
                if student["name"] in text:
                    matched_student = student
                    break

            if matched_student:
                student_name = matched_student["name"]
                english_name = matched_student.get("english_name", "")
                class_name = matched_student.get("class_name", "")

                print("✅ 找到學生:", student_name)

                already_exists = any(
                    item["student_name"] == student_name
                    for item in pickup_queue
                )

                if not already_exists:
                    pickup_queue.append({
                        "student_name": student_name,
                        "english_name": english_name,
                        "class_name": class_name,
                        "user_id": user_id
                    })

                    print("📥 加入 queue:", student_name)

                    if TEACHER_GROUP_ID:
                        teacher_message = (
                            f"📢 接送通知\n"
                            f"學生：{student_name} {english_name}\n"
                            f"班級：{class_name if class_name else '未填'}\n"
                            f"請老師到接送看板確認叫號。"
                        )
                        push_to_line(TEACHER_GROUP_ID, teacher_message)
                    else:
                        print("⚠️ 尚未設定 TEACHER_GROUP_ID，無法通知老師群組")

                else:
                    print("⚠️ 已存在 queue，不重複加入")

            else:
                print("❌ 找不到學生:", text)

    return "OK"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
