import os
import uuid
import json
import argparse
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from flask_cors import CORS
import cv2
from yomitoku import DocumentAnalyzer
import logging
import cv2
import numpy as np
import tempfile
from pdf2image import convert_from_path

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flaskアプリケーション初期化（一度だけ）
app = Flask(__name__)
CORS(app)  # CORSを有効化

# 静的ファイルのベースディレクトリ設定
STATIC_FOLDER = '/static'
os.makedirs(STATIC_FOLDER, exist_ok=True)
app.config['STATIC_FOLDER'] = STATIC_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB制限

# 許可するファイル拡張子
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

# YomiTokuアナライザーの初期化
def get_analyzer(use_gpu=True, use_lite=False):
    device = "cuda" if use_gpu else "cpu"
    return DocumentAnalyzer(
        visualize=True,      # 可視化を有効化
        device=device        # デバイス選択
    )

# ファイル拡張子のチェック
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# リクエスト処理のためのフォルダ作成
def create_request_folder():
    # タイムスタンプフォルダ名を生成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    request_id = f"{timestamp}_{uuid.uuid4().hex[:8]}"

    # リクエスト用のフォルダパス
    request_folder = os.path.join(app.config['STATIC_FOLDER'], request_id)

    # フォルダを作成
    os.makedirs(request_folder, exist_ok=True)

    return {
        "request_id": request_id,
        "folder_path": request_folder
    }

def merge_markdown_files(request_folder, file_paths, output_path):
    """複数のMarkdownファイルを1つにマージし、ページ番号マークを追加する"""
    try:
        with open(output_path, 'w', encoding='utf-8') as outfile:
            for i, file_path in enumerate(file_paths):
                # ページ番号マークを追加
                # outfile.write(f"{{{{ページ{i}}}}}------------------------------------------------\n\n")
                outfile.write(f"第{i+1}ページ------------------------------------------------\n\n")

                # 現在のページ内容を読み込み、書き出し
                with open(file_path, 'r', encoding='utf-8') as infile:
                    outfile.write(infile.read())

                # ページ区切りを追加
                outfile.write("\n\n")

        return True
    except Exception as e:
        logger.error(f"Markdownファイルのマージに失敗しました: {str(e)}")
        return False

def process_pdf(pdf_path, request_folder, request_id):
    """PDFファイルを画像に変換し、各ページを処理する"""
    try:
        # PDF画像変換用の一時ディレクトリを作成
        with tempfile.TemporaryDirectory() as temp_dir:
            # PDFを画像（PIL Image）に変換
            pages = convert_from_path(pdf_path)

            results_data = []
            pdf_basename = os.path.splitext(os.path.basename(pdf_path))[0]

            # 各ページを順番に処理
            for i, page in enumerate(pages):
                # 画像を一時ファイルとして保存
                page_image_path = os.path.join(temp_dir, f"page_{i+1}.png")
                page.save(page_image_path, "PNG")

                # 画像をOpenCVフォーマットに変換
                img = cv2.imread(page_image_path)

                # YomiTokuアナライザーの初期化と処理
                analyzer = get_analyzer()
                results, ocr_vis, layout_vis = analyzer(img)

                # 結果の保存
                page_basename = f"{pdf_basename}_page_{i+1}"

                # 可視化結果の保存
                ocr_vis_path = os.path.join(request_folder, f"{page_basename}_ocr.jpg")
                layout_vis_path = os.path.join(request_folder, f"{page_basename}_layout.jpg")
                cv2.imwrite(ocr_vis_path, ocr_vis)
                cv2.imwrite(layout_vis_path, layout_vis)

                # マークダウン生成
                md_output_path = os.path.join(request_folder, f"{page_basename}.md")
                results.to_markdown(md_output_path, img=img)

                # 結果データを収集（相対パス）
                page_result = {
                    "page_number": i+1,
                    "ocr_visualization": f"/static/{request_id}/{page_basename}_ocr.jpg",
                    "layout_visualization": f"/static/{request_id}/{page_basename}_layout.jpg",
                    "markdown": f"/static/{request_id}/{page_basename}.md"
                }

                # ページごとの結果をリストに追加
                results_data.append(page_result)

            # すべてmdファイルをマージ`
            markdown_files = [os.path.join(request_folder, f"{pdf_basename}_page_{i+1}.md") for i in range(len(pages))]
            merged_md_path = os.path.join(request_folder, f"{pdf_basename}_merged.md")
            merge_success = merge_markdown_files(request_folder, markdown_files, merged_md_path)

            if merge_success:
                # マージ後のMarkdownファイルのパスを結果に追加
                results_data.append({
                    "type": "merged",
                    "markdown": f"/static/{request_id}/{pdf_basename}_merged.md"
                })

            return results_data

    except Exception as e:
        raise Exception(f"PDF処理エラー: {str(e)}")

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.config['STATIC_FOLDER'], filename)

