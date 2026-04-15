from flask import Flask, request

app = Flask(__name__)

students = [
    "彭禹哲",
    "彭禹誠",
    "許書寧",
    "李紹麒",
    "姚行謙"
]

pickup_queue = []

@app.route("/", methods=["GET"])
def home():
    return "Pixie LINE Webhook Running"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if "events" in data:
        for event in data["events"]:
            if event["type"] == "message":
                text = event["message"]["text"]

                for name in students:
                    if name in text:
                        pickup_queue.append(name)
                        print(f"家長接送：{name}")

    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
