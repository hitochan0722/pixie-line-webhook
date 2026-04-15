from flask import Flask, request
import os
import requests

app = Flask(__name__)

students = [
    "彭禹哲",
    "彭禹誠",
    "許書寧",
    "李紹麒",
    "姚行謙"
]

pickup_queue = []

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "")

@app.route("/", methods=["GET"])
def home():
    return "Pixie LINE Webhook Running"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print("收到 webhook:", data)

    if "events" in data:
        for event in data["events"]:
            if event.get("type") == "message" and event["message"].get("type") == "text":
                text = event["message"]["text"].strip()
                reply_token = event.get("replyToken")
                print(f"收到文字訊息: {text}")

                matched_student = None
                for name in students:
                    if name in text:
                        matched_student = name
                        pickup_queue.append(name)
                        print(f"家長接送：{name}")
                        break

                if reply_token and CHANNEL_ACCESS_TOKEN:
                    if matched_student:
                        reply_message = f"已收到接送通知，{matched_student}準備放學中。"
                    else:
                        reply_message = "已收到您的訊息。"

                    reply_to_line(reply_token, reply_message)

    return "OK", 200

def reply_to_line(reply_token, text):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
    }

    response = requests.post(url, headers=headers, json=payload)
    print("LINE 回覆結果:", response.status_code, response.text)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
