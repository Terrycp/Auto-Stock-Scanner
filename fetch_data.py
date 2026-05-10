"""
Standalone data fetcher for stock scanner
Runs scraping logic without GUI - suitable for GitHub Actions or scheduled tasks
"""
import time
import sqlite3
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from io import StringIO

# --- Configuration ---
DB_NAME = "stock_data.db"
URL_LIST = [
    ("Bullish Catapult", "https://stockcharts.com/def/servlet/SC.scan?s=TSAL[t.t_eq_s]![as0,20,tv_gt_40000]![ya_eq_1]&report=predefall"),
    ("Quadruple Top Breakout", "https://stockcharts.com/def/servlet/SC.scan?s=TSAL[t.t_eq_s]![as0,20,tv_gt_40000]![yj_eq_1]&report=predefall"),
    ("Morning Star", "https://stockcharts.com/def/servlet/SC.scan?s=TSAL[t.t_eq_s]![as0,20,tv_gt_40000]![wh_eq_1]&report=predefall"),
    ("Bear Trap", "https://stockcharts.com/def/servlet/SC.scan?scanId=pf-bear-trap&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
    ("Bearish Signal Reversal", "https://stockcharts.com/def/servlet/SC.scan?scanId=pf-bearish-signal-reversal&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
    ("Bullish Triangle", "https://stockcharts.com/def/servlet/SC.scan?scanId=pf-bullish-triangle&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
    ("Bullish Engulfing", "https://stockcharts.com/def/servlet/SC.scan?scanId=bullish-engulfing&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
    ("Three White Soldiers", "https://stockcharts.com/def/servlet/SC.scan?scanId=three-white-soldiers&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
    ("Bullish MACD Crossover", "https://stockcharts.com/def/servlet/SC.scan?scanId=bullish-macd-crossovers&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
    ("Oversold Improving RSI", "https://stockcharts.com/def/servlet/SC.scan?scanId=oversold-with-an-improving-rsi&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
    ("Piercing Line", "https://stockcharts.com/def/servlet/SC.scan?scanId=piercing-line&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
    ("Underperforming SPY 52W Low", "https://stockcharts.com/def/servlet/SC.scan?scanId=underperforming-spy-52-week-relative-lows&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
    ("Underperforming SPY 9M Low", "https://stockcharts.com/def/servlet/SC.scan?scanId=underperforming-spy-9-month-relative-lows&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
    ("Underperforming SPY 6M Low", "https://stockcharts.com/def/servlet/SC.scan?scanId=underperforming-spy-6-month-relative-lows&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
    ("New 52W Low", "https://stockcharts.com/def/servlet/SC.scan?scanId=new-52-week-lows&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
    ("New 9M Low", "https://stockcharts.com/def/servlet/SC.scan?scanId=new-9-month-lows&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
    ("New 6M Low", "https://stockcharts.com/def/servlet/SC.scan?scanId=new-6-month-lows&filters=market-cap-greater-than-100m%2Cus-stocks&sorter=predefIntraday&rankby=true"),
]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
STANDARD_COLS = [
    "Symbol",
    "Name",
    "Exchange",
    "Sector",
    "Industry",
    "Last",
    "Volume",
    "SCTR",
    "U",
    "Daily MACD Line(12,26,9,Daily Close)",
    "Daily RSI(14,Daily Close)"
]

# --- Database Setup ---
def add_column_if_not_exists(db_name, table_name, column_name, column_type):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    
    if column_name not in columns:
        cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN "{column_name}" {column_type}')
        print(f"Added column: {column_name}")
    
    conn.commit()
    conn.close()

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stocks (
        FileName TEXT,
        Symbol TEXT,
        Name TEXT,
        Exchange TEXT,
        Sector TEXT,
        Industry TEXT,
        Last REAL,
        Volume INTEGER,
        SCTR REAL,
        U TEXT,
        Date TEXT
    )
    """)
    conn.commit()
    conn.close()

def add_missing_columns_dynamic(df, table_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_cols = [row[1] for row in cursor.fetchall()]
    
    for col in df.columns:
        if col not in existing_cols:
            cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN "{col}" TEXT')
            print(f"Added new column: {col}")
    
    conn.commit()
    conn.close()

# --- Scraping Function ---
def fetch_data():
    """Fetch stock data from URLs and update database"""
    init_db()
    conn = sqlite3.connect(DB_NAME)
    
    for scan_name, link in URL_LIST:
        time.sleep(1)
        try:
            resp = requests.get(link, headers=HEADERS)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # --- Extract date from website ---
            scan_name_tag = soup.find(class_="scan-name")
            if scan_name_tag:
                file_name = scan_name_tag.get_text(strip=True)
            else:
                file_name = "Unknown Scan"
            
            date_tag = soup.find(id="table-date")
            if date_tag:
                raw_datetime = date_tag.get_text(strip=True)
            else:
                raw_datetime = None
            
            if raw_datetime:
                try:
                    parsed_date = datetime.strptime(raw_datetime, "%d %b %Y, %I:%M %p")
                    formatted_date = parsed_date.strftime("%Y-%m-%d")
                except Exception as e:
                    print("Date parse error:", e)
                    formatted_date = datetime.now().strftime("%Y-%m-%d")
            else:
                formatted_date = datetime.now().strftime("%Y-%m-%d")
            
            table = soup.find("table", {"id": "sccDataTable"})
            if not table:
                print(f"No table found for {scan_name}")
                continue
            
            df_new = pd.read_html(StringIO(str(table)))[0]
            # Remove index column if exists
            if df_new.columns[0].startswith("Unnamed"):
                df_new = df_new.iloc[:, 1:]
            
            # Rename columns safely (strip spaces)
            df_new.columns = [col.strip() for col in df_new.columns]
            
            # Ensure all expected columns exist
            for col in STANDARD_COLS:
                if col not in df_new.columns:
                    df_new[col] = None
            
            # Reorder strictly
            df_new = df_new[STANDARD_COLS]
            extra_cols = [col for col in df_new.columns if col not in STANDARD_COLS]
            df_new = df_new[STANDARD_COLS + extra_cols]
            df_new["FileName"] = file_name
            df_new["Date"] = formatted_date
            
            # Get existing symbols for this scan
            cursor = conn.cursor()
            cursor.execute(
                "SELECT Symbol FROM stocks WHERE FileName=? AND Date=?",
                (file_name, formatted_date)
            )
            old_symbols = [row[0] for row in cursor.fetchall()]
            
            # Filter to only new symbols
            new_symbols = df_new[~df_new["Symbol"].isin(old_symbols)]
            
            if len(new_symbols) > 0:
                # --- Ensure DB has all columns first ---
                add_missing_columns_dynamic(new_symbols, "stocks")
                # --- Insert only new data ---
                new_symbols.to_sql("stocks", conn, if_exists="append", index=False)
                print(f"Inserted {len(new_symbols)} new records for {file_name}")
            else:
                print(f"No new records for {file_name}")
                
        except Exception as e:
            print(f"Error fetching {scan_name}: {e}")
    
    conn.close()
    print("✅ Fetch & Update complete!")

if __name__ == "__main__":
    fetch_data()
