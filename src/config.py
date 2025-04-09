"""
設定管理モジュール
環境変数の読み込みや設定の管理を担当
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# ロガーの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# プロジェクトルートディレクトリの取得
ROOT_DIR = Path(__file__).parent.parent.absolute()

# .envファイルの読み込み
load_dotenv(ROOT_DIR / '.env')

class Config:
    """
    アプリケーション設定を管理するクラス
    .envファイルや環境変数から設定を読み込む
    """
    
    def __init__(self):
        """設定の初期化"""
        # noteアカウント情報
        self.username = os.getenv('NOTE_USERNAME')
        self.password = os.getenv('NOTE_PASSWORD')
        
        # 出力設定
        self.output_dir = os.getenv('OUTPUT_DIR', str(ROOT_DIR / 'output'))
        
        # ブラウザ設定
        self.headless = os.getenv('HEADLESS', 'False').lower() == 'true'
        
        # リクエスト設定
        self.request_delay = int(os.getenv('REQUEST_DELAY', '2'))
        self.timeout = int(os.getenv('TIMEOUT', '30'))
        self.max_retries = int(os.getenv('MAX_RETRIES', '3'))
        
        # 並列処理設定
        self.max_workers = int(os.getenv('MAX_WORKERS', '1'))
        
        # 検証
        self._validate()
    
    def _validate(self):
        """設定のバリデーション"""
        if not self.username or not self.password:
            logger.warning("NOTE_USERNAMEまたはNOTE_PASSWORDが設定されていません")
        
        # 出力ディレクトリの存在確認と作成
        output_path = Path(self.output_dir)
        if not output_path.exists():
            logger.info(f"出力ディレクトリを作成します: {output_path}")
            output_path.mkdir(parents=True, exist_ok=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """設定を辞書形式で返却（パスワードは除外）"""
        config_dict = self.__dict__.copy()
        # 機密情報を削除
        if 'password' in config_dict:
            config_dict['password'] = '********'
        return config_dict
    
    def __str__(self) -> str:
        """設定情報の文字列表現"""
        return f"Config: {self.to_dict()}"


# 設定インスタンスのシングルトン
config = Config()