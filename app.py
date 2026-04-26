from flask import Flask, request
import requests
import os
import json

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")

SHEET_API = "https://script.google.com/macros/s/AKfycbx3pzdi1iiC-He3UlNmDZJbacuoSUiBo5pedcU1zGnL3cE5y_SJD8Z6RRDnyhuw_9XG/exec"

GROUP_ID = "Cf1a0bd7a5507f3eea9bed99be40d2dfe"


def line_headers():
    return {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + CHANNEL_ACCESS_TOKEN
    }


def reply_to_line(reply_token, message):
    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=line_headers(),
        json={
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": message
                }
            ]
        }
    )


def push_line(to, message):
    requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers=line_headers(),
        json={
            "to": to,
            "messages": [
                {
                    "type": "text",
                    "text": message
                }
            ]
        }
    )


def parse_jsonp(text):
    return json.loads(text[text.find("(") + 1:text.rfind(")")])


def lookup_student(user_id):
    url = f"{SHEET_API}?action=lookup&userId={user_id}&callback=cb"
    res = requests.get(url)
    data = parse_jsonp(res.text)
    students = data.get("students", [])
    return students[0] if students else None


def add_pickup(student, parent_user_id):
    requests.get(
        SHEET_API,
        params={
            "action": "addPickup",
            "student_id": student.get("student_id", ""),
            "name": student.get("name", ""),
            "english_name": student.get("english_name", ""),
            "class_name": student.get("class_name", ""),
            "parent_user_id": parent_user_id,
            "parent_name": "",
            "status": "待處理",
            "callback": "cb"
        }
    )


def get_last_pickup():
    res = requests.get(
        SHEET_API,
        params={
            "action": "lastPickup",
            "callback": "cb"
        }
    )
    return parse_jsonp(res.text)


def update_pickup(row, status, reply):
    requests.get(
        SHEET_API,
        params={
            "action": "updatePickup",
            "row": row,
            "status": status,
            "reply": reply,
            "callback": "cb"
        }
    )


@app.route("/", methods=["GET"])
def home():
    return "PiXiE LINE webhook is running."


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json(silent=True) or {}
    print(json.dumps(body, ensure_ascii=False), flush=True)

    for event in body.get("events", []):
        if event.get("type") != "message":
            continue

        msg = event.get("message", {})
        if msg.get("type") != "text":
            continue

        text = msg.get("text", "").strip()
        reply_token = event.get("replyToken")
        source = event.get("source", {})
        source_type = source.get("type")
        user_id = source.get("userId")

        # 老師群組回覆 1~5
        if source_type == "group" and text in ["1", "2", "3", "4", "5"]:
            pickup = get_last_pickup()
            parent_id = pickup.get("parent_user_id", "")
            row = pickup.get("row", "")

            if not parent_id:
                reply_to_line(reply_token, "找不到最近一筆接送紀錄。")
                return "OK", 200

            status_map = {
                "1": "收拾書包中",
                "2": "作業未完成",
                "3": "準備下樓",
                "4": "老師確認中",
                "5": "已接走"
            }

            reply_map = {
                "1": "家長您好，孩子正在收拾書包中，請稍候一下。",
                "2": "家長您好，孩子作業尚未完成，約需再 5–10 分鐘，完成後會協助孩子準備下樓。",
                "3": "家長您好，孩子已準備下樓，請稍候。",
                "4": "家長您好，老師正在確認孩子狀況，請稍候一下。",
                "5": "孩子已完成接送登記，謝謝您。"
            }

            status = status_map[text]
            reply_message = reply_map[text]

            push_line(parent_id, reply_message)
            update_pickup(row, status, reply_message)

            reply_to_line(reply_token, "已通知家長：" + status)

            return "OK", 200

        # 家長私訊：接小孩
        if source_type == "user" and "接" in text:
            student = lookup_student(user_id)

            if not student:
                reply_to_line(reply_token, "尚未綁定學生，請先完成家長綁定。")
                return "OK", 200

            add_pickup(student, user_id)

            name = student.get("name", "")
            english = student.get("english_name", "")
            class_name = student.get("class_name", "")

            # 不先回家長，等老師按 1~5 才回
            push_line(
                GROUP_ID,
                "🚗【接送通知】\n\n"
                f"學生：{name} {english}\n"
                f"班級：{class_name}\n\n"
                "請老師回覆數字：\n"
                "1️⃣ 收拾書包中\n"
                "2️⃣ 作業未完成，還需 5–10 分鐘\n"
                "3️⃣ 準備下樓\n"
                "4️⃣ 老師確認中\n"
                "5️⃣ 已接走"
            )

            return "OK", 200

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
