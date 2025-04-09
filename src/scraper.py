"""
ブラウザ操作とデータ収集のコアロジック
noteダッシュボードへのログイン、ナビゲーション、データ抽出処理を担当
"""

import time
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import polars as pl

from .config import config

# ロガーの設定
logger = logging.getLogger(__name__)

class Article:
    """記事データモデル"""
    
    def __init__(self, title: str, url: str, published_at: str):
        self.title = title
        self.url = url
        self.published_at = published_at
        self.views = 0
        self.likes = 0
        self.comments = 0
        self.text_content = ""
        self.char_count = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """記事データを辞書形式で返却"""
        return {
            'title': self.title,
            'url': self.url,
            'published_at': self.published_at,
            'views': self.views,
            'likes': self.likes,
            'comments': self.comments,
            'char_count': self.char_count,
        }
    
    def __str__(self) -> str:
        """記事データの文字列表現"""
        return f"Article('{self.title}', views={self.views}, likes={self.likes})"


class NoteDashboardScraper:
    """noteダッシュボードスクレイピングの中核クラス"""
    
    # noteサイトのURL
    NOTE_BASE_URL = "https://note.com"
    NOTE_LOGIN_URL = "https://note.com/login"
    
    # 各要素に対するセレクタ（複数戦略）
    SELECTORS = {
        # ログイン関連
        'login': {
            'email_input': ['input[type="email"]', 'input[name="email"]'],
            'password_input': ['input[type="password"]', 'input[name="password"]'],
            'submit_button': ['button[type="submit"]', 'button.n-button--primary'],
        },
        # ダッシュボード関連
        'dashboard': {
            'link': ['a[href*="/dashboard"]', '.dashboard-link'],
            'articles_tab': ['a[href*="/dashboard/articles"]', '.articles-tab'],
        },
        # 記事一覧
        'article_list': {
            'articles': ['.article-item', '.article-row'],
            'title': ['.article-title', 'h3.title'],
            'url': ['a.article-link', 'a[href*="/"]'],
            'published_at': ['.published-date', '.date'],
            'views': ['.view-count', '.views'],
            'likes': ['.like-count', '.likes'],
            'comments': ['.comment-count', '.comments'],
        },
        # ページネーション
        'pagination': {
            'next_button': ['.pagination-next:not(.disabled)', '.next-page:not(.disabled)'],
        },
    }
    
    def __init__(self, headless: bool = None):
        """
        初期化
        
        Args:
            headless: ヘッドレスモード（指定がなければconfig値を使用）
        """
        self.headless = headless if headless is not None else config.headless
        self.driver = None
        self.wait = None
        self.articles = []
    
    def setup_browser(self):
        """ブラウザの初期化と設定"""
        logger.info("ブラウザを初期化します...")
        
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # 自動ダウンロードと更新によるドライバ管理
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.wait = WebDriverWait(self.driver, config.timeout)
            logger.info("ブラウザの初期化が完了しました")
        except WebDriverException as e:
            logger.error(f"ブラウザの初期化に失敗しました: {str(e)}")
            raise
    
    def find_element_with_multiple_selectors(self, selectors: List[str], by: By = By.CSS_SELECTOR) -> Optional[Any]:
        """複数のセレクタを試して要素を検索"""
        for selector in selectors:
            try:
                element = self.driver.find_element(by, selector)
                return element
            except NoSuchElementException:
                continue
        return None
    
    def find_elements_with_multiple_selectors(self, selectors: List[str], by: By = By.CSS_SELECTOR) -> List[Any]:
        """複数のセレクタを試して要素リストを検索"""
        for selector in selectors:
            try:
                elements = self.driver.find_elements(by, selector)
                if elements:
                    return elements
            except NoSuchElementException:
                continue
        return []
    
    def wait_for_element_with_multiple_selectors(self, selectors: List[str], by: By = By.CSS_SELECTOR) -> Optional[Any]:
        """複数のセレクタを試して要素が表示されるまで待機"""
        for selector in selectors:
            try:
                element = self.wait.until(EC.presence_of_element_located((by, selector)))
                return element
            except TimeoutException:
                continue
        return None
    
    def login(self) -> bool:
        """noteアカウントへのログイン処理"""
        try:
            logger.info("ログインページにアクセスしています...")
            self.driver.get(self.NOTE_LOGIN_URL)
            
            logger.info("ログインフォームを入力しています...")
            # メールアドレス入力
            email_input = self.wait_for_element_with_multiple_selectors(
                self.SELECTORS['login']['email_input']
            )
            if not email_input:
                logger.error("メールアドレス入力フィールドが見つかりません")
                return False
            
            email_input.send_keys(config.username)
            
            # パスワード入力
            password_input = self.find_element_with_multiple_selectors(
                self.SELECTORS['login']['password_input']
            )
            if not password_input:
                logger.error("パスワード入力フィールドが見つかりません")
                return False
            
            password_input.send_keys(config.password)
            
            # ログインボタンクリック
            submit_button = self.find_element_with_multiple_selectors(
                self.SELECTORS['login']['submit_button']
            )
            if not submit_button:
                logger.error("ログインボタンが見つかりません")
                return False
            
            submit_button.click()
            
            # ログイン成功の確認（マイページに遷移するまで待機）
            try:
                self.wait.until(lambda d: "/login" not in d.current_url)
                logger.info("ログイン成功しました")
                return True
            except TimeoutException:
                logger.error("ログインに失敗したようです")
                # デバッグ用にスクリーンショット保存
                self.take_screenshot("login_failed")
                return False
                
        except Exception as e:
            logger.error(f"ログイン処理中にエラーが発生しました: {str(e)}")
            self.take_screenshot("login_error")
            return False
    
    def navigate_to_dashboard(self) -> bool:
        """ダッシュボードページへの遷移"""
        try:
            logger.info("ダッシュボードへ移動しています...")
            
            # ダッシュボードリンクを探して移動
            dashboard_link = self.find_element_with_multiple_selectors(
                self.SELECTORS['dashboard']['link']
            )
            
            if dashboard_link:
                dashboard_link.click()
            else:
                # リンクが見つからない場合はURLで直接アクセス
                logger.info("ダッシュボードリンクが見つからないため、URLで直接アクセスします")
                self.driver.get(f"{self.NOTE_BASE_URL}/dashboard")
            
            # 記事タブへの移動（必要な場合）
            try:
                articles_tab = self.wait_for_element_with_multiple_selectors(
                    self.SELECTORS['dashboard']['articles_tab']
                )
                if articles_tab:
                    articles_tab.click()
                    logger.info("記事タブに移動しました")
            except:
                logger.info("記事タブへの移動はスキップします")
            
            # 正しくダッシュボードに移動したことを確認
            if "/dashboard" in self.driver.current_url:
                logger.info("ダッシュボードへの移動に成功しました")
                return True
            else:
                logger.error("ダッシュボードへの移動に失敗しました")
                self.take_screenshot("dashboard_navigation_failed")
                return False
                
        except Exception as e:
            logger.error(f"ダッシュボード移動中にエラーが発生しました: {str(e)}")
            self.take_screenshot("dashboard_navigation_error")
            return False
    
    def extract_articles_from_current_page(self) -> List[Article]:
        """現在のページから記事データを抽出"""
        logger.info("現在のページから記事データを抽出しています...")
        
        page_articles = []
        
        try:
            # ページ内の記事要素リストを取得
            article_elements = self.find_elements_with_multiple_selectors(
                self.SELECTORS['article_list']['articles']
            )
            
            if not article_elements:
                logger.warning("ページ内に記事要素が見つかりませんでした")
                return []
            
            logger.info(f"{len(article_elements)}件の記事要素を検出しました")
            
            for element in article_elements:
                try:
                    # 記事タイトルとURL
                    title_element = element.find_element(By.CSS_SELECTOR, 
                                                        self.SELECTORS['article_list']['title'][0])
                    url_element = element.find_element(By.CSS_SELECTOR,
                                                     self.SELECTORS['article_list']['url'][0])
                    
                    title = title_element.text.strip() if title_element else "不明なタイトル"
                    url = url_element.get_attribute("href") if url_element else ""
                    
                    # 公開日
                    date_element = element.find_element(By.CSS_SELECTOR,
                                                      self.SELECTORS['article_list']['published_at'][0])
                    published_at = date_element.text.strip() if date_element else ""
                    
                    # 記事オブジェクト作成
                    article = Article(title, url, published_at)
                    
                    # 各種統計情報
                    try:
                        views_element = element.find_element(By.CSS_SELECTOR,
                                                          self.SELECTORS['article_list']['views'][0])
                        article.views = self._parse_number(views_element.text)
                    except:
                        pass
                    
                    try:
                        likes_element = element.find_element(By.CSS_SELECTOR,
                                                          self.SELECTORS['article_list']['likes'][0])
                        article.likes = self._parse_number(likes_element.text)
                    except:
                        pass
                    
                    try:
                        comments_element = element.find_element(By.CSS_SELECTOR,
                                                             self.SELECTORS['article_list']['comments'][0])
                        article.comments = self._parse_number(comments_element.text)
                    except:
                        pass
                    
                    page_articles.append(article)
                    logger.debug(f"記事を抽出しました: {article}")
                    
                except Exception as e:
                    logger.warning(f"記事要素からのデータ抽出中にエラー: {str(e)}")
            
            return page_articles
            
        except Exception as e:
            logger.error(f"記事データの抽出中にエラーが発生しました: {str(e)}")
            self.take_screenshot("article_extraction_error")
            return []
    
    def has_next_page(self) -> bool:
        """次のページが存在するかどうかを確認"""
        next_button = self.find_element_with_multiple_selectors(
            self.SELECTORS['pagination']['next_button']
        )
        return next_button is not None and next_button.is_enabled()
    
    def go_to_next_page(self) -> bool:
        """次のページへ移動"""
        try:
            next_button = self.find_element_with_multiple_selectors(
                self.SELECTORS['pagination']['next_button']
            )
            
            if next_button and next_button.is_enabled():
                next_button.click()
                # ページ読み込み待機
                time.sleep(config.request_delay)
                return True
            else:
                logger.info("次のページはありません")
                return False
                
        except Exception as e:
            logger.error(f"次ページへの移動中にエラーが発生しました: {str(e)}")
            return False
    
    def extract_all_articles(self, max_pages: int = None) -> List[Article]:
        """全ページから記事データを抽出"""
        logger.info("全ページから記事データの抽出を開始します...")
        
        all_articles = []
        page_count = 1
        
        # 現在のページから記事を抽出
        page_articles = self.extract_articles_from_current_page()
        all_articles.extend(page_articles)
        logger.info(f"ページ {page_count}: {len(page_articles)} 件の記事を抽出しました")
        
        # ページネーション処理
        while self.has_next_page() and (max_pages is None or page_count < max_pages):
            if self.go_to_next_page():
                page_count += 1
                page_articles = self.extract_articles_from_current_page()
                all_articles.extend(page_articles)
                logger.info(f"ページ {page_count}: {len(page_articles)} 件の記事を抽出しました")
            else:
                break
        
        logger.info(f"全 {page_count} ページから合計 {len(all_articles)} 件の記事を抽出しました")
        return all_articles
    
    def get_article_details(self, article: Article) -> Article:
        """記事詳細ページから追加情報を取得"""
        if not article.url:
            return article
        
        logger.info(f"記事詳細ページを取得しています: {article.title}")
        
        try:
            # 記事詳細ページに移動
            self.driver.get(article.url)
            time.sleep(config.request_delay)
            
            # 記事本文を取得
            try:
                article_body = self.driver.find_element(By.CSS_SELECTOR, ".note-common-styles__textnote-body")
                if article_body:
                    article.text_content = article_body.text
                    article.char_count = len(article.text_content)
                    logger.debug(f"記事の文字数: {article.char_count}")
            except:
                logger.warning(f"記事本文の取得に失敗しました: {article.title}")
            
            return article
            
        except Exception as e:
            logger.error(f"記事詳細の取得中にエラーが発生しました: {str(e)}")
            return article
    
    def get_all_articles_details(self, articles: List[Article], max_articles: int = None) -> List[Article]:
        """全ての記事の詳細情報を取得"""
        logger.info(f"記事詳細情報の取得を開始します（全{len(articles)}件）...")
        
        # 最大記事数の制限（指定がある場合）
        target_articles = articles[:max_articles] if max_articles is not None else articles
        
        for i, article in enumerate(target_articles):
            logger.info(f"記事詳細取得中 ({i+1}/{len(target_articles)}): {article.title}")
            self.get_article_details(article)
            # 連続アクセスによるブロック回避のため遅延を入れる
            time.sleep(config.request_delay)
        
        logger.info("記事詳細情報の取得が完了しました")
        return articles
    
    def scrape(self, get_details: bool = True, max_pages: int = None, max_articles: int = None) -> List[Article]:
        """スクレイピングのメイン処理"""
        logger.info("スクレイピングを開始します...")
        
        try:
            # ブラウザの初期化
            self.setup_browser()
            
            # ログイン処理
            if not self.login():
                logger.error("ログインに失敗したため、処理を終了します")
                return []
            
            # ダッシュボードに移動
            if not self.navigate_to_dashboard():
                logger.error("ダッシュボードへの移動に失敗したため、処理を終了します")
                return []
            
            # 記事データの抽出
            self.articles = self.extract_all_articles(max_pages)
            
            # 各記事の詳細情報を取得（オプション）
            if get_details and self.articles:
                self.get_all_articles_details(self.articles, max_articles)
            
            return self.articles
            
        except Exception as e:
            logger.error(f"スクレイピング処理中にエラーが発生しました: {str(e)}")
            self.take_screenshot("scraping_error")
            return []
            
        finally:
            # ブラウザの終了処理
            self.close()
    
    def take_screenshot(self, name: str):
        """デバッグ用のスクリーンショット保存機能"""
        if self.driver:
            try:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = f"{name}_{timestamp}.png"
                screenshots_dir = Path(config.output_dir) / "screenshots"
                screenshots_dir.mkdir(parents=True, exist_ok=True)
                
                screenshot_path = screenshots_dir / filename
                self.driver.save_screenshot(str(screenshot_path))
                logger.info(f"スクリーンショットを保存しました: {screenshot_path}")
            except Exception as e:
                logger.error(f"スクリーンショット保存中にエラーが発生しました: {str(e)}")
    
    def save_page_source(self, name: str):
        """デバッグ用のページソース保存機能"""
        if self.driver:
            try:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = f"{name}_{timestamp}.html"
                debug_dir = Path(config.output_dir) / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                
                page_source_path = debug_dir / filename
                with open(page_source_path, "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                logger.info(f"ページソースを保存しました: {page_source_path}")
            except Exception as e:
                logger.error(f"ページソース保存中にエラーが発生しました: {str(e)}")
    
    def close(self):
        """ブラウザの終了処理"""
        if self.driver:
            logger.info("ブラウザを終了します")
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
    
    def _parse_number(self, text: str) -> int:
        """数値テキストを整数に変換（「1.2k」→1200など）"""
        if not text:
            return 0
        
        text = text.strip().lower()
        
        # 単位の処理
        multiplier = 1
        if 'k' in text:
            multiplier = 1000
            text = text.replace('k', '')
        elif 'm' in text:
            multiplier = 1000000
            text = text.replace('m', '')
        
        try:
            # カンマを除去し、小数を処理
            text = text.replace(',', '')
            value = float(text)
            return int(value * multiplier)
        except:
            return 0