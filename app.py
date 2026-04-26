from flask import Flask, request
import requests
import os
import json

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")

SHEET_API = "https://script.google.com/macros/s/AKfycbx3pzdi1iiC-He3UlNmDZJbacuoSUiBo5pedcU1zGnL3cE5y_SJD8Z6RRDnyhuw_9XG/exec"

GROUP_ID = "Cf1a0bd7a5507f3eea9bed99be40d2dfe"


def reply_to_line(reply_token, message):
    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + CHANNEL_ACCESS_TOKEN
        },
        json={
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": message}]
        }
    )


def push_to_group(message):
    requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + CHANNEL_ACCESS_TOKEN
        },
        json={
            "to": GROUP_ID,
            "messages": [{"type": "text", "text": message}]
        }
    )


def lookup_student(user_id):
    url = f"{SHEET_API}?action=lookup&userId={user_id}&callback=cb"

    try:
        res = requests.get(url)
        text = res.text

        json_text = text[text.find("(")+1:text.rfind(")")]
        data = json.loads(json_text)

        students = data.get("students", [])

        return students[0] if students else None

    except Exception as e:
        print("lookup error:", e)
        return None


@app.route("/", methods=["GET"])
def home():
    return "PiXiE LINE webhook is running."


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json(silent=True) or {}

    print("======收到LINE事件======")
    print(json.dumps(body, indent=2))

    for event in body.get("events", []):

        if event.get("type") != "message":
            continue

        message = event.get("message", {})

        if message.get("type") != "text":
            continue

        text = message.get("text", "").strip()

        print("收到文字:", text)

        reply_token = event.get("replyToken")
        user_id = event.get("source", {}).get("userId")

        # 只要包含「接」就觸發
        if "接" in text:

            student = lookup_student(user_id)

            if not student:
                reply_to_line(
                    reply_token,
                    "尚未綁定學生，請先完成家長綁定。"
                )
                return "OK", 200

            name = student.get("name", "")
            english = student.get("english_name", "")
            class_name = student.get("class_name", "")

            reply_to_line(
                reply_token,
                f"已收到接送通知：{name} {english}"
            )

            push_to_group(
                f"🚗【接送通知】\n\n"
                f"學生：{name} {english}\n"
                f"班級：{class_name}\n\n"
                f"請選擇回覆：\n"
                f"1️⃣ 收拾書包中\n"
                f"2️⃣ 作業未完成，還需 5–10 分鐘\n"
                f"3️⃣ 準備下樓\n"
                f"4️⃣ 老師確認中\n"
                f"5️⃣ 已接走"
            )

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
