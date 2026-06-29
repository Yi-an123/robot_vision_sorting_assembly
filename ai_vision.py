import json
import os
import time
import socket
import cv2
import requests

# ============================
# 三个盒子的棋子配置
# ============================
boxes = {
    1: [("yellow", 4), ("black", 2), ("black", 3), ("red", 4)],
    2: [("yellow", 2), ("red", 1),    ("yellow", 1), ("red", 2)],
    3: [("black", 1),  ("black", 4),  ("blue", 4),   ("blue", 2)],
}

# ============================
# 配置
# ============================
SAVE_DIR = r'C:\Users\18794\OneDrive\Desktop\Ricardo_ai'
PIC_TOKEN = '1970|sNco9ziaC4FvOCoV1q6LWi663dCmLuNM5n5Ko38Lf1a97607'
UPLOAD_URL = 'https://www.boltp.com/api/v2/upload'
AI_TOKEN = '854b2c17ea9d4572af78d85f64f20ce1.CBocTwI7ryGHq9zR'
AI_URL = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'

HOST = '0.0.0.0'
PORT = 8005


def capture_photo():
    """USB 相机拍照，返回图片路径"""
    # for idx in [0, 1]:  # 尝试 /dev/video0 和 /dev/video1
    cap = cv2.VideoCapture(1)
    if cap.isOpened():
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None:
            path = os.path.join(SAVE_DIR, f'photo_{time.strftime("%Y%m%d_%H%M%S")}.jpg')
            cv2.imwrite(path, frame)
            return path
    return None


def process_image(image_path):
    """上传 -> AI 识别 -> 匹配盒子 -> 返回位置字符串"""
    headers = {
        'Authorization': f'Bearer {PIC_TOKEN}',
        'Accept': 'application/json',
    }

    # 第一步：上传图片到 boltp
    with open(image_path, 'rb') as f:
        files = {'file': f}
        data = {'storage_id': 2}
        resp = requests.post(UPLOAD_URL, headers=headers, files=files, data=data, timeout=60)
        result = resp.json()

    if result.get('status') != 'success':
        return '0,0'

    image_url = result['data']['public_url']

    # 第二步：发给智谱 GLM-4V 识别
    ai_headers = {'Authorization': f'Bearer {AI_TOKEN}', 'Content-Type': 'application/json'}
    payload = {
        'model': 'glm-4v',
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'image_url', 'image_url': {'url': image_url}},
                {'type': 'text', 'text': (
                    '请识别图片中圆圈内的颜色（注意：是圆圈内部填充的颜色，不是文字的颜色）。'
                    '颜色只能从 ["blue","red","black","yellow"] 中选择。'
                    '数字是在圆圈颜色内部，只能从 [1,2,3,4] 中选择。'
                    '请只返回一个 JSON，不要其他文字，格式严格如下：'
                    '{"color":"xxx","number":N}'
                )},
            ]
        }]
    }

    resp = requests.post(AI_URL, headers=ai_headers, json=payload, timeout=60)

    if resp.status_code != 200:
        return '0,0'

    answer = resp.json()['choices'][0]['message']['content']

    # 第三步：解析 JSON
    try:
        answer = answer.strip()
        if answer.startswith('```'):
            answer = answer.split('\n', 1)[1]
            if answer.endswith('```'):
                answer = answer.rsplit('```', 1)[0]
            answer = answer.strip()
            if answer.startswith('json'):
                answer = answer[4:].strip()

        rec = json.loads(answer)
        print(rec)
        rec_color = rec['color']
        rec_number = rec['number']
    except (json.JSONDecodeError, KeyError):
        return '0,0'

    # 第四步：匹配盒子
    for box_id, pieces in boxes.items():
        for pos, (color, number) in enumerate(pieces, start=1):
            if rec_color == color and rec_number == number:
                return f'{box_id},{pos}'

    return '0,0'


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(1)
    print(f'Server running on {HOST}:{PORT}')

    while True:
        print('Waiting for robot connection...')
        client, addr = s.accept()
        print(f'Robot connected: {addr}')

        try:
            while True:
                data = client.recv(200)
                if not data:
                    print('Robot disconnected')
                    break

                signal = data.decode('utf-8').strip()
                print(f'Received: {signal}')

                if signal == '1':
                    # 拍照
                    photo_path = capture_photo()
                    if photo_path is None:
                        print('Camera error')
                        client.send(b'0,0')
                        continue

                    print(f'Photo captured: {photo_path}')

                    # 上传 + AI 识别 + 匹配
                    result = process_image(photo_path)
                    print(f'Send to robot: {result}')

                    # 返回给机器人
                    client.send(result.encode('utf-8'))

        except (ConnectionResetError, BrokenPipeError):
            print('Connection lost')
        finally:
            client.close()


if __name__ == '__main__':
    main()
