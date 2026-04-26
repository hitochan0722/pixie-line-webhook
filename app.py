from flask import Flask, request, jsonify
import requests
import os
import json
import csv
import urllib.parse

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")

# Google Sheet API URL（你原本的）
SHEET_API = "https://script.google.com/macros/s/AKfycbxxxx/exec"

# 老師群組ID（你之前抓到的）
GROUP_ID = "Cf1a0bd7a5507f3eea9bed99be40d2dfe"


# =========================
# 回覆 LINE 訊息
# =========================

def reply_to_line(reply_token, message):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    data = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=headers,
        json=data
    )


# =========================
# 推送群組（老師）
# =========================

def push_to_group(student_name, english_name):

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    message = f"""🚗【接送通知】

學生：
{student_name} {english_name}

請選擇狀態：
1️⃣ 收拾書包中
2️⃣ 作業未完成
3️⃣ 準備下樓
4️⃣ 老師確認中
5️⃣ 已接走
"""

    data = {
        "to": GROUP_ID,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers=headers,
        json=data
    )


# =========================
# 查學生
# =========================

def lookup_student(user_id):

    url = f"{SHEET_API}?action=lookup&userId={user_id}&callback=cb"

    res = requests.get(url)

    text = res.text

    json_text = text[text.find("(")+1:text.rfind(")")]

    data = json.loads(json_text)

    if data["students"]:
        return data["students"][0]

    return None


# =========================
# webhook
# =========================

@app.route("/webhook", methods=["POST"])
def webhook():

    body = request.get_json()

    events = body.get("events", [])

    for event in events:

        if event["type"] == "message":

            text = event["message"]["text"]

            reply_token = event["replyToken"]

            user_id = event["source"]["userId"]

            # =========================
            # 家長：接小孩
            # =========================

            if "接" in text:

                student = lookup_student(user_id)

                if not student:

                    reply_to_line(
                        reply_token,
                        "尚未綁定學生，請先完成綁定。"
                    )

                    return "ok"

                name = student["name"]

                english = student["english_name"]

                # 回家長

                reply_to_line(
                    reply_token,
                    f"已收到接送通知：{name} {english}"
                )

                # 通知老師

                push_to_group(name, english)

                return "ok"

    return "ok"


@app.route("/", methods=["GET"])
def home():
    return "Pixie webhook running"
