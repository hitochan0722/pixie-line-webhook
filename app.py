from flask import Flask, request, jsonify, render_template
import os
import csv
import json
from datetime import datetime, date
import requests

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "")

CSV_STUDENTS = "students.csv"
CSV_PICKUPS = "pickups.csv"
CSV_LEAVES = "leaves.csv"


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_text():
    return date.today().strftime("%Y-%m-%d")


def ensure_csv(path, headers):
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, headers, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def append_csv(path, headers, row):
    ensure_csv(path, headers)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writerow(row)


def load_students():
    ensure_csv(CSV_STUDENTS, [
        "student_id",
        "學生姓名",
        "英文姓名",
        "年級",
        "班級",
        "家長姓名",
        "家長LINE名稱",
        "接送方式",
        "備註"
    ])
    return read_csv(CSV_STUDENTS)


def find_student(text):
    students = load_students()
    for s in students:
        name = s.get("學生姓名", "").strip()
        english = s.get("英文姓名", "").strip()

        if name and name in text:
            return s

        if english and english.lower() in text.lower():
            return s

    return None


def reply_to_line(reply_token, message):
    if not CHANNEL_ACCESS_TOKEN or not reply_token:
        return

    url = "https://api.line.me/v2/bot/message/reply"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    body = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    requests.post(url, headers=headers, data=json.dumps(body))


def push_to_line(user_id, message):
    if not CHANNEL_ACCESS_TOKEN or not user_id:
        return

    url = "https://api.line.me/v2/bot/message/push"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    body = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    requests.post(url, headers=headers, data=json.dumps(body))


@app.route("/")
def home():
    return "PiXiE V9 接送叫號看板 + 請假統計系統已啟動"


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    events = data.get("events", [])

    for event in events:
        if event.get("type") != "message":
            continue

        message = event.get("message", {})

        if message.get("type") != "text":
            continue

        text = message.get("text", "").strip()
        text_clean = text.replace(" ", "").replace("　", "")

        reply_token = event.get("replyToken", "")
        source = event.get("source", {})
        user_id = source.get("userId", "")

        student = find_student(text_clean)

        # =========================
        # 老師手動通知 1~5
        # =========================

        if text_clean in ["1", "2", "3", "4", "5"]:

            message_map = {
                "1": "孩子準備中，請稍候。",
                "2": "孩子正在下樓。",
                "3": "請到門口接孩子。",
                "4": "目前接送人數較多，請稍等一下。",
                "5": "已完成接送，謝謝。"
            }

            rows = read_csv(CSV_PICKUPS)

            target = None

            for r in rows:
                if r.get("狀態") != "已完成":
                    target = r
                    break

            if target:
                parent_line_id = target.get("家長LINE_ID", "")
                student_name = target.get("學生姓名", "")
                notify_text = f"{student_name}：{message_map[text_clean]}"

                push_to_line(parent_line_id, notify_text)

                if text_clean == "5":
                    target["狀態"] = "已完成"
                    target["完成時間"] = now_text()
                else:
                    target["狀態"] = f"已通知{ text_clean }"

                write_csv(CSV_PICKUPS, [
                    "id",
                    "student_id",
                    "學生姓名",
                    "英文姓名",
                    "班級",
                    "家長LINE_ID",
                    "狀態",
                    "通知時間",
                    "完成時間"
                ], rows)

                reply_to_line(reply_token, f"已通知家長：{student_name}")

            else:
                reply_to_line(reply_token, "目前看板沒有等待接送的學生。")

            continue

        # =========================
        # 家長接送：不自動回覆，只加入看板
        # =========================

        if "接" in text_clean and student:

            headers = [
                "id",
                "student_id",
                "學生姓名",
                "英文姓名",
                "班級",
                "家長LINE_ID",
                "狀態",
                "通知時間",
                "完成時間"
            ]

            row = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "student_id": student.get("student_id", ""),
                "學生姓名": student.get("學生姓名", ""),
                "英文姓名": student.get("英文姓名", ""),
                "班級": student.get("班級", ""),
                "家長LINE_ID": user_id,
                "狀態": "等待叫號",
                "通知時間": now_text(),
                "完成時間": ""
            }

            append_csv(CSV_PICKUPS, headers, row)

            print(f"接送新增：{student.get('學生姓名', '')}")

            # 不回覆家長
            continue

        # =========================
        # 請假
        # =========================

        if "請假" in text_clean and student:

            leave_type = "其他"

            if "病假" in text_clean:
                leave_type = "病假"
            elif "事假" in text_clean:
                leave_type = "事假"

            headers = [
                "id",
                "student_id",
                "學生姓名",
                "英文姓名",
                "班級",
                "假別",
                "請假日期",
                "原始訊息",
                "家長LINE_ID",
                "收到時間"
            ]

            row = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "student_id": student.get("student_id", ""),
                "學生姓名": student.get("學生姓名", ""),
                "英文姓名": student.get("英文姓名", ""),
                "班級": student.get("班級", ""),
                "假別": leave_type,
                "請假日期": today_text(),
                "原始訊息": text,
                "家長LINE_ID": user_id,
                "收到時間": now_text()
            }

            append_csv(CSV_LEAVES, headers, row)

            reply_to_line(
                reply_token,
                f"已收到請假通知：{student.get('學生姓名')}，假別：{leave_type}。"
            )

            continue

    return jsonify({"status": "ok"})


