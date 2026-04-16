matched_student = None
for name in students:
    if "接" in text and name in text:
        matched_student = name
        pickup_queue.append(name)
        print(f"家長接送：{name}")
        break

if reply_token and CHANNEL_ACCESS_TOKEN and matched_student:
    reply_message = f"已收到接送通知，{matched_student}準備放學中。"
    reply_to_line(reply_token, reply_message)
