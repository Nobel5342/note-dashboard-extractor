"""
データ処理と分析モジュール
抽出されたデータの処理、分析、可視化を担当
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import polars as pl

from .scraper import Article
from .config import config

# ロガーの設定
logger = logging.getLogger(__name__)


class DataProcessor:
    """データ処理クラス"""
    
    def __init__(self, articles: List[Article] = None):
        """
        初期化
        
        Args:
            articles: 分析対象の記事リスト（あれば）
        """
        self.articles = articles or []
        self.dataframe = None
    
    def create_dataframe(self) -> pl.DataFrame:
        """記事リストをDataFrameに変換"""
        logger.info("記事データをDataFrameに変換しています...")
        
        if not self.articles:
            logger.warning("変換する記事データがありません")
            return pl.DataFrame()
        
        # 記事リストを辞書のリストに変換
        data = [article.to_dict() for article in self.articles]
        
        try:
            # Polarsデータフレーム作成
            df = pl.DataFrame(data)
            self.dataframe = df
            
            logger.info(f"DataFrameを作成しました（{len(df)}件のデータ）")
            return df
        except Exception as e:
            logger.error(f"DataFrameの作成中にエラーが発生しました: {str(e)}")
            return pl.DataFrame()
    
    def process_data(self) -> pl.DataFrame:
        """データの前処理"""
        if self.dataframe is None:
            self.create_dataframe()
        
        if len(self.dataframe) == 0:
            return self.dataframe
        
        logger.info("データの前処理を実行しています...")
        
        try:
            df = self.dataframe
            
            # 日付の変換（例: "2023年4月1日" → datetime型）
            # noteの日付形式に合わせて処理
            try:
                if "published_at" in df.columns:
                    # 日本語の日付表記を解析
                    df = df.with_columns([
                        pl.col("published_at").str.replace("年", "-").str.replace("月", "-").str.replace("日", "")
                        .alias("published_at_clean")
                    ])
                    # 日付型に変換
                    df = df.with_columns([
                        pl.col("published_at_clean").str.to_date().alias("published_date")
                    ])
                    # 不要な中間列を削除
                    df = df.drop("published_at_clean")
            except Exception as e:
                logger.warning(f"日付の変換処理に失敗しました: {str(e)}")
            
            # 数値データの型変換を確認
            for col in ["views", "likes", "comments", "char_count"]:
                if col in df.columns:
                    df = df.with_columns([
                        pl.col(col).cast(pl.Int64).alias(col)
                    ])
            
            self.dataframe = df
            logger.info("データの前処理が完了しました")
            return df
            
        except Exception as e:
            logger.error(f"データ前処理中にエラーが発生しました: {str(e)}")
            return self.dataframe
    
    def calculate_statistics(self) -> Dict[str, Any]:
        """基本統計情報の計算"""
        if self.dataframe is None or len(self.dataframe) == 0:
            logger.warning("統計情報を計算するデータがありません")
            return {}
        
        logger.info("基本統計情報を計算しています...")
        stats = {}
        
        try:
            df = self.dataframe
            
            # 記事数
            stats["total_articles"] = len(df)
            
            # 各種合計値
            for col in ["views", "likes", "comments", "char_count"]:
                if col in df.columns:
                    total = df[col].sum()
                    stats[f"total_{col}"] = int(total)
            
            # 各種平均値
            for col in ["views", "likes", "comments", "char_count"]:
                if col in df.columns:
                    avg = df[col].mean()
                    stats[f"average_{col}"] = round(float(avg), 2)
            
            # 記事あたりのいいね率（閲覧数に対するいいね数の割合）
            if "views" in df.columns and "likes" in df.columns:
                # ゼロ除算を回避
                df_non_zero_views = df.filter(pl.col("views") > 0)
                if len(df_non_zero_views) > 0:
                    like_ratio = df_non_zero_views["likes"].sum() / df_non_zero_views["views"].sum()
                    stats["like_ratio"] = round(float(like_ratio) * 100, 2)  # パーセント表示
            
            logger.info("基本統計情報の計算が完了しました")
            return stats
            
        except Exception as e:
            logger.error(f"統計情報の計算中にエラーが発生しました: {str(e)}")
            return {}
    
    def save_to_csv(self, output_path: Optional[str] = None) -> str:
        """データをCSV形式で保存"""
        if self.dataframe is None:
            logger.error("保存するデータがありません")
            return ""
        
        # 出力先の設定
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"note_data_{timestamp}.csv"
            output_path = Path(config.output_dir) / filename
        else:
            output_path = Path(output_path)
            
        # 親ディレクトリの作成
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"データをCSVファイルに保存しています: {output_path}")
        
        try:
            self.dataframe.write_csv(output_path)
            logger.info(f"CSVファイルの保存が完了しました: {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"CSVファイル保存中にエラーが発生しました: {str(e)}")
            return ""
    
    def generate_summary_report(self, output_path: Optional[str] = None) -> str:
        """レポート生成（統計情報のテキスト出力）"""
        if self.dataframe is None or len(self.dataframe) == 0:
            logger.warning("レポート生成用のデータがありません")
            return ""
        
        logger.info("サマリーレポートを生成しています...")
        
        # 統計情報の計算
        stats = self.calculate_statistics()
        
        # 出力先の設定
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"note_report_{timestamp}.txt"
            output_path = Path(config.output_dir) / filename
        else:
            output_path = Path(output_path)
            
        # 親ディレクトリの作成
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("# note Dashboard Data Report\n\n")
                f.write(f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                f.write("## 基本情報\n\n")
                f.write(f"- 記事総数: {stats.get('total_articles', 0)}件\n")
                f.write(f"- 総閲覧数: {stats.get('total_views', 0):,}回\n")
                f.write(f"- 総いいね数: {stats.get('total_likes', 0):,}件\n")
                f.write(f"- 総コメント数: {stats.get('total_comments', 0):,}件\n")
                f.write(f"- 総文字数: {stats.get('total_char_count', 0):,}文字\n\n")
                
                f.write("## 平均値\n\n")
                f.write(f"- 平均閲覧数: {stats.get('average_views', 0):.1f}回/記事\n")
                f.write(f"- 平均いいね数: {stats.get('average_likes', 0):.1f}件/記事\n")
                f.write(f"- 平均コメント数: {stats.get('average_comments', 0):.1f}件/記事\n")
                f.write(f"- 平均文字数: {stats.get('average_char_count', 0):.1f}文字/記事\n\n")
                
                f.write("## エンゲージメント\n\n")
                f.write(f"- いいね率: {stats.get('like_ratio', 0):.2f}%（総いいね数÷総閲覧数）\n")
                
                # トップ記事情報
                f.write("\n## 人気記事（閲覧数トップ5）\n\n")
                try:
                    top_by_views = self.dataframe.sort("views", reverse=True).head(5)
                    for i, row in enumerate(top_by_views.rows(named=True)):
                        f.write(f"{i+1}. {row['title']} - {row['views']:,}回\n")
                except:
                    f.write("データ不足のため表示できません\n")
                
                f.write("\n## いいね数トップ5\n\n")
                try:
                    top_by_likes = self.dataframe.sort("likes", reverse=True).head(5)
                    for i, row in enumerate(top_by_likes.rows(named=True)):
                        f.write(f"{i+1}. {row['title']} - {row['likes']:,}いいね\n")
                except:
                    f.write("データ不足のため表示できません\n")
            
            logger.info(f"サマリーレポートの生成が完了しました: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"レポート生成中にエラーが発生しました: {str(e)}")
            return ""