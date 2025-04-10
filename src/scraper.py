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
            'text_content': self.text_content,  # 本文フィールドを追加
            'published_at_clean': 0,  # データ処理用のデフォルト値
        }
    
    def __str__(self) -> str:
        """記事データの文字列表現"""
        return f"Article('{self.title}', views={self.views}, likes={self.likes})"


class NoteDashboardScraper:
    """noteダッシュボードスクレイピングの中核クラス"""
    
    # noteサイトのURL
    NOTE_BASE_URL = "https://note.com"
    NOTE_LOGIN_URL = "https://note.com/login"
    NOTE_DASHBOARD_URL = "https://note.com/sitesettings/stats"  # 統計情報ダッシュボードURL
    
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
            'link': ['a[href*="/dashboard"]', '.dashboard-link', 'a[href="/dashboard/notes"]'],
            'articles_tab': ['a[href*="/dashboard/notes"]', '.articles-tab', 'a[href="/dashboard/notes"]'],
        },
        # 記事一覧（最新のセレクタを追加）
        'article_list': {
            'articles': ['.article-item', '.article-row', '.dashboard-notes_cardContainer__', '.noteItem', 'article', '.articleItem'],
            'title': ['.article-title', 'h3.title', '.noteItem-title', 'h2', 'h3', '.title'],
            'url': ['a.article-link', 'a[href*="/"]', 'a', '.noteItem-link', 'a[href*="note.com"]'],
            'published_at': ['.published-date', '.date', '.noteItem-date', 'time', '.publishDate'],
            'views': ['.view-count', '.views', '.noteItem-views', '.viewCount', '.stats-views', '.m-noteContent__viewCount', '.o-noteContentData__viewCount', '.o-noteContentStats__count'],
            'likes': ['.like-count', '.likes', '.noteItem-likes', '.likeCount', '.stats-likes'],
            'comments': ['.comment-count', '.comments', '.noteItem-comments', '.commentCount', '.stats-comments'],
        },
        # ページネーション
        'pagination': {
            'next_button': ['.pagination-next:not(.disabled)', '.next-page:not(.disabled)', 'button[aria-label="次のページ"]'],
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
        
        # タスクマネージャーでChromeDriverプロセスを終了させる
        try:
            import os
            import subprocess
            import time
            
            # Windows環境でのChromeDriver終了処理
            if os.name == 'nt':
                try:
                    # タスクキルでchromedriver.exeプロセスを強制終了
                    subprocess.run("taskkill /f /im chromedriver.exe", shell=True, 
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    logger.info("既存のchromedriver.exeプロセスを終了しました")
                    # 少し待機してプロセス終了を確実に
                    time.sleep(1)
                except Exception as e:
                    logger.debug(f"chromedriver.exeの終了処理中にエラー: {str(e)}")
        except Exception as e:
            logger.debug(f"プロセス終了処理中にエラー: {str(e)}")
        
        # 直接ドライバーを使用する方法に変更
        try:
            # Chrome Driverパスを直接指定（デフォルトはカレントディレクトリのドライバー）
            import os
            import sys
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            
            # システムによって実行ファイル名を変更
            driver_name = "chromedriver.exe" if sys.platform == "win32" else "chromedriver"
            driver_path = os.path.join(project_root, driver_name)
            
            # ドライバーが存在しない場合は標準のwebdriver-managerを使用
            if not os.path.exists(driver_path):
                logger.info(f"プロジェクトディレクトリにドライバーが見つからないため、標準の方法を使用します")
                try:
                    service = Service()
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    self.wait = WebDriverWait(self.driver, config.timeout)
                    logger.info("ブラウザの初期化が完了しました")
                except Exception as e:
                    logger.error(f"標準のブラウザ初期化に失敗しました: {str(e)}")
                    raise
            else:
                # プロジェクトディレクトリにあるドライバーを使用
                logger.info(f"ローカルのドライバーを使用します: {driver_path}")
                service = Service(executable_path=driver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                self.wait = WebDriverWait(self.driver, config.timeout)
                logger.info("ブラウザの初期化が完了しました (ローカルドライバー)")
                
        except Exception as e:
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
            
            # デバッグ用にページソースを保存
            self.save_page_source("login_page")
            
            # 少し待機してJSの実行を待つ
            time.sleep(3)
            
            logger.info("ログインフォームを入力しています...")

            # 最新のnoteサイトではログイン要素のセレクタが変更されている可能性があるため
            # 様々なセレクタを試みる
            
            # メールアドレス入力
            email_selectors = [
                'input[type="email"]', 
                'input[name="email"]',
                'input[placeholder="メールアドレス"]',
                '.o-login__mail input[type="email"]',
                '.o-login input[type="email"]'
            ]
            
            email_input = None
            for selector in email_selectors:
                try:
                    logger.debug(f"メールアドレスセレクタを試行: {selector}")
                    email_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if email_input:
                        logger.info(f"メールアドレス入力フィールドが見つかりました: {selector}")
                        break
                except NoSuchElementException:
                    continue
            
            if not email_input:
                # JavaScript実行を試みる
                logger.info("JavaScriptで入力フィールドを探します")
                try:
                    email_input = self.driver.execute_script("""
                        return document.querySelector('input[type="email"]') || 
                               document.querySelector('input[placeholder*="メール"]') ||
                               document.querySelector('input[placeholder*="mail"]');
                    """)
                except Exception as e:
                    logger.error(f"JavaScript実行エラー: {str(e)}")
            
            if not email_input:
                logger.error("メールアドレス入力フィールドが見つかりません")
                self.take_screenshot("email_not_found")
                return False
            
            email_input.send_keys(config.username)
            logger.info("メールアドレスを入力しました")
            
            # パスワード入力
            password_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                'input[placeholder="パスワード"]',
                '.o-login__mail input[type="password"]',
                '.o-login input[type="password"]'
            ]
            
            password_input = None
            for selector in password_selectors:
                try:
                    logger.debug(f"パスワードセレクタを試行: {selector}")
                    password_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if password_input:
                        logger.info(f"パスワード入力フィールドが見つかりました: {selector}")
                        break
                except NoSuchElementException:
                    continue
            
            if not password_input:
                # JavaScript実行を試みる
                logger.info("JavaScriptでパスワードフィールドを探します")
                try:
                    password_input = self.driver.execute_script("""
                        return document.querySelector('input[type="password"]') || 
                               document.querySelector('input[placeholder*="パスワード"]') ||
                               document.querySelector('input[placeholder*="password"]');
                    """)
                except Exception as e:
                    logger.error(f"JavaScript実行エラー: {str(e)}")
            
            if not password_input:
                logger.error("パスワード入力フィールドが見つかりません")
                self.take_screenshot("password_not_found")
                return False
            
            password_input.send_keys(config.password)
            logger.info("パスワードを入力しました")
            
            # ログインボタンクリック
            submit_selectors = [
                'button[type="submit"]', 
                'button.n-button--primary',
                '.o-login__button button',
                'button.a-button[data-type="primary"]',
                '.o-login__button .a-button'
            ]
            
            submit_button = None
            for selector in submit_selectors:
                try:
                    logger.debug(f"ログインボタンセレクタを試行: {selector}")
                    submit_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if submit_button:
                        logger.info(f"ログインボタンが見つかりました: {selector}")
                        break
                except NoSuchElementException:
                    continue
            
            if not submit_button:
                # JavaScript実行を試みる
                logger.info("JavaScriptでログインボタンを探します")
                try:
                    submit_button = self.driver.execute_script("""
                        return document.querySelector('button[type="submit"]') || 
                               document.querySelector('.o-login__button button') ||
                               document.querySelector('button.a-button[data-type="primary"]');
                    """)
                except Exception as e:
                    logger.error(f"JavaScript実行エラー: {str(e)}")
            
            if not submit_button:
                logger.error("ログインボタンが見つかりません")
                self.take_screenshot("submit_not_found")
                return False
            
            submit_button.click()
            logger.info("ログインボタンをクリックしました")
            
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
            logger.info("統計情報ダッシュボードへ移動しています...")
            
            # 統計情報ダッシュボードに直接アクセス
            logger.info("統計情報ダッシュボードに直接アクセスします")
            self.driver.get(self.NOTE_DASHBOARD_URL)
            
            # ページ読み込み待機
            time.sleep(3)
            
            # デバッグ用にページソースを保存
            self.save_page_source("dashboard_page")
            
            # 期間を「全期間」に変更する
            try:
                logger.info("データ表示期間を「全期間」に変更します")
                # 全期間ボタンを探す
                period_button_selectors = [
                    'button.btn:not(.is-active):contains("全期間")',
                    'li.m-buttonGroup__item:last-child button',
                    'ul[aria-label="表示期間切り替え"] li:last-child button'
                ]
                
                # JavaScriptを使って全期間ボタンをクリック
                clicked = self.driver.execute_script("""
                    const buttons = document.querySelectorAll('ul[aria-label="表示期間切り替え"] button');
                    for (const button of buttons) {
                        if (button.textContent.trim() === '全期間') {
                            if (!button.disabled && !button.classList.contains('is-active')) {
                                button.click();
                                return true;
                            } else if (button.classList.contains('is-active')) {
                                // すでに選択されている
                                return 'already-active';
                            }
                        }
                    }
                    return false;
                """)
                
                if clicked == "already-active":
                    logger.info("既に「全期間」が選択されています")
                elif clicked:
                    logger.info("「全期間」ボタンをクリックしました")
                    # ボタンクリック後にデータ読み込みを待機
                    time.sleep(2)
                else:
                    logger.warning("「全期間」ボタンが見つからないか、クリックできませんでした")
            except Exception as e:
                logger.warning(f"期間変更中にエラーが発生しました: {str(e)}")
            
            # 正しくダッシュボードに移動したことを確認
            if "/sitesettings/stats" in self.driver.current_url:
                logger.info("統計情報ダッシュボードへの移動に成功しました")
                return True
            else:
                logger.error("統計情報ダッシュボードへの移動に失敗しました")
                self.take_screenshot("dashboard_navigation_failed")
                return False
                
        except Exception as e:
            logger.error(f"ダッシュボード移動中にエラーが発生しました: {str(e)}")
            self.take_screenshot("dashboard_navigation_error")
            return False
    
    def extract_articles_from_current_page(self) -> List[Article]:
        """現在のページから記事データを抽出"""
        logger.info("統計情報ページから記事データを抽出しています...")
        
        page_articles = []
        
        try:
            # デバッグ用にページソースを保存
            self.save_page_source("stats_page")
            
            # *** 改善された記事データ抽出ロジック ***
            # JavaScriptを使用してnoteダッシュボードから直接データを抽出
            articles_data = self.driver.execute_script("""
                // 記事データを格納する配列
                const articles = [];
                
                // 統計情報テーブルを検索
                const table = document.querySelector('.o-statsContent__table');
                if (!table) return articles;
                
                // テーブル内の全ての行を取得
                const rows = table.querySelectorAll('tbody tr');
                if (!rows || rows.length === 0) return articles;
                
                // 各行から記事データを抽出
                rows.forEach(row => {
                    // 記事タイトルと URL の取得
                    const titleCell = row.querySelector('.o-statsContent__tableTitle');
                    if (!titleCell) return;
                    
                    const titleLink = titleCell.querySelector('a');
                    if (!titleLink) return;
                    
                    const title = titleLink.textContent.trim();
                    const url = titleLink.href;
                    
                    // ビュー数の取得 - ダッシュボードの表示値
                    const viewCell = row.querySelector('.o-statsContent__tableStat--type_view');
                    const views = viewCell ? viewCell.textContent.trim() : '0';
                    
                    // コメント数の取得
                    const commentCell = row.querySelector('.o-statsContent__tableStat--type_comment');
                    const comments = commentCell ? commentCell.textContent.trim() : '0';
                    
                    // いいね数(スキ)の取得
                    const likeCell = row.querySelector('.o-statsContent__tableStat--type_suki');
                    const likes = likeCell ? likeCell.textContent.trim() : '0';
                    
                    // 公開日は記事ページから取得するため空で設定
                    const published_at = '';
                    
                    articles.push({
                        title,
                        url,
                        published_at,
                        views,
                        likes,
                        comments
                    });
                });
                
                // debug: 全ての記事データをコンソールに出力
                console.log('Extracted article data:', articles);
                
                return articles;
            """)
            
            if articles_data and len(articles_data) > 0:
                logger.info(f"JavaScript経由で{len(articles_data)}件の記事データを抽出しました")
                for article_data in articles_data:
                    article = Article(
                        article_data['title'],
                        article_data['url'],
                        article_data['published_at']
                    )
                    article.views = self._parse_number(article_data['views'])
                    article.likes = self._parse_number(article_data['likes'])
                    article.comments = self._parse_number(article_data['comments'])
                    page_articles.append(article)
                    logger.debug(f"記事を抽出しました: {article.title}, ビュー数: {article.views}")
                
                logger.info(f"合計{len(page_articles)}件の記事を抽出しました")
                return page_articles
            
            # JavaScript抽出に失敗した場合は従来の方法を試す
            logger.warning("JavaScriptでの抽出に失敗しました。従来の方法を試みます。")
            
            # 従来のテーブル抽出方法
            # 統計情報ページの構造に合わせて記事を抽出
            table_selectors = [
                'table.o-statsContent__table',
                'table.statsTable',
                'table.article-stats-table',
                'table',
                '.table-container table',
                '.stats-container table'
            ]
            
            table = None
            for selector in table_selectors:
                try:
                    table = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if table:
                        logger.info(f"統計テーブルが見つかりました: {selector}")
                        break
                except NoSuchElementException:
                    continue
            
            if not table:
                logger.warning("統計テーブルが見つかりません")
                self.take_screenshot("no_stats_table")
                return []
            
            # 行要素を取得
            rows = None
            try:
                rows = table.find_elements(By.CSS_SELECTOR, 'tbody tr')
                logger.info(f"{len(rows)}件の記事行が見つかりました")
            except NoSuchElementException:
                logger.warning("テーブル内に行要素が見つかりません")
                self.take_screenshot("no_table_rows")
                return []
            
            # 各行から記事データを抽出
            for row in rows:
                try:
                    # タイトルとURLを含むセル
                    title_cell = row.find_elements(By.CSS_SELECTOR, 'td')[0]  # 最初の列を仮定
                    
                    # タイトルとURLを取得
                    title_link = title_cell.find_element(By.CSS_SELECTOR, 'a')
                    title = title_link.text.strip()
                    url = title_link.get_attribute('href')
                    
                    # 公開日を取得（3列目を仮定）
                    try:
                        date_cell = row.find_elements(By.CSS_SELECTOR, 'td')[2]
                        published_at = date_cell.text.strip()
                    except:
                        published_at = ""
                    
                    # 記事オブジェクト作成
                    article = Article(title, url, published_at)
                    
                    # ビュー数
                    try:
                        views_cell = row.find_elements(By.CSS_SELECTOR, 'td')[3]  # 4列目を仮定
                        article.views = self._parse_number(views_cell.text)
                        logger.debug(f"ビュー数を取得: {title} - {article.views}")
                    except:
                        pass
                    
                    # いいね数
                    try:
                        likes_cell = row.find_elements(By.CSS_SELECTOR, 'td')[4]  # 5列目を仮定
                        article.likes = self._parse_number(likes_cell.text)
                    except:
                        pass
                    
                    # コメント数
                    try:
                        comments_cell = row.find_elements(By.CSS_SELECTOR, 'td')[5]  # 6列目を仮定
                        article.comments = self._parse_number(comments_cell.text)
                    except:
                        pass
                    
                    page_articles.append(article)
                    logger.debug(f"記事を抽出しました: {article}")
                    
                except Exception as e:
                    logger.warning(f"行からのデータ抽出中にエラー: {str(e)}")
            
            if not page_articles:
                logger.warning("ページ内に記事要素が見つかりませんでした")
                self.take_screenshot("no_articles_found")
            else:
                logger.info(f"合計{len(page_articles)}件の記事を抽出しました")
            
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
            
            # 公開日時を取得
            try:
                # 公開日時を取得するための複数のセレクタを試す
                publication_date_selectors = [
                    ".o-noteContentHeader__date time",  # 新UIの公開日時
                    ".o-noteContentHeader time",        # 別のパターン
                    ".m-article__date time",            # 古いUIの公開日時
                    ".note-common-styles__date time",   # 別のパターン
                    "time",                             # シンプルにtimeタグを探す
                    "[datetime]",                       # datetime属性を持つ要素
                    ".o-noteContentData__date"          # 別パターン
                ]
                
                for selector in publication_date_selectors:
                    try:
                        date_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if date_element:
                            # まずはテキストコンテンツを試す
                            published_at = date_element.text.strip()
                            
                            # テキストが空の場合はdatetime属性を確認
                            if not published_at and date_element.get_attribute("datetime"):
                                published_at = date_element.get_attribute("datetime")
                            
                            if published_at:
                                article.published_at = published_at
                                logger.debug(f"記事ページから公開日時を取得: {article.published_at}")
                                break
                    except NoSuchElementException:
                        continue
                
                # セレクタで見つからない場合はJavaScriptで探す
                if not article.published_at:
                    logger.info("JavaScript経由で公開日時を取得します")
                    published_at = self.driver.execute_script("""
                        // 公開日時を含む可能性のある要素を探す
                        const dateElements = [
                            document.querySelector('.o-noteContentHeader__date time'),
                            document.querySelector('.o-noteContentHeader time'),
                            document.querySelector('.m-article__date time'),
                            document.querySelector('.note-common-styles__date time'),
                            document.querySelector('time'),
                            document.querySelector('[datetime]'),
                            document.querySelector('.o-noteContentData__date')
                        ];
                        
                        // 見つかった要素から日付情報を取得
                        for (const el of dateElements) {
                            if (el) {
                                // テキストコンテンツを確認
                                const dateText = el.textContent.trim();
                                if (dateText) return dateText;
                                
                                // datetime属性を確認
                                const dateAttr = el.getAttribute('datetime');
                                if (dateAttr) return dateAttr;
                            }
                        }
                        
                        // 日付のパターンを探す
                        const datePatterns = [
                            /\\d{4}[年/\\-]\\s*\\d{1,2}[月/\\-]\\s*\\d{1,2}[日]?/,  // 2023年10月1日 または 2023/10/1
                            /\\d{1,2}[月/\\-]\\s*\\d{1,2}[日]?,\\s*\\d{4}/,          // 10月1日, 2023
                            /\\d{4}-\\d{2}-\\d{2}/                               // 2023-10-01 (ISO形式)
                        ];
                        
                        const bodyText = document.body.textContent;
                        for (const pattern of datePatterns) {
                            const match = bodyText.match(pattern);
                            if (match) return match[0];
                        }
                        
                        return '';
                    """)
                    
                    if published_at:
                        article.published_at = published_at
                        logger.debug(f"JavaScriptで公開日時を取得: {article.published_at}")
            except Exception as e:
                logger.warning(f"記事ページからの公開日時取得に失敗しました: {article.title} - {str(e)}")
            
            # 記事本文を取得
            try:
                # 複数のセレクタを試す
                article_body_selectors = [
                    ".note-common-styles__textnote-body",
                    ".o-noteContentText",
                    "article .o-noteEmbedContainer",
                    ".m-textContent",
                    "article .note-body"
                ]
                
                for selector in article_body_selectors:
                    try:
                        article_body = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if article_body:
                            article.text_content = article_body.text
                            article.char_count = len(article.text_content)
                            logger.debug(f"記事の文字数: {article.char_count}")
                            break
                    except NoSuchElementException:
                        continue
                
                # セレクタで見つからない場合はJavaScriptで試す
                if not article.text_content:
                    logger.info("JavaScript経由で記事本文を取得します")
                    article_content = self.driver.execute_script("""
                        // 記事本文を含む可能性のある要素を探す
                        const contentElements = [
                            document.querySelector('.note-common-styles__textnote-body'),
                            document.querySelector('.o-noteContentText'),
                            document.querySelector('article .o-noteEmbedContainer'),
                            document.querySelector('.m-textContent'),
                            document.querySelector('article')
                        ];
                        
                        // 最初に見つかった要素のテキストを返す
                        for (const el of contentElements) {
                            if (el && el.textContent.trim()) {
                                return el.textContent.trim();
                            }
                        }
                        
                        // 何も見つからなければ全体のテキストを返す
                        return document.body.textContent.trim();
                    """)
                    
                    if article_content:
                        article.text_content = article_content
                        article.char_count = len(article_content)
                        logger.debug(f"JavaScriptで記事本文を取得しました: {article.char_count}文字")
            except Exception as e:
                logger.warning(f"記事本文の取得に失敗しました: {article.title} - {str(e)}")
            
            # ビュー数が未取得または0の場合は記事ページから取得を試みる
            if article.views <= 0:
                try:
                    # より多くのセレクタパターンを試す
                    view_count_selectors = [
                        ".o-noteContentData .viewCount",
                        ".o-noteContentData__item--views",
                        ".noteStat span[data-test='viewCount']",
                        ".viewCountText",
                        "span[title*='閲覧']",
                        ".o-noteContentStats__count",
                        ".m-noteContent__viewCount",
                        ".o-noteContentData__viewCount",
                        "span[title*='view']",
                        ".viewCount",
                        ".o-noteContentFooter .count",
                        "div[class*='viewCount']"
                    ]
                    
                    for selector in view_count_selectors:
                        try:
                            view_count_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                            if view_count_element:
                                view_count_text = view_count_element.text.strip()
                                article.views = self._parse_number(view_count_text)
                                logger.debug(f"記事ページからビュー数を取得: {article.views}")
                                if article.views > 0:  # 有効な値が取得できたら終了
                                    break
                        except NoSuchElementException:
                            continue
                    
                    # セレクタで見つからない場合はJavaScriptで試す
                    if article.views <= 0:
                        logger.info("JavaScript経由でビュー数を取得します")
                        view_count = self.driver.execute_script("""
                            // ビュー数を含む可能性のある要素を全て取得
                            const allElements = document.querySelectorAll('*');
                            
                            // テキストコンテンツが「閲覧」または「views」、「読者」、「view」を含む要素を探す
                            for (const el of allElements) {
                                const text = el.textContent.trim();
                                if ((text.includes('閲覧') || 
                                     text.includes('view') || 
                                     text.includes('読者') || 
                                     text.includes('View')) && 
                                    /\\d+/.test(text)) {
                                    return text;
                                }
                            }
                            
                            // ページ全体から数字と単位のパターンを検索
                            const viewPatterns = [
                                /(\\d+[\\.\\d]*)\\s*(views|回|閲覧)/i,
                                /(\\d+[\\.\\d]*)\\s*(views|回|閲覧|読者)/i,
                                /閲覧数[：:]\\s*(\\d+[\\.\\d]*)/i,
                                /views[：:]\\s*(\\d+[\\.\\d]*)/i
                            ];
                            
                            const bodyText = document.body.textContent;
                            for (const pattern of viewPatterns) {
                                const match = bodyText.match(pattern);
                                if (match && match[1]) {
                                    return match[1];
                                }
                            }
                            
                            return '';
                        """)
                        
                        if view_count:
                            article.views = self._parse_number(view_count)
                            logger.debug(f"JavaScriptでビュー数を取得: {article.views}")
                except Exception as e:
                    logger.warning(f"記事ページからのビュー数取得に失敗しました: {article.title} - {str(e)}")
            
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