@app.route("/board")
def board():
    return render_template("board.html")


@app.route("/leave")
def leave():
    return render_template("leave.html")


@app.route("/api/pickups")
def api_pickups():
    ensure_csv(CSV_PICKUPS, [
        "id",
        "student_id",
        "學生姓名",
        "英文姓名",
        "班級",
        "家長LINE_ID",
        "狀態",
        "通知時間",
        "完成時間"
    ])

    rows = read_csv(CSV_PICKUPS)

    rows = [
        r for r in rows
        if r.get("狀態") != "已完成"
    ]

    return jsonify(rows)


@app.route("/api/pickup/call", methods=["POST"])
def api_pickup_call():
    pickup_id = request.json.get("id")
    rows = read_csv(CSV_PICKUPS)

    for r in rows:
        if r.get("id") == pickup_id:
            r["狀態"] = "已叫號"

    write_csv(CSV_PICKUPS, [
        "id",
        "student_id",
        "學生姓名",
        "英文姓名",
        "班級",
        "家長LINE_ID",
        "狀態",
        "通知時間",
        "完成時間"
    ], rows)

    return jsonify({"status": "ok"})


@app.route("/api/pickup/done", methods=["POST"])
def api_pickup_done():
    pickup_id = request.json.get("id")
    rows = read_csv(CSV_PICKUPS)

    for r in rows:
        if r.get("id") == pickup_id:
            r["狀態"] = "已完成"
            r["完成時間"] = now_text()

    write_csv(CSV_PICKUPS, [
        "id",
        "student_id",
        "學生姓名",
        "英文姓名",
        "班級",
        "家長LINE_ID",
        "狀態",
        "通知時間",
        "完成時間"
    ], rows)

    return jsonify({"status": "ok"})


@app.route("/api/pickup/cancel", methods=["POST"])
def api_pickup_cancel():
    pickup_id = request.json.get("id")
    rows = read_csv(CSV_PICKUPS)

    rows = [
        r for r in rows
        if r.get("id") != pickup_id
    ]

    write_csv(CSV_PICKUPS, [
        "id",
        "student_id",
        "學生姓名",
        "英文姓名",
        "班級",
        "家長LINE_ID",
        "狀態",
        "通知時間",
        "完成時間"
    ], rows)

    return jsonify({"status": "ok"})


@app.route("/api/pickup/clear", methods=["POST"])
def api_pickup_clear():
    write_csv(CSV_PICKUPS, [
        "id",
        "student_id",
        "學生姓名",
        "英文姓名",
        "班級",
        "家長LINE_ID",
        "狀態",
        "通知時間",
        "完成時間"
    ], [])

    return jsonify({"status": "ok"})


@app.route("/api/leaves")
def api_leaves():
    ensure_csv(CSV_LEAVES, [
        "id",
        "student_id",
        "學生姓名",
        "英文姓名",
        "班級",
        "假別",
        "請假日期",
        "原始訊息",
        "家長LINE_ID",
        "收到時間"
    ])

    rows = read_csv(CSV_LEAVES)

    today = today_text()

    today_count = len([
        r for r in rows
        if r.get("請假日期") == today
    ])

    month = today[:7]

    month_count = len([
        r for r in rows
        if r.get("收到時間", "").startswith(month)
    ])

    return jsonify({
        "rows": rows,
        "today_count": today_count,
        "month_count": month_count
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
