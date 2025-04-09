"""
コマンドラインインターフェース
ユーザーがコマンドラインからツールを操作するためのインターフェース
"""

import logging
import sys
from pathlib import Path
from typing import Optional
import click
from datetime import datetime

from .scraper import NoteDashboardScraper
from .processor import DataProcessor
from .config import config

# ロガーの設定
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """note Dashboard Extractor - noteダッシュボードからのデータ抽出ツール"""
    pass


@cli.command("extract", help="noteダッシュボードからデータを抽出")
@click.option("--headless", is_flag=True, default=None, help="ヘッドレスモードで実行")
@click.option("--output", "-o", type=str, help="出力ディレクトリを指定")
@click.option("--period", type=click.Choice(["all", "month", "week"]), default="all", help="データ収集期間")
@click.option("--max-pages", type=int, default=None, help="取得する最大ページ数")
@click.option("--max-articles", type=int, default=None, help="詳細を取得する最大記事数")
@click.option("--skip-details", is_flag=True, default=False, help="記事詳細の取得をスキップ")
@click.option("--debug", is_flag=True, default=False, help="デバッグモードで実行")
def extract(
    headless: Optional[bool],
    output: Optional[str],
    period: str,
    max_pages: Optional[int],
    max_articles: Optional[int],
    skip_details: bool,
    debug: bool,
):
    """noteダッシュボードからデータを抽出する"""
    # デバッグモード設定
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("デバッグモードが有効になりました")

    # 出力先の設定
    if output:
        config.output_dir = output
        logger.info(f"出力先を設定しました: {output}")

    # ヘッドレスモードの設定
    if headless is not None:
        config.headless = headless

    logger.info(f"ヘッドレスモード: {config.headless}")
    logger.info(f"期間: {period}")
    logger.info(f"最大ページ数: {max_pages or '制限なし'}")
    logger.info(f"最大記事数: {max_articles or '制限なし'}")
    logger.info(f"記事詳細取得: {'スキップ' if skip_details else '取得する'}")

    try:
        # スクレイピング実行
        start_time = datetime.now()
        logger.info(f"データ抽出を開始します: {start_time}")

        scraper = NoteDashboardScraper(headless=config.headless)
        articles = scraper.scrape(
            get_details=(not skip_details),
            max_pages=max_pages,
            max_articles=max_articles
        )

        end_time = datetime.now()
        duration = end_time - start_time
        logger.info(f"データ抽出が完了しました: {end_time} (所要時間: {duration})")
        logger.info(f"抽出された記事数: {len(articles)}")

        if not articles:
            logger.error("記事データが取得できませんでした")
            sys.exit(1)

        # データ処理
        logger.info("データ処理を開始します...")
        processor = DataProcessor(articles)
        processor.process_data()

        # CSV保存
        csv_path = processor.save_to_csv()
        if csv_path:
            logger.info(f"CSVファイルを保存しました: {csv_path}")
        else:
            logger.error("CSVファイルの保存に失敗しました")

        # レポート生成
        report_path = processor.generate_summary_report()
        if report_path:
            logger.info(f"サマリーレポートを生成しました: {report_path}")
        else:
            logger.error("サマリーレポートの生成に失敗しました")

        logger.info("処理が完了しました")

    except Exception as e:
        logger.error(f"処理中にエラーが発生しました: {str(e)}")
        sys.exit(1)


@cli.command("version", help="バージョン情報を表示")
def version():
    """バージョン情報を表示する"""
    from . import __version__
    click.echo(f"note Dashboard Extractor v{__version__}")


def main():
    """メイン関数"""
    try:
        cli()
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()