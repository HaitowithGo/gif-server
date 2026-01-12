import os
import io
import requests
from flask import Flask, request, render_template, send_file, jsonify
from PIL import Image, ImageSequence, ImageOps

app = Flask(__name__)

# 処理済みデータをメモリ上に保持（本番ではファイル保存推奨）
processed_binary = None
current_version = 0

SCREEN_WIDTH = 128
SCREEN_HEIGHT = 64

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
        
        # ヘッダー情報 (フレーム数: 2バイト, 遅延: 2バイト)
        # 後で書き込むためにプレースホルダー
        frame_count = 0
        duration = 100 # デフォルト
        
        # 全フレーム処理
        for frame in ImageSequence.Iterator(img):
            frame = frame.convert("RGBA")
            
            # 1. 縦長判定と回転 (縦 > 横 なら90度回転)
            if frame.height > frame.width:
                frame = frame.rotate(90, expand=True)
            
            # 2. リサイズ (アスペクト比維持で画面に収める)
            # 背景を黒で埋める
            bg = Image.new("1", (SCREEN_WIDTH, SCREEN_HEIGHT), 0)
            
            # 画像をリサイズ
            frame.thumbnail((SCREEN_WIDTH, SCREEN_HEIGHT), Image.Resampling.LANCZOS)
            
            # 中央配置計算
            offset_x = (SCREEN_WIDTH - frame.width) // 2
            offset_y = (SCREEN_HEIGHT - frame.height) // 2
            
            # 3. 2値化 (ディザリング)
            # 貼り付けてからconvert('1')することで綺麗にディザリングされる
            temp_canvas = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (0,0,0))
            temp_canvas.paste(frame, (offset_x, offset_y))
            frame_1bit = temp_canvas.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
            
            # 4. XBM形式のビット配列ではなく、OLEDバッファ直書き用のバイト列にする
            # ESP8266側での処理を減らすため、raw bytesを追加
            output_stream.write(frame_1bit.tobytes())
            frame_count += 1
            
            # 初回フレームからduration取得 (ms)
            if frame_count == 1:
                duration = frame.info.get('duration', 100)

        # バイナリデータの構築完了
        raw_data = output_stream.getvalue()
        
        # ヘッダー作成: [フレーム数(2byte)][FPS待ち時間(2byte)]
        header = frame_count.to_bytes(2, 'big') + duration.to_bytes(2, 'big')
        
        processed_binary = header + raw_data
        current_version += 1 # 更新通知用
        
        return "OK: Sent to Display", 200
        
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/status')
def status():
    # ESPが更新を確認するためのエンドポイント
    return jsonify({"version": current_version})

@app.route('/download')
def download():
    # ESPがバイナリをダウンロードするエンドポイント
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