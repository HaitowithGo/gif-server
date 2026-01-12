import io
import requests
from flask import Flask, request, render_template, send_file, jsonify
from PIL import Image, ImageSequence, ImageOps

app = Flask(__name__)

# データ保持用
processed_binary = None
current_version = 0

SCREEN_SIZE = (128, 64)

def reverse_bits(data):
    reversed_data = bytearray()
    for b in data:
        # ビット反転処理
        b = (b & 0xF0) >> 4 | (b & 0x0F) << 4
        b = (b & 0xCC) >> 2 | (b & 0x33) << 2
        b = (b & 0xAA) >> 1 | (b & 0x55) << 1
        reversed_data.append(b)
    return bytes(reversed_data)

def process_gif(url):
    try:
        resp = requests.get(url, timeout=10)
        img = Image.open(io.BytesIO(resp.content))
    except:
        return None

    output = io.BytesIO()
    frames = 0
    duration = 100

    for frame in ImageSequence.Iterator(img):
        frame = frame.convert("RGBA")
        
        # 縦長画像は90度回転して、横長画面を有効活用する
        if frame.height > frame.width:
            frame = frame.rotate(90, expand=True)

        # 常に画面いっぱいにフィットさせる（黒帯なし）
        processed = ImageOps.fit(frame, SCREEN_SIZE, method=Image.Resampling.LANCZOS)

        # 2値化 & ビット反転
        mono = processed.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
        output.write(reverse_bits(mono.tobytes()))
        
        frames += 1
        if frames == 1:
            duration = frame.info.get('duration', 100)

    # ヘッダー作成 [Frames(2B)][Duration(2B)]
    header = frames.to_bytes(2, 'big') + duration.to_bytes(2, 'big')
    return header + output.getvalue()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    global processed_binary, current_version
    url = request.form.get('url')
    
    data = process_gif(url)
    if data:
        processed_binary = data
        current_version += 1
        return "OK", 200
    return "Error", 500

@app.route('/status')
def status(): return jsonify({"version": current_version})

@app.route('/download')
def download():
    if processed_binary:
        return send_file(io.BytesIO(processed_binary), mimetype='application/octet-stream', as_attachment=True, download_name='anim.bin')
    return "No Data", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)