from flask import Flask, request

app = Flask(__name__)

@app.route("/")
def home():
    return "Webhook running"

@app.route("/callback", methods=["POST"])
def callback():
    # 接收 LINE 訊息但不做任何回覆
    data = request.get_json()

    print("收到LINE訊息：")
    print(data)

    return "OK"

if __name__ == "__main__":
    app.run()