@app.route('/download/<path:filename>')
def download_file(filename):
    """ファイルを強制ダウンロードするエンドポイント"""
    try:
        return send_from_directory(
            app.config['STATIC_FOLDER'],
            filename,
            as_attachment=True,
            download_name=os.path.basename(filename)
        )
    except FileNotFoundError:
        return jsonify({"error": "ファイルが見つかりません"}), 404

@app.route('/')
def index():
    return jsonify({
        "status": "ok",
        "message": "日本語OCR APIが正常に動作しています",
        "endpoints": {
            "/ocr": "画像をアップロードしてOCR処理を行う (POST)",
            "/health": "ヘルスチェック (GET)"
        }
    })

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

@app.route('/ocr', methods=['POST'])
def ocr_endpoint():
    # ファイル部分があるか確認
    if 'file' not in request.files:
        return jsonify({"error": "ファイルがありません"}), 400

    file = request.files['file']

    # ファイル名が空でないか確認
    if file.filename == '':
        return jsonify({"error": "ファイルが選択されていません"}), 400

    # ファイルタイプの確認
    if not allowed_file(file.filename):
        return jsonify({"error": f"サポートされていないファイル形式です。対応形式: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    # リクエスト用のフォルダを作成
    request_info = create_request_folder()
    request_folder = request_info["folder_path"]
    request_id = request_info["request_id"]

    # ファイルを安全に保存
    filename = secure_filename(file.filename)
    file_path = os.path.join(request_folder, filename)
    file.save(file_path)

    try:
        # OCRパラメータの取得
        use_gpu = request.form.get('use_gpu', 'true').lower() == 'true'
        use_lite = request.form.get('lite', 'false').lower() == 'true'
        output_format = request.form.get('format', 'json').lower()

        # 出力フォーマットの検証
        if output_format not in ['json', 'md', 'html', 'csv']:
            output_format = 'json'

        # 画像の読み込み (PDFの場合は特別な処理が必要)
        if file_path.lower().endswith('.pdf'):
            try:
                # PDFファイルの処理
                pdf_results = process_pdf(file_path, request_folder, request_id)

                # PDFファイルの処理が成功した場合
                base_filename = os.path.splitext(filename)[0]
                download_url = f"http://192.168.131.194:9552/download/{request_id}/{base_filename}_merged.md"

                response = {
                    "status": "success",
                    "message": f"PDFが正常に処理されました。ページ数: {len(pdf_results) - 1}", # merged_md項目を除く
                    "request_id": request_id,
                    "pages": pdf_results,
                    "original_file": f"/static/{request_id}/{filename}",
                    "merged_markdown": f"/static/{request_id}/{base_filename}_merged.md",  # マージ後のmarkdownファイルパスを追加
                    "download_url": download_url,  # ダウンロードリンクを追加
                    "completed": True,  # 処理完了フラグを追加
                    "completion_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 処理完了時間
                }
                return jsonify(response)
            except Exception as e:
                logger.error(f"PDF処理エラー: {str(e)}")
                return jsonify({"error": f"PDF処理エラー: {str(e)}"}), 500
        else:
            # 画像ファイルの読み込み
            img = cv2.imread(file_path)
            if img is None:
                return jsonify({"error": "画像ファイルを読み込めません"}), 400

            # アナライザーの作成と画像処理
            analyzer = get_analyzer(use_gpu=use_gpu, use_lite=use_lite)

            # 画像分析
            logger.info(f"画像分析開始: {file_path}")
            results, ocr_vis, layout_vis = analyzer(img)

            # ファイル名（拡張子なし）
            base_filename = os.path.splitext(filename)[0]

            # 可視化結果の保存
            ocr_vis_path = os.path.join(request_folder, f"{base_filename}_ocr.jpg")
            layout_vis_path = os.path.join(request_folder, f"{base_filename}_layout.jpg")
            cv2.imwrite(ocr_vis_path, ocr_vis)
            cv2.imwrite(layout_vis_path, layout_vis)

            # レスポンスの準備
            if output_format == 'json':
                # YomiTokuの結果を処理可能な形に変換
                try:
                    # paragraphsとその他の属性を手動で辞書に変換
                    result_dict = {}

                    # 段落情報を取得
                    if hasattr(results, 'paragraphs'):
                        paragraphs_data = []
                        for p in results.paragraphs:
                            paragraph = {}
                            # 一般的に存在する属性を確認
                            if hasattr(p, 'contents'):
                                paragraph['content'] = p.contents
                            if hasattr(p, 'role'):
                                paragraph['role'] = p.role
                            if hasattr(p, 'direction'):
                                paragraph['direction'] = p.direction
                            if hasattr(p, 'order'):
                                paragraph['order'] = p.order
                            if hasattr(p, 'box'):
                                paragraph['box'] = p.box
                            paragraphs_data.append(paragraph)
                        result_dict['paragraphs'] = paragraphs_data

                    # 単語情報を取得
                    if hasattr(results, 'words'):
                        words_data = []
                        for w in results.words:
                            word = {}
                            if hasattr(w, 'content'):
                                word['content'] = w.content
                            if hasattr(w, 'direction'):
                                word['direction'] = w.direction
                            if hasattr(w, 'rec_score'):
                                word['confidence'] = w.rec_score
                            words_data.append(word)
                        result_dict['words'] = words_data

                    # テーブル情報を取得
                    if hasattr(results, 'tables'):
                        result_dict['tables'] = len(results.tables)

                    # 図形情報を取得
                    if hasattr(results, 'figures'):
                        figures_data = []
                        for f in results.figures:
                            figure = {}
                            if hasattr(f, 'order'):
                                figure['order'] = f.order
                            if hasattr(f, 'box'):
                                figure['box'] = f.box
                            figures_data.append(figure)
                        result_dict['figures'] = figures_data

                except Exception as e:
                    logger.error(f"結果のシリアライズに失敗しました: {str(e)}")
                    # 失敗した場合は空の辞書を返す
                    result_dict = {}

                # Markdown形式の結果も生成する
                md_output_path = os.path.join(request_folder, f"{base_filename}.md")
                try:
                    # to_markdownメソッドには出力パスとイメージが必要
                    results.to_markdown(md_output_path, img=img)
                    logger.info(f"Markdown形式の結果を保存しました: {md_output_path}")

                    # 生成されたMarkdownファイルの内容を読み込む
                    with open(md_output_path, 'r', encoding='utf-8') as f:
                        md_content = f.read()
                except Exception as e:
                    logger.error(f"Markdown生成に失敗しました: {str(e)}")
                    md_content = f"Markdown生成エラー: {str(e)}"

                # 画像ファイルにもダウンロードリンクを追加
                download_url = f"http://192.168.131.194:9552/download/{request_id}/{base_filename}.md"

                response = {
                    "status": "success",
                    "request_id": request_id,
                    "result": result_dict,
                    "files": {
                        "original": f"/static/{request_id}/{filename}",
                        "ocr_visualization": f"/static/{request_id}/{base_filename}_ocr.jpg",
                        "layout_visualization": f"/static/{request_id}/{base_filename}_layout.jpg",
                        "markdown": f"/static/{request_id}/{base_filename}.md"
                    },
                    "download_url": download_url,  # ダウンロードリンクを追加
                    "completed": True,  # 処理完了フラグを追加
                    "completion_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # 処理完了時間
                    "markdown_content": md_content
                }
                return jsonify(response)
            else:
                # 他の出力フォーマットの処理
                output_path = os.path.join(request_folder, f"{base_filename}.{output_format}")

                if output_format == 'md':
                    results.to_markdown(output_path, img=img)
                elif output_format == 'html':
                    results.to_html(output_path, img=img)
                elif output_format == 'csv':
                    results.to_csv(output_path)

                # 生成されたファイルの内容を読み込み
                with open(output_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 他の形式にもダウンロードリンクを追加
                download_url = f"http://192.168.131.194:9552/download/{request_id}/{base_filename}.{output_format}"

                # 処理後のコンテンツを返却
                response = {
                    "status": "success",
                    "request_id": request_id,
                    "format": output_format,
                    "content": content,
                    "files": {
                        "original": f"/static/{request_id}/{filename}",
                        "ocr_visualization": f"/static/{request_id}/{base_filename}_ocr.jpg",
                        "layout_visualization": f"/static/{request_id}/{base_filename}_layout.jpg",
                        "output_file": f"/static/{request_id}/{base_filename}.{output_format}"
                    },
                    "download_url": download_url,  # ダウンロードリンクを追加
                    "completed": True,  # 処理完了フラグを追加
                    "completion_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 処理完了時間
                }
                return jsonify(response)

    except Exception as e:
        logger.error(f"OCR処理エラー: {str(e)}", exc_info=True)
        return jsonify({"error": f"処理に失敗しました: {str(e)}"}), 500

# CLIモード用の処理関数
def process_file(path, output_dir, with_pagination=True):
    """ファイルを処理するCLI関数"""
    logger.info(f"ファイル処理: {path}")
    logger.info(f"出力先: {output_dir}")

    # 出力ディレクトリが存在しない場合は作成
    os.makedirs(output_dir, exist_ok=True)

    # YomiTokuアナライザーの初期化
    analyzer = get_analyzer()

    # 画像の読み込み
    img = cv2.imread(path)
    if img is None:
        logger.error(f"画像を読み込めません: {path}")
        return False

    # 分析実行
    results, ocr_vis, layout_vis = analyzer(img)

    # 結果の保存
    basename = os.path.basename(path)
    filename = os.path.splitext(basename)[0]

    # 可視化結果の保存
    cv2.imwrite(os.path.join(output_dir, f"{filename}_ocr.jpg"), ocr_vis)
    cv2.imwrite(os.path.join(output_dir, f"{filename}_layout.jpg"), layout_vis)

    # マークダウンとして保存
    md_path = os.path.join(output_dir, f"{filename}.md")
    results.to_markdown(md_path, img=img)

    logger.info(f"処理完了: {path}")
    logger.info(f"結果を保存しました: {md_path}")

    return True


if __name__ == '__main__':
    import sys

    if len(sys.argv) <= 1 or '--server' in sys.argv:
        # APIサーバーとして実行
        logger.info("APIサーバーモードで起動します")
        # Flaskの開発サーバーを使用
        app.run(host='0.0.0.0', port=5550, debug=False)
    else:
        # コマンドライン引数がある場合はCLIモードで実行
        parser = argparse.ArgumentParser(description="日本語OCR")
        parser.add_argument("path", nargs='?', default="./static/1.PNG",
                           help="処理する画像またはPDFファイルのパス")
        parser.add_argument("--output", "-o", default="./output", help="出力ディレクトリ")
        parser.add_argument("--no-pagination", action="store_false", dest="with_pagination",
                          help="ページ番号情報を含めない")
        args = parser.parse_args()

        # CLIモードの処理
        process_file(args.path, args.output, args.with_pagination)