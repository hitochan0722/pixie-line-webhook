from flask import Flask, request, jsonify, render_template
import csv
import json
import requests
import os

app = Flask(__name__)

# LINE 設定
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")

students = []
pickup_queue = []

GROUP_ID = None

# 讀取學生名單
def load_students():
    global students
    students = []

    try:
        with open("students.csv", newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                students.append(row["學生姓名"])
    except:
        print("students.csv 讀取失敗")

load_students()

# 發送 LINE 訊息
def push_group_message(text):

    global GROUP_ID

    if not GROUP_ID:
        print("⚠️ 尚未取得 GROUP_ID")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    data = {
        "to": GROUP_ID,
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
    }

    requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers=headers,
        data=json.dumps(data)
    )

@app.route("/")
def home():
    return "Webhook running"

# LINE webhook
@app.route("/webhook", methods=["POST"])
def webhook():

    global GROUP_ID

    body = request.get_json()

    print("收到 webhook")

    if "events" in body:

        for event in body["events"]:

            # 抓群組ID
            if event["source"]["type"] == "group":

                GROUP_ID = event["source"]["groupId"]

                print("GROUP ID =", GROUP_ID)

            # 處理文字訊息
            if event["type"] == "message":

                if event["message"]["type"] == "text":

                    text = event["message"]["text"]

                    for name in students:

                        if name in text and "接" in text:

                            pickup_queue.append(name)

                            print("加入接送：", name)

    return "OK"

# 取得接送名單
@app.route("/api/pickups")
def get_pickups():
    return jsonify(pickup_queue)

# 叫號
@app.route("/api/call/<name>", methods=["POST"])
def call_student(name):

    if name in pickup_queue:
        pickup_queue.remove(name)

    message = f"{name}請到門口"

    print("叫號：", message)

    push_group_message(message)

    return "OK"

# 看板
@app.route("/board")
def board():
    return render_template("board.html")

if __name__ == "__main__":
    app.run()
