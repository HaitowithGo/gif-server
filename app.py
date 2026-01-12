import os
import io
import requests
from flask import Flask, request, render_template, send_file, jsonify
from PIL import Image, ImageSequence

app = Flask(__name__)

# 処理済みデータをメモリ上に保持
processed_binary = None
current_version = 0

SCREEN_WIDTH = 128
SCREEN_HEIGHT = 64

# --- ビット反転関数 (ここが修正のキモ) ---
# Pillowの出力(MSB First)をU8g2のXBM形式(LSB First)に合わせる
def reverse_bits_in_bytes(data):
    reversed_data = bytearray()
    for b in data:
        # 8ビット単位で並びを逆にするビット演算
        b = (b & 0xF0) >> 4 | (b & 0x0F) << 4
        b = (b & 0xCC) >> 2 | (b & 0x33) << 2
        b = (b & 0xAA) >> 1 | (b & 0x55) << 1
        reversed_data.append(b)
    return bytes(reversed_data)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    global processed_binary, current_version
    url = request.form.get('url')
    
    try:
        # GIPHYからダウンロード
        resp = requests.get(url)
        img = Image.open(io.BytesIO(resp.content))
        
        output_stream = io.BytesIO()
        
        frame_count = 0
        duration = 100 
        
        # 全フレーム処理
        for frame in ImageSequence.Iterator(img):
            frame = frame.convert("RGBA")
            
            # 1. 縦長判定と回転 (縦 > 横 なら90度回転)
            if frame.height > frame.width:
                frame = frame.rotate(90, expand=True)
            
            # 2. 背景作成（黒）
            bg = Image.new("1", (SCREEN_WIDTH, SCREEN_HEIGHT), 0)
            
            # 3. リサイズ (アスペクト比維持)
            frame.thumbnail((SCREEN_WIDTH, SCREEN_HEIGHT), Image.Resampling.LANCZOS)
            
            # 4. 中央配置
            offset_x = (SCREEN_WIDTH - frame.width) // 2
            offset_y = (SCREEN_HEIGHT - frame.height) // 2
            
            # 5. 貼り付け & 2値化 (ディザリング)
            temp_canvas = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (0,0,0))
            temp_canvas.paste(frame, (offset_x, offset_y))
            frame_1bit = temp_canvas.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
            
            # 6. 生データを取得してビット反転！
            raw_bytes = frame_1bit.tobytes()
            reversed_bytes = reverse_bits_in_bytes(raw_bytes)
            
            # 書き込み
            output_stream.write(reversed_bytes)
            frame_count += 1
            
            if frame_count == 1:
                duration = frame.info.get('duration', 100)

        # バイナリ構築: [Frame数(2B)][Duration(2B)][画像データ...]
        # 画像データが空でないことを確認
        raw_data = output_stream.getvalue()
        if not raw_data:
             return "Error: Empty GIF data", 400

        header = frame_count.to_bytes(2, 'big') + duration.to_bytes(2, 'big')
        processed_binary = header + raw_data
        
        # バージョンを更新してESPに通知
        current_version += 1
        
        return f"OK: Processed {frame_count} frames.", 200
        
    except Exception as e:
        print(e)
        return f"Error: {str(e)}", 500

@app.route('/status')
def status():
    return jsonify({"version": current_version})

@app.route('/download')
def download():
    if processed_binary:
        return send_file(
            io.BytesIO(processed_binary),
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name='anim.bin'
        )
    return "No Data", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)