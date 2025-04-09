# note Dashboard Extractor

noteダッシュボードからデータを抽出し、分析するためのツールです。クリエイターとして自分の記事のパフォーマンスデータを簡単に収集・分析できます。

## 機能

- noteダッシュボードへの自動ログイン
- 記事一覧データの抽出（タイトル、URL、公開日、閲覧数、いいね数、コメント数）
- 記事詳細ページからの追加情報取得（本文、文字数）
- データの処理と統計情報の計算
- CSVエクスポートとサマリーレポート生成

## 必要条件

- Python 3.8以上
- Chrome ブラウザ（Seleniumで使用）

## インストール方法

1. リポジトリをクローンします:

```bash
git clone https://github.com/yourusername/note-dashboard-extractor.git
cd note-dashboard-extractor
```

2. 依存パッケージをインストールします:

```bash
pip install -r requirements.txt
```

3. 環境設定ファイルをコピーして編集します:

```bash
cp .env.example .env
# .envファイルを編集してnoteアカウント情報などを設定
```

## 設定方法

`.env` ファイルで以下の設定が可能です:

```
# noteアカウント情報
NOTE_USERNAME=your_email@example.com
NOTE_PASSWORD=your_password

# 出力設定
OUTPUT_DIR=./output

# ブラウザ設定
# ブラウザを表示せず実行する場合はTrueに設定
HEADLESS=False

# リクエスト設定
# リクエスト間の待機時間（秒）
REQUEST_DELAY=2
# タイムアウト（秒）
TIMEOUT=30
# 最大リトライ回数
MAX_RETRIES=3

# 並列処理設定
# 同時実行ワーカー数
MAX_WORKERS=1
```

## 使用方法

### データ抽出

```bash
# 基本的なデータ抽出
python -m src.cli extract

# ヘッドレスモードで実行（ブラウザを表示せず）
python -m src.cli extract --headless

# 出力先を指定
python -m src.cli extract --output ./my_output_dir

# 最大ページ数を制限
python -m src.cli extract --max-pages 5

# 詳細を取得する最大記事数を制限
python -m src.cli extract --max-articles 10

# 記事詳細の取得をスキップ
python -m src.cli extract --skip-details

# デバッグモードで実行
python -m src.cli extract --debug
```

### バージョン情報の表示

```bash
python -m src.cli version
```

## 出力結果

- `output/` ディレクトリ（または指定した出力先）に以下のファイルが生成されます:
  - `note_data_YYYYMMDD_HHMMSS.csv` - 抽出したデータのCSVファイル
  - `note_report_YYYYMMDD_HHMMSS.txt` - 統計情報のテキストレポート
  - `screenshots/` - デバッグ用のスクリーンショット（エラー発生時）
  - `debug/` - デバッグ用のログファイル

## 注意事項・制限事項

- このツールはnoteの公式APIを使用していないため、noteのサイト構造変更により動作しなくなる可能性があります
- 大量の記事を持つアカウントでは処理に時間がかかる場合があります
- 短時間に大量のリクエストを行うとアカウントが一時的にブロックされる可能性があるため、REQUEST_DELAYの値を適切に設定してください
- ツールの使用はnoteの利用規約に準拠してください

## ライセンス

MIT

## 免責事項

このツールはnoteのクリエイター向けに開発されたものであり、個人的な分析目的で使用することを想定しています。データのスクレイピングはnoteの利用規約に従って行ってください。このツールの使用によって生じたいかなる問題や損害についても、開発者は責任を負いません。
