# SharePulse - Enhanced UI Version
# Updated for new CSV format (Announcements only - Twitter remains same)

from flask import Flask, render_template_string, request, jsonify, send_from_directory
import pandas as pd
import os
from pathlib import Path
import time
import re

app = Flask(__name__)

# Use relative path - works on any platform (Windows/Linux/Render)
DATA_FOLDER = os.path.join(os.path.dirname(__file__), 'data', 'results')
# LOGO_FOLDER = r"C:\Users\saiameth\Desktop\data\logos"  # Disabled - no logos available

# ============== HELPER FUNCTIONS ==============
def convert_bold(text):
    """Convert **text** to <strong>text</strong>"""
    if not text or pd.isna(text):
        return ''
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', str(text))

# ============== CLASSIFICATION SYSTEM ==============
CLASSIFICATIONS = {
    'trading_window': {
        'name': 'Trading Window',
        'icon': '🔒',
        'color': '#6B7280',
        'bg': '#F3F4F6',
        'keywords': ['trading window', 'closure of trading']
    },
    'order_contract': {
        'name': 'Orders & Contracts',
        'icon': '📋',
        'color': '#059669',
        'bg': '#D1FAE5',
        'keywords': ['award', 'order', 'receipt of order', 'contract']
    },
    'financial_results': {
        'name': 'Financial Results',
        'icon': '📊',
        'color': '#2563EB',
        'bg': '#DBEAFE',
        'keywords': ['financial result', 'quarterly', 'annual result', 'audited', 'unaudited']
    },
    'board_meeting': {
        'name': 'Board Meeting',
        'icon': '👥',
        'color': '#7C3AED',
        'bg': '#EDE9FE',
        'keywords': ['board meeting', 'meeting of board']
    },
    'shareholder_meeting': {
        'name': 'Shareholder Meeting',
        'icon': '🗳️',
        'color': '#DB2777',
        'bg': '#FCE7F3',
        'keywords': ['shareholder meeting', 'agm', 'egm', 'postal ballot', 'voting']
    },
    'dividend': {
        'name': 'Dividend',
        'icon': '💰',
        'color': '#CA8A04',
        'bg': '#FEF3C7',
        'keywords': ['dividend', 'interim dividend', 'final dividend']
    },
    'acquisition': {
        'name': 'Acquisitions & SAST',
        'icon': '🤝',
        'color': '#EA580C',
        'bg': '#FFEDD5',
        'keywords': ['sast', 'acquisition', 'takeover', 'reg. 29', 'regulation 29']
    },
    'disclosure': {
        'name': 'Disclosures',
        'icon': '📢',
        'color': '#0891B2',
        'bg': '#CFFAFE',
        'keywords': ['disclosure', 'material issue', 'reg 23', 'regulation 23', 'lodr']
    },
    'corporate_action': {
        'name': 'Corporate Action',
        'icon': '⚡',
        'color': '#DC2626',
        'bg': '#FEE2E2',
        'keywords': ['bonus', 'split', 'rights issue', 'buyback', 'corporate action']
    },
    'appointment': {
        'name': 'Appointments',
        'icon': '👔',
        'color': '#4F46E5',
        'bg': '#E0E7FF',
        'keywords': ['appointment', 'resignation', 'cessation', 'director', 'kmp', 'key managerial']
    },
    'litigation': {
        'name': 'Legal & Appeals',
        'icon': '⚖️',
        'color': '#BE123C',
        'bg': '#FFE4E6',
        'keywords': ['appeal', 'litigation', 'legal', 'court', 'nclt', 'sebi order']
    },
    'general': {
        'name': 'General Updates',
        'icon': '📌',
        'color': '#64748B',
        'bg': '#F1F5F9',
        'keywords': ['update', 'general', 'announcement']
    }
}

def classify_announcement(subject):
    """Classify announcement based on subject keywords"""
    if not subject or pd.isna(subject):
        return 'general'
    
    subject_lower = str(subject).lower()
    
    for class_id, config in CLASSIFICATIONS.items():
        for keyword in config['keywords']:
            if keyword in subject_lower:
                return class_id
    
    return 'general'

def get_classification_info(class_id):
    """Get classification details"""
    return CLASSIFICATIONS.get(class_id, CLASSIFICATIONS['general'])

# ============== CACHING SYSTEM ==============
class DataCache:
    def __init__(self, ttl_seconds=300):
        self.data = None
        self.last_loaded = 0
        self.ttl = ttl_seconds
    
    def get_data(self):
        current_time = time.time()
        if self.data is None or (current_time - self.last_loaded) > self.ttl:
            self.data = self._load_from_disk()
            self.last_loaded = current_time
            print(f"[Cache] Data reloaded at {time.strftime('%H:%M:%S')}")
        return self.data
    
    def _detect_format(self, df):
        """Detect if CSV is new format (announcements), twitter format, or old format (mixed)"""
        new_format_cols = ['Company', 'Scrip_Code', 'Category', 'KeyInsights', 'PDF_Link']
        old_format_cols = ['COMPANY', 'COMPANY TYPE', 'SUMMARY', 'SOURCE_LINK']
        twitter_format_cols = ['Company_Name', 'Tweet_URL', 'Unified_Summary', 'channel_name']

        df_cols = list(df.columns)

        # Check for Twitter format
        twitter_matches = sum(1 for col in twitter_format_cols if col in df_cols)

        # Check for new announcement format
        new_matches = sum(1 for col in new_format_cols if col in df_cols)

        # Check for old format
        df_cols_upper = [col.upper() for col in df_cols]
        old_matches = sum(1 for col in old_format_cols if col in df_cols_upper)

        if twitter_matches >= 3:
            return 'new_twitter'
        elif new_matches >= 3:
            return 'new_announcement'
        elif old_matches >= 2:
            return 'old_format'
        return 'unknown'
    
    def _normalize_new_format(self, df):
        """Convert new announcement CSV format to standard format"""
        normalized = pd.DataFrame()
        
        normalized['COMPANY'] = df['Company'] if 'Company' in df.columns else df.get('COMPANY', 'Unknown')
        normalized['COMPANY TYPE'] = 'Announcement'
        
        # Date priority: Disseminated_Time > Received_Time > Scrape_DateTime
        # Try multiple date formats: handles both / and - separators automatically
        def parse_date(date_series):
            """Try multiple date formats - handles / and - separators"""
            formats_to_try = [
                # Slash formats (DD/MM/YYYY)
                '%d/%m/%Y %H:%M',      # 26/12/2025 13:23
                '%d/%m/%Y %H:%M:%S',   # 26/12/2025 13:23:00
                '%d/%m/%Y',            # 26/12/2025
                
                # Dash formats (DD-MM-YYYY)
                '%d-%m-%Y %H:%M',      # 26-12-2025 13:23
                '%d-%m-%Y %H:%M:%S',   # 26-12-2025 13:23:00
                '%d-%m-%Y',            # 26-12-2025
                
                # ISO formats (YYYY-MM-DD)
                '%Y-%m-%d %H:%M:%S',   # 2025-12-26 13:23:00
                '%Y-%m-%d %H:%M',      # 2025-12-26 13:23
                '%Y-%m-%d',            # 2025-12-26
                
                # ISO with slash (YYYY/MM/DD)
                '%Y/%m/%d %H:%M:%S',   # 2025/12/26 13:23:00
                '%Y/%m/%d %H:%M',      # 2025/12/26 13:23
                '%Y/%m/%d',            # 2025/12/26
                
                # Month name formats
                '%d %b %Y',            # 26 Dec 2025
                '%d %B %Y',            # 26 December 2025
                '%b %d, %Y',           # Dec 26, 2025
                '%B %d, %Y',           # December 26, 2025
            ]
            
            # Clean the series - strip whitespace
            clean_series = date_series.astype(str).str.strip()
            
            for fmt in formats_to_try:
                try:
                    parsed = pd.to_datetime(clean_series, format=fmt, errors='coerce')
                    # If more than 50% parsed successfully, use this format
                    valid_count = parsed.notna().sum()
                    if valid_count > 0 and valid_count >= len(date_series) * 0.5:
                        print(f"[Date Parser] Using format: {fmt} ({valid_count}/{len(date_series)} parsed)")
                        return parsed.dt.strftime('%Y-%m-%d')
                except Exception as e:
                    continue
            
            # Fallback: let pandas infer the format with dayfirst=True (for DD/MM/YYYY preference)
            try:
                parsed = pd.to_datetime(clean_series, dayfirst=True, errors='coerce')
                valid_count = parsed.notna().sum()
                if valid_count > 0:
                    print(f"[Date Parser] Using pandas auto-detect ({valid_count}/{len(date_series)} parsed)")
                    return parsed.dt.strftime('%Y-%m-%d')
            except:
                pass
            
            print("[Date Parser] WARNING: Could not parse dates, using N/A")
            return pd.Series(['N/A'] * len(date_series))
        
        if 'Disseminated_Time' in df.columns and df['Disseminated_Time'].notna().any():
            normalized['DATES'] = parse_date(df['Disseminated_Time'])
        elif 'Received_Time' in df.columns and df['Received_Time'].notna().any():
            normalized['DATES'] = parse_date(df['Received_Time'])
        elif 'Scrape_DateTime' in df.columns and df['Scrape_DateTime'].notna().any():
            normalized['DATES'] = parse_date(df['Scrape_DateTime'])
        else:
            normalized['DATES'] = 'N/A'
        
        normalized['SUMMARY'] = df.get('KeyInsights', df.get('Subject', ''))
        normalized['SOURCE_LINK'] = df.get('PDF_Link', '')
        normalized['SCRIP_CODE'] = df.get('Scrip_Code', '')
        normalized['CATEGORY'] = df.get('Category', df.get('Subject', ''))
        normalized['HEADLINE'] = df.get('Headline', '')
        normalized['RECEIVED_TIME'] = df.get('Received_Time', '')
        normalized['DISSEMINATED_TIME'] = df.get('Disseminated_Time', '')
        normalized['PDF_SIZE'] = df.get('PDF_Size', '')
        normalized['TWEET_URL'] = ''
        normalized['CHANNEL_NAME'] = ''
        
        return normalized
    
    def _normalize_old_format(self, df):
        """Ensure old format has all expected columns"""
        df.columns = [col.strip().upper() for col in df.columns]

        expected_cols = ['COMPANY', 'COMPANY TYPE', 'DATES', 'SUMMARY', 'SOURCE_LINK',
                        'TWEET_URL', 'CHANNEL_NAME', 'SCRIP_CODE', 'CATEGORY',
                        'HEADLINE', 'RECEIVED_TIME', 'DISSEMINATED_TIME', 'PDF_SIZE']

        for col in expected_cols:
            if col not in df.columns:
                df[col] = ''

        return df

    def _normalize_twitter_format(self, df):
        """Convert new Twitter CSV format to standard format"""
        normalized = pd.DataFrame()

        # Map Company_Name to COMPANY
        normalized['COMPANY'] = df.get('Company_Name', 'Unknown')
        normalized['COMPANY TYPE'] = 'Twitter'

        # Parse dates - use the 'date' column
        def parse_date(date_series):
            """Parse Twitter date format"""
            formats_to_try = [
                '%Y-%m-%dT%H:%M:%S',   # 2025-12-26T03:27:49
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d',
                '%d/%m/%Y',
                '%d-%m-%Y',
            ]

            clean_series = date_series.astype(str).str.strip()

            for fmt in formats_to_try:
                try:
                    parsed = pd.to_datetime(clean_series, format=fmt, errors='coerce')
                    valid_count = parsed.notna().sum()
                    if valid_count > 0 and valid_count >= len(date_series) * 0.5:
                        print(f"[Twitter Date Parser] Using format: {fmt} ({valid_count}/{len(date_series)} parsed)")
                        return parsed.dt.strftime('%Y-%m-%d')
                except Exception:
                    continue

            # Fallback
            try:
                parsed = pd.to_datetime(clean_series, dayfirst=True, errors='coerce')
                valid_count = parsed.notna().sum()
                if valid_count > 0:
                    print(f"[Twitter Date Parser] Using pandas auto-detect ({valid_count}/{len(date_series)} parsed)")
                    return parsed.dt.strftime('%Y-%m-%d')
            except:
                pass

            print("[Twitter Date Parser] WARNING: Could not parse dates, using N/A")
            return pd.Series(['N/A'] * len(date_series))

        if 'date' in df.columns and df['date'].notna().any():
            normalized['DATES'] = parse_date(df['date'])
        else:
            normalized['DATES'] = 'N/A'

        # Clean Twitter summary - remove AI metadata lines
        def clean_twitter_summary(text):
            """Remove first 2 lines: RELEVANT line and Sources line"""
            if not text or pd.isna(text):
                return ''

            text_str = str(text).strip()
            lines = text_str.split('\n')

            # Remove first 2 lines if they contain metadata
            if len(lines) >= 2:
                # Check if first line contains "RELEVANT"
                if 'RELEVANT' in lines[0].upper() or 'Sources:' in lines[1]:
                    # Skip first 2 lines (metadata)
                    lines = lines[2:]

            # Filter out empty lines and join
            cleaned_lines = [line.strip() for line in lines if line.strip()]
            cleaned = '\n'.join(cleaned_lines)

            # If still empty or too short, return original without first 2 lines
            if not cleaned or len(cleaned) < 10:
                return text_str

            return cleaned

        # Use Unified_Summary or Overall_Company_Summary for SUMMARY
        if 'Unified_Summary' in df.columns:
            normalized['SUMMARY'] = df['Unified_Summary'].apply(clean_twitter_summary)
        elif 'Overall_Company_Summary' in df.columns:
            normalized['SUMMARY'] = df['Overall_Company_Summary'].apply(clean_twitter_summary)
        else:
            normalized['SUMMARY'] = ''

        # Twitter-specific fields
        normalized['TWEET_URL'] = df.get('Tweet_URL', '')
        normalized['CHANNEL_NAME'] = df.get('channel_name', '')

        # External links as SOURCE_LINK if available
        normalized['SOURCE_LINK'] = df.get('External_URLs', '')

        # Empty fields for announcement-specific columns
        normalized['SCRIP_CODE'] = ''
        normalized['CATEGORY'] = ''
        normalized['HEADLINE'] = ''
        normalized['RECEIVED_TIME'] = ''
        normalized['DISSEMINATED_TIME'] = ''
        normalized['PDF_SIZE'] = ''

        return normalized
    
    def _load_from_disk(self):
        all_data = []
        data_path = Path(DATA_FOLDER)
        
        if not data_path.exists():
            print(f"Warning: Data folder {DATA_FOLDER} does not exist!")
            return pd.DataFrame()
        
        for csv_file in data_path.glob("*.csv"):
            try:
                df = pd.read_csv(csv_file)
                
                format_type = self._detect_format(df)
                print(f"Loaded: {csv_file.name} ({len(df)} rows) - Format: {format_type}")

                if format_type == 'new_announcement':
                    df = self._normalize_new_format(df)
                elif format_type == 'new_twitter':
                    df = self._normalize_twitter_format(df)
                elif format_type == 'old_format':
                    df = self._normalize_old_format(df)
                else:
                    df.columns = [col.strip().upper() for col in df.columns]
                
                all_data.append(df)
                
            except Exception as e:
                print(f"Error loading {csv_file}: {e}")
        
        if all_data:
            combined = pd.concat(all_data, ignore_index=True)
            combined.columns = [col.strip().upper() for col in combined.columns]
            return combined
        return pd.DataFrame()
    
    def refresh(self):
        self.data = self._load_from_disk()
        self.last_loaded = time.time()
        return self.data

cache = DataCache(ttl_seconds=300)

def get_data():
    return cache.get_data()

# ============== ENHANCED HTML TEMPLATE ==============

SEARCH_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stock Announcements</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #C45A35;
            --primary-hover: #A84D2E;
            --primary-light: #FEF3EE;
            --twitter: #1D9BF0;
            --twitter-hover: #1A8CD8;
            --twitter-light: #EEF6FF;
            --bg: #F8F9FA;
            --card-bg: #FFFFFF;
            --text-primary: #1A1A1A;
            --text-secondary: #555555;
            --text-muted: #888888;
            --border: #E8E8E8;
            --border-light: #F0F0F0;
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.04);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
            --shadow-lg: 0 12px 24px rgba(0,0,0,0.12);
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg);
            color: var(--text-primary);
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
        }
        
        .top-bar {
            background: var(--card-bg);
            border-bottom: 1px solid var(--border);
            padding: 12px 24px;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: var(--shadow-sm);
        }
        .top-bar-inner {
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
        }
        
        .search-container { flex: 1; max-width: 480px; }
        .search-box {
            display: flex;
            background: var(--bg);
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
            overflow: hidden;
            transition: all 0.2s;
        }
        .search-box:focus-within {
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(196, 90, 53, 0.1);
        }
        .search-input {
            flex: 1;
            border: none;
            background: transparent;
            padding: 10px 14px;
            font-size: 0.9rem;
            font-family: inherit;
            color: var(--text-primary);
            outline: none;
        }
        .search-input::placeholder { color: var(--text-muted); }
        .search-btn {
            background: var(--primary);
            border: none;
            padding: 10px 20px;
            color: white;
            font-weight: 600;
            font-size: 0.85rem;
            font-family: inherit;
            cursor: pointer;
            transition: background 0.2s;
        }
        .search-btn:hover { background: var(--primary-hover); }
        
        .filters {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .date-input {
            display: flex;
            align-items: center;
            gap: 6px;
            background: var(--bg);
            padding: 8px 12px;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
            font-size: 0.8rem;
        }
        .date-input label { color: var(--text-muted); font-weight: 500; }
        .date-input input {
            border: none;
            background: transparent;
            font-family: inherit;
            font-size: 0.8rem;
            color: var(--text-primary);
            outline: none;
            width: 110px;
        }
        .clear-btn {
            padding: 8px 14px;
            background: transparent;
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            color: var(--text-muted);
            font-size: 0.8rem;
            font-family: inherit;
            cursor: pointer;
            transition: all 0.2s;
        }
        .clear-btn:hover { 
            background: var(--bg); 
            border-color: var(--primary);
            color: var(--primary);
        }
        
        .main {
            max-width: 1400px;
            margin: 0 auto;
            padding: 24px;
        }
        
        .section-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 24px;
        }
        .section-title {
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .section-title::before {
            content: '';
            width: 4px;
            height: 20px;
            background: var(--primary);
            border-radius: 2px;
        }
        .header-meta {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .date-badge {
            background: var(--primary-light);
            color: var(--primary);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
        }
        .stats-badge {
            color: var(--text-muted);
            font-size: 0.85rem;
        }
        
        .columns {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
        }
        
        .column {
            background: var(--card-bg);
            border-radius: var(--radius-lg);
            border: 1px solid var(--border);
            overflow: hidden;
        }
        
        .column-header {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-light);
            background: linear-gradient(to bottom, #FAFAFA, #FFFFFF);
        }
        .column-icon {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .column-icon.ann { background: var(--primary-light); }
        .column-icon.twt { background: var(--twitter-light); }
        .column-icon svg { width: 16px; height: 16px; }
        .column-icon.ann svg { fill: var(--primary); }
        .column-icon.twt svg { fill: var(--twitter); }
        
        .column-title {
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-primary);
            flex: 1;
        }
        .column-count {
            background: var(--bg);
            color: var(--text-muted);
            padding: 4px 10px;
            border-radius: 10px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        
        .cards-container {
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            max-height: 600px;
            overflow-y: auto;
        }
        .cards-container::-webkit-scrollbar { width: 6px; }
        .cards-container::-webkit-scrollbar-track { background: transparent; }
        .cards-container::-webkit-scrollbar-thumb { 
            background: var(--border); 
            border-radius: 3px;
        }
        
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border-light);
            border-radius: var(--radius-md);
            padding: 16px;
            cursor: pointer;
            transition: all 0.2s ease;
            position: relative;
        }
        .card:hover {
            border-color: var(--primary);
            box-shadow: var(--shadow-md);
            transform: translateY(-2px);
        }
        .card.twitter:hover { border-color: var(--twitter); }
        
        .card-top {
            display: flex;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 12px;
        }
        
        .avatar {
            width: 40px;
            height: 40px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 0.9rem;
            color: white;
            flex-shrink: 0;
            background: linear-gradient(135deg, var(--primary) 0%, #E07850 100%);
        }
        .card.twitter .avatar {
            background: linear-gradient(135deg, var(--twitter) 0%, #5AB8F5 100%);
        }
        .avatar img {
            width: 100%;
            height: 100%;
            object-fit: contain;
            border-radius: 10px;
            padding: 4px;
            background: #F5F5F5;
        }
        
        .card-info { flex: 1; min-width: 0; }
        .card-company {
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 2px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .card-date {
            font-size: 0.8rem;
            color: var(--text-muted);
        }
        
        .card-right {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 6px;
            flex-shrink: 0;
        }
        
        .class-badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-size: 0.68rem;
            font-weight: 500;
            padding: 4px 10px;
            border-radius: 12px;
            white-space: nowrap;
        }
        .class-icon { font-size: 0.75rem; }
        
        .more-badge {
            background: var(--primary);
            color: white;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.7rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .card.twitter .more-badge { background: var(--twitter); }
        
        .card-summary {
            font-size: 0.85rem;
            color: var(--text-secondary);
            line-height: 1.5;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            margin-bottom: 12px;
        }
        
        .card-footer {
            display: flex;
            justify-content: flex-end;
        }
        .view-btn {
            display: flex;
            align-items: center;
            gap: 4px;
            color: var(--primary);
            font-size: 0.8rem;
            font-weight: 600;
            text-decoration: none;
        }
        .card.twitter .view-btn { color: var(--twitter); }
        .view-btn svg { width: 14px; height: 14px; fill: currentColor; }
        
        .loading {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 40px;
            color: var(--text-muted);
            gap: 12px;
        }
        .spinner {
            width: 32px;
            height: 32px;
            border: 3px solid var(--border);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        
        .empty {
            text-align: center;
            padding: 40px;
            color: var(--text-muted);
            font-size: 0.9rem;
        }
        
        .results-section { display: none; }
        .results-section.active { display: block; }
        .latest-section.hidden { display: none; }
        
        .results-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
            max-width: 700px;
        }
        .result-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 16px 20px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .result-card:hover {
            border-color: var(--primary);
            transform: translateX(4px);
            box-shadow: var(--shadow-sm);
        }
        .result-name {
            font-size: 1rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 6px;
        }
        .result-meta {
            display: flex;
            gap: 16px;
            font-size: 0.8rem;
            color: var(--text-muted);
        }
        
        .footer {
            text-align: center;
            padding: 24px;
            color: var(--text-muted);
            font-size: 0.8rem;
            border-top: 1px solid var(--border);
            margin-top: 40px;
        }
        
        @media (max-width: 1000px) {
            .columns { grid-template-columns: 1fr; }
            .top-bar-inner { flex-wrap: wrap; }
            .search-container { order: 3; flex: 100%; max-width: none; margin-top: 12px; }
        }
        @media (max-width: 600px) {
            .filters { flex-wrap: wrap; width: 100%; }
            .date-input { flex: 1; }
        }
    </style>
</head>
<body>
    <header class="top-bar">
        <div class="top-bar-inner">
            <div class="search-container">
                <form class="search-box" id="searchForm">
                    <input type="text" class="search-input" id="searchInput" 
                           placeholder="Search company (e.g., Reliance, HDFC, Tata...)" autocomplete="off">
                    <button type="submit" class="search-btn">Search</button>
                </form>
            </div>
            
            <div class="filters">
                <div class="date-input">
                    <label>From</label>
                    <input type="date" id="dateFrom">
                </div>
                <div class="date-input">
                    <label>To</label>
                    <input type="date" id="dateTo">
                </div>
                <button class="clear-btn" id="clearBtn">Clear</button>
            </div>
        </div>
    </header>
    
    <main class="main">
        <section id="latestSection" class="latest-section">
            <div class="section-header">
                <h1 class="section-title">Latest Updates</h1>
                <div class="header-meta">
                    <span class="date-badge" id="dateBadge">Loading...</span>
                    <span class="stats-badge" id="statsBadge"></span>
                </div>
            </div>
            
            <div class="columns">
                <div class="column">
                    <div class="column-header">
                        <div class="column-icon ann">
                            <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>
                        </div>
                        <span class="column-title">Announcements</span>
                        <span class="column-count" id="annCount">0</span>
                    </div>
                    <div class="cards-container" id="annCards">
                        <div class="loading"><div class="spinner"></div>Loading...</div>
                    </div>
                </div>
                
                <div class="column">
                    <div class="column-header">
                        <div class="column-icon twt">
                            <svg viewBox="0 0 24 24"><path d="M23 3a10.9 10.9 0 0 1-3.14 1.53 4.48 4.48 0 0 0-7.86 3v1A10.66 10.66 0 0 1 3 4s-4 9 5 13a11.64 11.64 0 0 1-7 2c9 5 20 0 20-11.5a4.5 4.5 0 0 0-.08-.83A7.72 7.72 0 0 0 23 3z"/></svg>
                        </div>
                        <span class="column-title">Twitter Updates</span>
                        <span class="column-count" id="twtCount">0</span>
                    </div>
                    <div class="cards-container" id="twtCards">
                        <div class="loading"><div class="spinner"></div>Loading...</div>
                    </div>
                </div>
            </div>
        </section>
        
        <section id="resultsSection" class="results-section">
            <div class="section-header">
                <h1 class="section-title">Search Results</h1>
            </div>
            <div class="results-list" id="resultsList"></div>
        </section>
    </main>
    
    <footer class="footer" id="footer"></footer>

    <script>
        var searchInput = document.getElementById('searchInput');
        var latestSection = document.getElementById('latestSection');
        var resultsSection = document.getElementById('resultsSection');
        var resultsList = document.getElementById('resultsList');
        var annCards = document.getElementById('annCards');
        var twtCards = document.getElementById('twtCards');
        var dateBadge = document.getElementById('dateBadge');
        var dateFrom = document.getElementById('dateFrom');
        var dateTo = document.getElementById('dateTo');

        // Infinite scroll state
        var annOffset = 0;
        var twtOffset = 0;
        var hasMoreAnn = true;
        var hasMoreTwt = true;
        var isLoadingAnn = false;
        var isLoadingTwt = false;

        // Logo functionality disabled - using initials only
        var logos = {};

        fetch('/api/stats').then(function(r) { return r.json(); }).then(function(d) {
            document.getElementById('statsBadge').textContent = d.total_companies + ' companies';
            document.getElementById('footer').textContent = 
                'Tracking ' + d.total_records + ' updates from ' + d.total_companies + ' companies';
        });
        
        function getAvatar(company, isTwitter) {
            // Returns company initials (logo functionality disabled)
            var initials = company.split(' ').map(function(w) { return w[0]; }).join('').substring(0, 2).toUpperCase();
            return initials;
        }
        
        function extractSummary(text) {
            if (!text) return '';

            // Clean up markdown formatting
            var clean = text.replace(/\\*\\*/g, '').replace(/\\*/g, '');

            // Split by newlines to get bullet points or sentences
            var lines = clean.split(/\\n/).filter(function(line) { return line.trim().length > 0; });

            if (lines.length > 0) {
                // Take first non-empty line/bullet point
                var summary = lines[0].trim();

                // If it's a bullet point, clean the bullet marker
                summary = summary.replace(/^[-•*]\\s*/, '');

                // Truncate if too long
                if (summary.length > 150) {
                    summary = summary.substring(0, 150) + '...';
                }

                return summary.trim();
            }

            // Fallback: just truncate the text
            if (clean.length > 150) {
                return clean.substring(0, 150) + '...';
            }

            return clean.trim();
        }
        
        function createCard(item, isTwitter) {
            var extra = isTwitter ? item.twitter_count - 1 : item.announcement_count - 1;
            var badge = extra > 0 ? '<span class="more-badge">+' + extra + '</span>' : '';

            var classBadgeHtml = '';
            if (!isTwitter && item.classification) {
                classBadgeHtml = '<div class="class-badge" style="background:' + item.classification.bg + ';color:' + item.classification.color + '">' +
                    '<span class="class-icon">' + item.classification.icon + '</span>' +
                    item.classification.name +
                '</div>';
            }

            var companyEncoded = encodeURIComponent(item.company);

            return '<div class="card ' + (isTwitter ? 'twitter' : '') + '" data-company="' + companyEncoded + '" style="cursor:pointer;">' +
                '<div class="card-top">' +
                    '<div class="avatar">' + getAvatar(item.company, isTwitter) + '</div>' +
                    '<div class="card-info">' +
                        '<div class="card-company">' + item.company + '</div>' +
                        '<div class="card-date">' + item.date + '</div>' +
                    '</div>' +
                    '<div class="card-right">' +
                        classBadgeHtml +
                        badge +
                    '</div>' +
                '</div>' +
                '<div class="card-summary">' + extractSummary(item.summary) + '</div>' +
                '<div class="card-footer">' +
                    '<span class="view-btn">View All <svg viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg></span>' +
                '</div>' +
            '</div>';
        }
        
        function loadData(reset) {
            if (reset) {
                annOffset = 0;
                twtOffset = 0;
                hasMoreAnn = true;
                hasMoreTwt = true;
                annCards.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';
                twtCards.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';
            }

            var url = '/api/latest-grouped';
            var params = [];
            if (dateFrom.value) params.push('from=' + dateFrom.value);
            if (dateTo.value) params.push('to=' + dateTo.value);
            params.push('offset=' + annOffset);
            params.push('limit=15');
            url += '?' + params.join('&');

            fetch(url).then(function(r) { return r.json(); }).then(function(data) {
                dateBadge.textContent = data.date || 'No data';

                // Handle announcements
                if (reset || annOffset === 0) {
                    if (data.announcements && data.announcements.length) {
                        annCards.innerHTML = data.announcements.map(function(i) { return createCard(i, false); }).join('');
                        document.getElementById('annCount').textContent = data.announcements.length;
                    } else {
                        annCards.innerHTML = '<div class="empty">No announcements</div>';
                        document.getElementById('annCount').textContent = 0;
                    }
                } else {
                    // Append to existing
                    if (data.announcements && data.announcements.length) {
                        var newCards = data.announcements.map(function(i) { return createCard(i, false); }).join('');
                        annCards.insertAdjacentHTML('beforeend', newCards);
                        var currentCount = parseInt(document.getElementById('annCount').textContent) || 0;
                        document.getElementById('annCount').textContent = currentCount + data.announcements.length;
                    }
                }

                // Handle twitter
                if (reset || twtOffset === 0) {
                    if (data.twitter && data.twitter.length) {
                        twtCards.innerHTML = data.twitter.map(function(i) { return createCard(i, true); }).join('');
                        document.getElementById('twtCount').textContent = data.twitter.length;
                    } else {
                        twtCards.innerHTML = '<div class="empty">No Twitter updates</div>';
                        document.getElementById('twtCount').textContent = 0;
                    }
                } else {
                    // Append to existing
                    if (data.twitter && data.twitter.length) {
                        var newCards = data.twitter.map(function(i) { return createCard(i, true); }).join('');
                        twtCards.insertAdjacentHTML('beforeend', newCards);
                        var currentCount = parseInt(document.getElementById('twtCount').textContent) || 0;
                        document.getElementById('twtCount').textContent = currentCount + data.twitter.length;
                    }
                }

                hasMoreAnn = data.has_more_announcements || false;
                hasMoreTwt = data.has_more_twitter || false;
                isLoadingAnn = false;
                isLoadingTwt = false;
            });
        }

        function loadMoreAnnouncements() {
            if (isLoadingAnn || !hasMoreAnn) return;
            isLoadingAnn = true;
            annOffset += 15;

            var url = '/api/latest-grouped';
            var params = [];
            if (dateFrom.value) params.push('from=' + dateFrom.value);
            if (dateTo.value) params.push('to=' + dateTo.value);
            params.push('offset=' + annOffset);
            params.push('limit=15');
            url += '?' + params.join('&');

            fetch(url).then(function(r) { return r.json(); }).then(function(data) {
                if (data.announcements && data.announcements.length) {
                    var newCards = data.announcements.map(function(i) { return createCard(i, false); }).join('');
                    annCards.insertAdjacentHTML('beforeend', newCards);
                    var currentCount = parseInt(document.getElementById('annCount').textContent) || 0;
                    document.getElementById('annCount').textContent = currentCount + data.announcements.length;
                }
                hasMoreAnn = data.has_more_announcements || false;
                isLoadingAnn = false;
            });
        }

        function loadMoreTwitter() {
            if (isLoadingTwt || !hasMoreTwt) return;
            isLoadingTwt = true;
            twtOffset += 15;

            var url = '/api/latest-grouped';
            var params = [];
            if (dateFrom.value) params.push('from=' + dateFrom.value);
            if (dateTo.value) params.push('to=' + dateTo.value);
            params.push('offset=' + twtOffset);
            params.push('limit=15');
            url += '?' + params.join('&');

            fetch(url).then(function(r) { return r.json(); }).then(function(data) {
                if (data.twitter && data.twitter.length) {
                    var newCards = data.twitter.map(function(i) { return createCard(i, true); }).join('');
                    twtCards.insertAdjacentHTML('beforeend', newCards);
                    var currentCount = parseInt(document.getElementById('twtCount').textContent) || 0;
                    document.getElementById('twtCount').textContent = currentCount + data.twitter.length;
                }
                hasMoreTwt = data.has_more_twitter || false;
                isLoadingTwt = false;
            });
        }

        // Infinite scroll listeners
        annCards.addEventListener('scroll', function() {
            var scrollTop = this.scrollTop;
            var scrollHeight = this.scrollHeight;
            var clientHeight = this.clientHeight;

            // Load more when 80% scrolled
            if ((scrollTop + clientHeight) >= scrollHeight * 0.8) {
                loadMoreAnnouncements();
            }
        });

        twtCards.addEventListener('scroll', function() {
            var scrollTop = this.scrollTop;
            var scrollHeight = this.scrollHeight;
            var clientHeight = this.clientHeight;

            // Load more when 80% scrolled
            if ((scrollTop + clientHeight) >= scrollHeight * 0.8) {
                loadMoreTwitter();
            }
        });

        loadData(true);

        // Handle card clicks using event delegation
        document.body.addEventListener('click', function(e) {
            var card = e.target.closest('.card, .result-card');
            if (card && card.hasAttribute('data-company')) {
                var company = card.getAttribute('data-company');
                window.location.href = '/share/' + company;
            }
        });

        dateFrom.addEventListener('change', function() { loadData(true); });
        dateTo.addEventListener('change', function() { loadData(true); });
        document.getElementById('clearBtn').addEventListener('click', function() {
            dateFrom.value = '';
            dateTo.value = '';
            loadData(true);
        });
        
        var debounce;
        searchInput.addEventListener('input', function() {
            clearTimeout(debounce);
            debounce = setTimeout(doSearch, 300);
        });
        document.getElementById('searchForm').addEventListener('submit', function(e) {
            e.preventDefault();
            doSearch();
        });
        
        function doSearch() {
            var q = searchInput.value.trim();
            if (!q) {
                latestSection.classList.remove('hidden');
                resultsSection.classList.remove('active');
                return;
            }
            
            latestSection.classList.add('hidden');
            resultsSection.classList.add('active');
            
            var url = '/api/search?q=' + encodeURIComponent(q);
            if (dateFrom.value) url += '&from=' + dateFrom.value;
            if (dateTo.value) url += '&to=' + dateTo.value;
            
            fetch(url).then(function(r) { return r.json(); }).then(function(data) {
                if (data.length) {
                    resultsList.innerHTML = data.map(function(i) {
                        return '<div class="result-card" data-company="' + encodeURIComponent(i.company) + '" style="cursor:pointer;">' +
                            '<div class="result-name">' + i.company + '</div>' +
                            '<div class="result-meta">' +
                                '<span>' + i.announcement_count + ' Announcements</span>' +
                                '<span>' + i.twitter_count + ' Twitter</span>' +
                                '<span>Latest: ' + i.latest_date + '</span>' +
                            '</div>' +
                        '</div>';
                    }).join('');
                } else {
                    resultsList.innerHTML = '<div class="empty">No results found for "' + q + '"</div>';
                }
            });
        }
    </script>
</body>
</html>
"""

DETAIL_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ company }}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #C45A35;
            --primary-light: #FEF3EE;
            --twitter: #1D9BF0;
            --twitter-light: #EEF6FF;
            --bg: #F8F9FA;
            --card-bg: #FFFFFF;
            --text-primary: #1A1A1A;
            --text-secondary: #555555;
            --text-muted: #888888;
            --border: #E8E8E8;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg);
            color: var(--text-primary);
            min-height: 100vh;
        }
        
        .top-bar {
            background: var(--card-bg);
            border-bottom: 1px solid var(--border);
            padding: 16px 24px;
            display: flex;
            align-items: center;
            gap: 16px;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .back-btn {
            padding: 8px 16px;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-primary);
            text-decoration: none;
            font-size: 0.85rem;
            font-weight: 500;
        }
        .back-btn:hover { border-color: var(--primary); }
        .page-title {
            font-size: 1.2rem;
            font-weight: 600;
        }
        
        .page-layout {
            max-width: 1200px;
            margin: 0 auto;
            padding: 24px;
            display: grid;
            grid-template-columns: 1fr 320px;
            gap: 24px;
        }
        
        .content-area { min-width: 0; overflow: hidden; }
        
        .sidebar {
            position: sticky;
            top: 80px;
            height: fit-content;
        }
        
        .calendar-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
        }
        .calendar-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px;
            border-bottom: 1px solid var(--border);
            background: #FAFAFA;
        }
        .calendar-title {
            font-size: 1rem;
            font-weight: 600;
        }
        .calendar-nav {
            display: flex;
            gap: 8px;
        }
        .calendar-nav button {
            width: 28px;
            height: 28px;
            border: 1px solid var(--border);
            background: var(--card-bg);
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
            color: var(--text-muted);
            transition: all 0.2s;
        }
        .calendar-nav button:hover {
            border-color: var(--primary);
            color: var(--primary);
        }
        
        .calendar-body { 
            padding: 12px; 
        }
        
        .calendar-weekdays {
            display: grid;
            grid-template-columns: repeat(7, minmax(32px, 1fr));
            margin-bottom: 4px;
        }
        .weekday {
            text-align: center;
            font-size: 0.65rem;
            font-weight: 600;
            color: var(--text-muted);
            padding: 4px 0;
            text-transform: uppercase;
        }
        
        .calendar-days {
            display: grid;
            grid-template-columns: repeat(7, minmax(32px, 1fr));
            grid-auto-rows: 32px;
            gap: 4px;
        }
        .calendar-day {
            height: 32px;
            min-width: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.75rem;
            border-radius: 6px;
            cursor: default;
            color: var(--text-secondary);
            background: transparent;
            transition: all 0.2s;
        }
        .calendar-day.empty { 
            visibility: hidden;
            height: 32px;
        }
        .calendar-day.today {
            font-weight: 700;
            border: 2px solid var(--primary);
        }
        .calendar-day.has-data {
            background: var(--primary-light);
            color: var(--primary);
            font-weight: 600;
            cursor: pointer;
        }
        .calendar-day.has-data:hover {
            background: var(--primary);
            color: white;
        }
        .calendar-day.has-twitter {
            background: var(--twitter-light);
            color: var(--twitter);
            cursor: pointer;
        }
        .calendar-day.has-twitter:hover {
            background: var(--twitter);
            color: white;
        }
        .calendar-day.has-both {
            background: linear-gradient(135deg, var(--primary-light) 50%, var(--twitter-light) 50%);
            cursor: pointer;
        }
        .calendar-day.has-both:hover {
            background: linear-gradient(135deg, var(--primary) 50%, var(--twitter) 50%);
            color: white;
        }
        .calendar-day.selected {
            background: var(--primary) !important;
            color: white !important;
            box-shadow: 0 2px 8px rgba(196, 90, 53, 0.4);
        }
        
        .calendar-legend {
            display: flex;
            justify-content: center;
            gap: 16px;
            padding: 12px;
            border-top: 1px solid var(--border);
            background: #FAFAFA;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.7rem;
            color: var(--text-muted);
        }
        .legend-dot {
            width: 10px;
            height: 10px;
            border-radius: 3px;
        }
        .legend-dot.ann { background: var(--primary-light); border: 1px solid var(--primary); }
        .legend-dot.twt { background: var(--twitter-light); border: 1px solid var(--twitter); }
        
        .stats-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        }
        .stats-title {
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--text-muted);
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .stats-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid var(--border);
        }
        .stats-row:last-child { border-bottom: none; }
        .stats-label { font-size: 0.85rem; color: var(--text-secondary); }
        .stats-value { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); }
        .stats-value.ann { color: var(--primary); }
        .stats-value.twt { color: var(--twitter); }
        
        /* Slide container */
        .slide-container {
            position: relative;
            overflow: hidden;
        }
        
        .slide-wrapper {
            transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease;
        }
        
        .slide-wrapper.slide-left {
            animation: slideLeft 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        .slide-wrapper.slide-right {
            animation: slideRight 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        @keyframes slideLeft {
            0% { transform: translateX(100%); opacity: 0; }
            100% { transform: translateX(0); opacity: 1; }
        }
        
        @keyframes slideRight {
            0% { transform: translateX(-100%); opacity: 0; }
            100% { transform: translateX(0); opacity: 1; }
        }
        
        .section {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            margin-bottom: 16px;
            overflow: hidden;
        }
        .section-header {
            padding: 16px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #FAFAFA;
            border-bottom: 1px solid transparent;
            cursor: pointer;
            transition: all 0.2s;
        }
        .section-header:hover {
            background: #F5F5F5;
        }
        .section-header.active {
            border-bottom-color: var(--border);
        }
        .section-title {
            font-size: 1rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .section-count {
            padding: 4px 10px;
            border-radius: 10px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .section-count.ann { background: var(--primary-light); color: var(--primary); }
        .section-count.twt { background: var(--twitter-light); color: var(--twitter); }
        
        .toggle {
            font-size: 1.2rem;
            color: var(--text-muted);
            transition: transform 0.3s;
        }
        .section-header.active .toggle {
            transform: rotate(180deg);
        }
        
        .section-content {
            display: none;
            max-height: 70vh;
            overflow-y: auto;
        }
        .section-content.active {
            display: block;
        }
        
        .item {
            padding: 20px;
            border-bottom: 1px solid #F0F0F0;
        }
        .item:last-child { border-bottom: none; }
        .item:hover { background: #FAFAFA; }
        .item-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 10px;
            gap: 12px;
        }
        .item-date { color: var(--primary); font-weight: 500; font-size: 0.85rem; }
        .item-classification {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            font-size: 0.75rem;
            font-weight: 500;
            padding: 4px 10px;
            border-radius: 14px;
            margin-left: 8px;
        }
        .item-class-icon { font-size: 0.85rem; }
        .item-type {
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            flex-shrink: 0;
        }
        .item-type.ann { background: var(--primary-light); color: var(--primary); }
        .item-type.twt { background: var(--twitter-light); color: var(--twitter); }
        .item-summary { 
            color: var(--text-secondary); 
            line-height: 1.7; 
            font-size: 0.92rem; 
            white-space: pre-line;
        }
        .item-summary strong {
            font-weight: 600;
            color: var(--text-primary);
        }
        .item-links { margin-top: 12px; display: flex; gap: 16px; flex-wrap: wrap; }
        .item-link { color: var(--primary); text-decoration: none; font-size: 0.85rem; font-weight: 500; }
        .item-link:hover { text-decoration: underline; }
        .item-channel { color: var(--text-muted); font-size: 0.85rem; margin-top: 8px; }
        .item-meta { 
            margin-top: 8px; 
            font-size: 0.75rem; 
            color: var(--text-muted);
            display: flex;
            gap: 16px;
        }
        
        .empty { 
            padding: 60px 40px; 
            text-align: center; 
            color: var(--text-muted);
        }
        .empty-icon {
            font-size: 3rem;
            margin-bottom: 16px;
            opacity: 0.5;
        }
        .empty-text {
            font-size: 1rem;
            margin-bottom: 8px;
        }
        .empty-hint {
            font-size: 0.85rem;
            color: var(--text-muted);
        }
        
        @media (max-width: 900px) {
            .page-layout {
                grid-template-columns: 1fr;
            }
            .sidebar {
                position: static;
                order: -1;
            }
        }
    </style>
</head>
<body>
    <header class="top-bar">
        <a href="/" class="back-btn">← Back</a>
        <h1 class="page-title">{{ company }}</h1>
    </header>
    
    <main class="page-layout">
        <div class="content-area">
            <!-- Slide container for announcements -->
            <div class="slide-container">
                <div class="slide-wrapper" id="slideWrapper">
                    <!-- Announcements Section -->
                    <div class="section" id="annSection">
                        <div class="section-header active" onclick="toggleSection('ann')">
                            <div class="section-title">
                                Announcements
                                <span class="section-count ann" id="annCount">0</span>
                            </div>
                            <span class="toggle">▾</span>
                        </div>
                        <div class="section-content active" id="annContent">
                            <div class="empty">
                                <div class="empty-icon">📄</div>
                                <div class="empty-text">Loading...</div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Twitter Section -->
                    <div class="section" id="twtSection">
                        <div class="section-header" onclick="toggleSection('twt')">
                            <div class="section-title">
                                Twitter Updates
                                <span class="section-count twt" id="twtCount">0</span>
                            </div>
                            <span class="toggle">▾</span>
                        </div>
                        <div class="section-content" id="twtContent">
                            <div class="empty">
                                <div class="empty-icon">🐦</div>
                                <div class="empty-text">No Twitter updates</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="sidebar">
            <div class="calendar-card">
                <div class="calendar-header">
                    <span class="calendar-title" id="calendarTitle">December 2025</span>
                    <div class="calendar-nav">
                        <button onclick="changeMonth(-1)">‹</button>
                        <button onclick="changeMonth(1)">›</button>
                    </div>
                </div>
                <div class="calendar-body">
                    <div class="calendar-weekdays">
                        <div class="weekday">Sun</div>
                        <div class="weekday">Mon</div>
                        <div class="weekday">Tue</div>
                        <div class="weekday">Wed</div>
                        <div class="weekday">Thu</div>
                        <div class="weekday">Fri</div>
                        <div class="weekday">Sat</div>
                    </div>
                    <div class="calendar-days" id="calendarDays"></div>
                </div>
                <div class="calendar-legend">
                    <div class="legend-item">
                        <div class="legend-dot ann"></div>
                        <span>Announcement</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-dot twt"></div>
                        <span>Twitter</span>
                    </div>
                </div>
            </div>
            
            <div class="stats-card">
                <div class="stats-title">Overall Summary</div>
                <div class="stats-row">
                    <span class="stats-label">Total Announcements</span>
                    <span class="stats-value ann" id="totalAnn">0</span>
                </div>
                <div class="stats-row">
                    <span class="stats-label">Total Twitter</span>
                    <span class="stats-value twt" id="totalTwt">0</span>
                </div>
                <div class="stats-row">
                    <span class="stats-label">Active Days</span>
                    <span class="stats-value" id="activeDays">0</span>
                </div>
            </div>
            
            <div class="stats-card">
                <div class="stats-title" id="breakdownTitle">Category Breakdown</div>
                <div id="categoryBreakdown"></div>
            </div>
        </div>
    </main>
    
    <script>
        var currentYear = 2025;
        var currentMonth = 11;
        var selectedDate = null;
        var previousDate = null;
        
        // Store all data by date
        var announcementsByDate = {};
        var twitterByDate = {};
        var allDates = [];
        
        // Parse data from backend
        {% for item in announcements %}
        {% if item.date and item.date != 'N/A' %}
        (function() {
            var dateKey = "{{ item.date[:10] }}";
            if (!announcementsByDate[dateKey]) announcementsByDate[dateKey] = [];
            announcementsByDate[dateKey].push({
                date: "{{ item.date }}",
                summary: {{ item.summary | tojson | safe }},
                source_link: "{{ item.source_link }}",
                received_time: "{{ item.received_time }}",
                pdf_size: "{{ item.pdf_size }}",
                classification: {
                    id: "{{ item.classification.id }}",
                    name: "{{ item.classification.name }}",
                    icon: "{{ item.classification.icon }}",
                    color: "{{ item.classification.color }}",
                    bg: "{{ item.classification.bg }}"
                }
            });
        })();
        {% endif %}
        {% endfor %}
        
        {% for item in twitter_posts %}
        {% if item.date and item.date != 'N/A' %}
        (function() {
            var dateKey = "{{ item.date[:10] }}";
            if (!twitterByDate[dateKey]) twitterByDate[dateKey] = [];
            twitterByDate[dateKey].push({
                date: "{{ item.date }}",
                summary: {{ item.summary | tojson | safe }},
                source_link: "{{ item.source_link }}",
                tweet_url: "{{ item.tweet_url }}",
                channel: "{{ item.channel }}"
            });
        })();
        {% endif %}
        {% endfor %}
        
        // Get all unique dates and sort descending
        var dateSet = {};
        for (var d in announcementsByDate) dateSet[d] = true;
        for (var d in twitterByDate) dateSet[d] = true;
        allDates = Object.keys(dateSet).sort().reverse();
        
        // Update stats
        var totalAnnouncements = {{ announcements|length }};
        var totalTwitter = {{ twitter_posts|length }};
        document.getElementById('totalAnn').textContent = totalAnnouncements;
        document.getElementById('totalTwt').textContent = totalTwitter;
        document.getElementById('activeDays').textContent = allDates.length;
        
        // Set initial date to latest
        if (allDates.length > 0) {
            selectedDate = allDates[0];
            var parts = selectedDate.split('-');
            currentYear = parseInt(parts[0]);
            currentMonth = parseInt(parts[1]) - 1;
        }
        
        function toggleSection(id) {
            var header = document.querySelector('#' + id + 'Section .section-header');
            var content = document.getElementById(id + 'Content');
            header.classList.toggle('active');
            content.classList.toggle('active');
        }
        
        function formatDateDisplay(dateStr) {
            var date = new Date(dateStr);
            var options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
            return date.toLocaleDateString('en-US', options);
        }
        
        function renderAnnouncements(dateStr, direction) {
            var wrapper = document.getElementById('slideWrapper');
            var annContent = document.getElementById('annContent');
            var twtContent = document.getElementById('twtContent');
            
            // Add slide animation
            if (direction) {
                wrapper.classList.remove('slide-left', 'slide-right');
                void wrapper.offsetWidth; // Trigger reflow
                wrapper.classList.add(direction === 'left' ? 'slide-left' : 'slide-right');
            }
            
            var announcements = announcementsByDate[dateStr] || [];
            var twitter = twitterByDate[dateStr] || [];
            
            // Update counts
            document.getElementById('annCount').textContent = announcements.length;
            document.getElementById('twtCount').textContent = twitter.length;
            
            // Render announcements
            if (announcements.length > 0) {
                var html = '';
                for (var i = 0; i < announcements.length; i++) {
                    var item = announcements[i];
                    html += '<div class="item">';
                    html += '<div class="item-header">';
                    html += '<div>';
                    html += '<span class="item-date">' + item.date + '</span>';
                    if (item.classification) {
                        html += '<span class="item-classification" style="background:' + item.classification.bg + ';color:' + item.classification.color + '">';
                        html += '<span class="item-class-icon">' + item.classification.icon + '</span>';
                        html += item.classification.name;
                        html += '</span>';
                    }
                    html += '</div>';
                    html += '<span class="item-type ann">Announcement</span>';
                    html += '</div>';
                    html += '<div class="item-summary">' + item.summary + '</div>';
                    if (item.received_time || item.pdf_size) {
                        html += '<div class="item-meta">';
                        if (item.received_time) html += '<span>Received: ' + item.received_time + '</span>';
                        if (item.pdf_size) html += '<span>PDF: ' + item.pdf_size + '</span>';
                        html += '</div>';
                    }
                    if (item.source_link) {
                        html += '<div class="item-links">';
                        html += '<a href="' + item.source_link + '" target="_blank" class="item-link">View PDF →</a>';
                        html += '</div>';
                    }
                    html += '</div>';
                }
                annContent.innerHTML = html;
            } else {
                annContent.innerHTML = '<div class="empty"><div class="empty-icon">📄</div><div class="empty-text">No announcements on this date</div><div class="empty-hint">Select another date from the calendar</div></div>';
            }
            
            // Render twitter
            if (twitter.length > 0) {
                var html = '';
                for (var i = 0; i < twitter.length; i++) {
                    var item = twitter[i];
                    html += '<div class="item">';
                    html += '<div class="item-header">';
                    html += '<span class="item-date">' + item.date + '</span>';
                    html += '<span class="item-type twt">Twitter</span>';
                    html += '</div>';
                    html += '<div class="item-summary">' + item.summary + '</div>';
                    if (item.channel) html += '<div class="item-channel">' + item.channel + '</div>';
                    html += '<div class="item-links">';
                    if (item.tweet_url) html += '<a href="' + item.tweet_url + '" target="_blank" class="item-link">View Tweet →</a>';
                    if (item.source_link) html += '<a href="' + item.source_link + '" target="_blank" class="item-link">Source →</a>';
                    html += '</div>';
                    html += '</div>';
                }
                twtContent.innerHTML = html;
            } else {
                twtContent.innerHTML = '<div class="empty"><div class="empty-icon">🐦</div><div class="empty-text">No Twitter updates on this date</div><div class="empty-hint">Select another date from the calendar</div></div>';
            }
            
            // Update breakdown for selected date
            updateCategoryBreakdown(dateStr);
        }
        
        function updateCategoryBreakdown(dateStr) {
            document.getElementById('breakdownTitle').textContent = formatDateDisplay(dateStr).split(',')[0] + "'s Breakdown";
            
            var announcements = announcementsByDate[dateStr] || [];
            var categoryCounts = {};
            
            for (var i = 0; i < announcements.length; i++) {
                var cat = announcements[i].classification;
                if (!categoryCounts[cat.id]) {
                    categoryCounts[cat.id] = { count: 0, name: cat.name, icon: cat.icon, color: cat.color };
                }
                categoryCounts[cat.id].count++;
            }
            
            var container = document.getElementById('categoryBreakdown');
            var sortedCats = Object.keys(categoryCounts).sort(function(a, b) {
                return categoryCounts[b].count - categoryCounts[a].count;
            });
            
            if (sortedCats.length === 0) {
                container.innerHTML = '<div class="stats-row"><span class="stats-label" style="color:#888;">No announcements</span></div>';
            } else {
                var html = '';
                for (var j = 0; j < sortedCats.length; j++) {
                    var cat = categoryCounts[sortedCats[j]];
                    html += '<div class="stats-row">';
                    html += '<span class="stats-label"><span style="margin-right:6px;">' + cat.icon + '</span>' + cat.name + '</span>';
                    html += '<span class="stats-value" style="color:' + cat.color + '">' + cat.count + '</span>';
                    html += '</div>';
                }
                container.innerHTML = html;
            }
        }
        
        function selectDate(dateStr) {
            if (dateStr === selectedDate) return;
            
            // Determine slide direction
            var direction = null;
            if (previousDate) {
                direction = dateStr > previousDate ? 'right' : 'left';
            } else if (selectedDate) {
                direction = dateStr > selectedDate ? 'right' : 'left';
            }
            
            previousDate = selectedDate;
            selectedDate = dateStr;
            
            // Update calendar selection
            var allCells = document.querySelectorAll('.calendar-day');
            for (var i = 0; i < allCells.length; i++) {
                allCells[i].classList.remove('selected');
                if (allCells[i].getAttribute('data-date') === dateStr) {
                    allCells[i].classList.add('selected');
                }
            }
            
            renderAnnouncements(dateStr, direction);
        }
        
        function renderCalendar() {
            var monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                             'July', 'August', 'September', 'October', 'November', 'December'];
            document.getElementById('calendarTitle').textContent = monthNames[currentMonth] + ' ' + currentYear;
            
            var firstDay = new Date(currentYear, currentMonth, 1).getDay();
            var daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
            var today = new Date();
            
            var container = document.getElementById('calendarDays');
            container.innerHTML = '';
            
            // Empty cells
            for (var i = 0; i < firstDay; i++) {
                var empty = document.createElement('div');
                empty.className = 'calendar-day empty';
                container.appendChild(empty);
            }
            
            // Day cells
            for (var day = 1; day <= daysInMonth; day++) {
                var mm = (currentMonth + 1).toString();
                if (mm.length === 1) mm = '0' + mm;
                var dd = day.toString();
                if (dd.length === 1) dd = '0' + dd;
                var dateStr = currentYear + '-' + mm + '-' + dd;
                
                var hasAnn = announcementsByDate[dateStr] ? announcementsByDate[dateStr].length : 0;
                var hasTwt = twitterByDate[dateStr] ? twitterByDate[dateStr].length : 0;
                
                var cell = document.createElement('div');
                cell.className = 'calendar-day';
                cell.textContent = day;
                
                if (hasAnn > 0 && hasTwt > 0) {
                    cell.className += ' has-both';
                } else if (hasAnn > 0) {
                    cell.className += ' has-data';
                } else if (hasTwt > 0) {
                    cell.className += ' has-twitter';
                }
                
                if (dateStr === selectedDate) {
                    cell.className += ' selected';
                }
                
                if (day === today.getDate() && currentMonth === today.getMonth() && currentYear === today.getFullYear()) {
                    cell.className += ' today';
                }
                
                if (hasAnn > 0 || hasTwt > 0) {
                    cell.setAttribute('data-date', dateStr);
                    cell.onclick = function() {
                        var d = this.getAttribute('data-date');
                        selectDate(d);
                    };
                }
                
                container.appendChild(cell);
            }
        }
        
        function changeMonth(delta) {
            currentMonth = currentMonth + delta;
            if (currentMonth > 11) {
                currentMonth = 0;
                currentYear = currentYear + 1;
            } else if (currentMonth < 0) {
                currentMonth = 11;
                currentYear = currentYear - 1;
            }
            renderCalendar();
        }
        
        // Initialize
        renderCalendar();
        if (selectedDate) {
            renderAnnouncements(selectedDate, null);
        } else {
            document.getElementById('annContent').innerHTML = '<div class="empty"><div class="empty-icon">📄</div><div class="empty-text">No announcements found</div></div>';
            document.getElementById('twtContent').innerHTML = '<div class="empty"><div class="empty-icon">🐦</div><div class="empty-text">No Twitter updates found</div></div>';
        }
    </script>
</body>
</html>
"""

# ============== ROUTES ==============

@app.route('/')
def home():
    return render_template_string(SEARCH_PAGE)

# Logo functionality disabled - no logo folder available
# @app.route('/logos/<path:filename>')
# def serve_logo(filename):
#     logo_path = Path(LOGO_FOLDER)
#     if logo_path.exists():
#         return send_from_directory(LOGO_FOLDER, filename)
#     return '', 404

@app.route('/api/logos')
def get_logos():
    # Returns empty dict - logo functionality disabled
    return jsonify({})

@app.route('/api/stats')
def get_stats():
    df = get_data()
    if df.empty:
        return jsonify({'total_companies': 0, 'total_records': 0})
    return jsonify({
        'total_companies': df['COMPANY'].nunique() if 'COMPANY' in df.columns else 0,
        'total_records': len(df)
    })

@app.route('/api/refresh')
def refresh():
    df = cache.refresh()
    return jsonify({
        'status': 'refreshed',
        'records': len(df),
        'companies': df['COMPANY'].nunique() if not df.empty else 0
    })

@app.route('/api/latest-grouped')
def get_latest_grouped():
    df = get_data()
    if df.empty:
        return jsonify({'date': 'No data', 'announcements': [], 'twitter': [], 'has_more_announcements': False, 'has_more_twitter': False})

    date_from = request.args.get('from', '')
    date_to = request.args.get('to', '')
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 15))

    # Clean DATES column - filter out invalid values
    if 'DATES' in df.columns:
        # Convert to string and identify valid dates (YYYY-MM-DD format)
        df['DATES'] = df['DATES'].astype(str)
        # Valid dates start with a year (4 digits)
        valid_date_mask = df['DATES'].str.match(r'^\d{4}-\d{2}-\d{2}', na=False)
    else:
        valid_date_mask = pd.Series([False] * len(df))

    if date_from or date_to:
        # Filter by date range, only on valid dates
        filtered = df[valid_date_mask].copy()
        if date_from: filtered = filtered[filtered['DATES'] >= date_from]
        if date_to: filtered = filtered[filtered['DATES'] <= date_to]
        date_label = f"{date_from or 'Start'} → {date_to or 'Now'}"

        ann_df = filtered[filtered['COMPANY TYPE'].str.lower() == 'announcement'] if 'COMPANY TYPE' in filtered.columns else filtered
        twt_df = filtered[filtered['COMPANY TYPE'].str.lower() == 'twitter'] if 'COMPANY TYPE' in filtered.columns else pd.DataFrame()
    else:
        # NO DATE FILTER: Get latest data independently for announcements and Twitter
        # Split FIRST, then get latest data from each
        all_ann = df[df['COMPANY TYPE'].str.lower() == 'announcement'] if 'COMPANY TYPE' in df.columns else df
        all_twt = df[df['COMPANY TYPE'].str.lower() == 'twitter'] if 'COMPANY TYPE' in df.columns else pd.DataFrame()

        # Get latest announcement data
        if not all_ann.empty:
            ann_valid_mask = all_ann['DATES'].str.match(r'^\d{4}-\d{2}-\d{2}', na=False)
            ann_valid = all_ann[ann_valid_mask]
            if not ann_valid.empty:
                latest_ann_date = ann_valid['DATES'].max()
                ann_df = all_ann[all_ann['DATES'] == latest_ann_date]
            else:
                ann_df = pd.DataFrame()
        else:
            ann_df = pd.DataFrame()

        # Get latest Twitter data independently
        if not all_twt.empty:
            twt_valid_mask = all_twt['DATES'].str.match(r'^\d{4}-\d{2}-\d{2}', na=False)
            twt_valid = all_twt[twt_valid_mask]
            if not twt_valid.empty:
                latest_twt_date = twt_valid['DATES'].max()
                twt_df = all_twt[all_twt['DATES'] == latest_twt_date]
            else:
                twt_df = pd.DataFrame()
        else:
            twt_df = pd.DataFrame()

        # Set date label to latest overall date
        valid_dates_df = df[valid_date_mask]
        if not valid_dates_df.empty:
            date_label = str(valid_dates_df['DATES'].max())
        else:
            date_label = 'Unknown'

    if ann_df.empty and twt_df.empty:
        return jsonify({'date': date_label, 'announcements': [], 'twitter': [], 'has_more_announcements': False, 'has_more_twitter': False})

    def group_by_company(source_df, other_df, is_twitter=False, offset=0, limit=15):
        result = []
        seen = set()
        # Sort by dates, putting NA values at the end
        if 'DATES' in source_df.columns:
            sorted_df = source_df.sort_values('DATES', ascending=False, na_position='last')
        else:
            sorted_df = source_df

        idx = 0
        for _, row in sorted_df.iterrows():
            company = row.get('COMPANY', 'Unknown')
            if company in seen: continue
            seen.add(company)

            # Skip until we reach offset
            if idx < offset:
                idx += 1
                continue

            # Stop if we've reached the limit
            if len(result) >= limit:
                break

            summary = str(row.get('SUMMARY', ''))
            if summary.startswith('**'):
                lines = summary.split('\n')
                for line in lines:
                    if line.strip() and not line.startswith('**Announcement'):
                        summary = line.replace('**', '').strip()
                        break

            if len(summary) > 150:
                summary = summary[:150] + '...'

            category = str(row.get('CATEGORY', ''))[:100] if pd.notna(row.get('CATEGORY')) else ''

            # Get classification
            subject = str(row.get('CATEGORY', '')) if pd.notna(row.get('CATEGORY')) else ''
            class_id = classify_announcement(subject)
            class_info = get_classification_info(class_id)

            result.append({
                'company': company,
                'date': str(row.get('DATES', 'N/A')),
                'summary': summary,
                'category': category,
                'classification': {
                    'id': class_id,
                    'name': class_info['name'],
                    'icon': class_info['icon'],
                    'color': class_info['color'],
                    'bg': class_info['bg']
                } if not is_twitter else None,
                'announcement_count': len(source_df[source_df['COMPANY'] == company]) if not is_twitter else (len(other_df[other_df['COMPANY'] == company]) if not other_df.empty else 0),
                'twitter_count': len(source_df[source_df['COMPANY'] == company]) if is_twitter else (len(other_df[other_df['COMPANY'] == company]) if not other_df.empty else 0)
            })
            idx += 1

        # Check if there's more data
        total_companies = source_df['COMPANY'].nunique() if 'COMPANY' in source_df.columns else 0
        has_more = (offset + len(result)) < total_companies

        return result, has_more

    ann_results, has_more_ann = group_by_company(ann_df, twt_df, False, offset, limit) if not ann_df.empty else ([], False)
    twt_results, has_more_twt = group_by_company(twt_df, ann_df, True, offset, limit) if not twt_df.empty else ([], False)

    return jsonify({
        'date': date_label,
        'announcements': ann_results,
        'twitter': twt_results,
        'has_more_announcements': has_more_ann,
        'has_more_twitter': has_more_twt
    })

@app.route('/api/search')
def search():
    q = request.args.get('q', '').strip().lower()
    if not q: return jsonify([])
    
    df = get_data()
    if df.empty: return jsonify([])
    
    filtered = df[df['COMPANY'].str.lower().str.contains(q, na=False)].copy()
    
    # Convert DATES to string for comparison
    if 'DATES' in filtered.columns:
        filtered['DATES'] = filtered['DATES'].astype(str)
        # Valid dates match YYYY-MM-DD pattern
        valid_date_mask = filtered['DATES'].str.match(r'^\d{4}-\d{2}-\d{2}', na=False)
    else:
        valid_date_mask = pd.Series([False] * len(filtered))
    
    date_from = request.args.get('from', '')
    date_to = request.args.get('to', '')
    if date_from: 
        filtered = filtered[valid_date_mask & (filtered['DATES'] >= date_from)]
    if date_to: 
        filtered = filtered[valid_date_mask & (filtered['DATES'] <= date_to)]
    
    if filtered.empty: return jsonify([])
    
    results = []
    for company in filtered['COMPANY'].unique():
        cd = filtered[filtered['COMPANY'] == company]
        # Get latest date safely - only valid YYYY-MM-DD dates
        try:
            valid_dates = cd[cd['DATES'].str.match(r'^\d{4}-\d{2}-\d{2}', na=False)]['DATES']
            latest = str(valid_dates.max()) if not valid_dates.empty else 'N/A'
            if not latest or latest == 'nan' or len(latest) < 10:
                latest = 'N/A'
        except:
            latest = 'N/A'
        
        results.append({
            'company': company,
            'announcement_count': len(cd[cd['COMPANY TYPE'].str.lower() == 'announcement']) if 'COMPANY TYPE' in cd.columns else 0,
            'twitter_count': len(cd[cd['COMPANY TYPE'].str.lower() == 'twitter']) if 'COMPANY TYPE' in cd.columns else 0,
            'latest_date': latest
        })
    
    results.sort(key=lambda x: (0 if x['company'].lower() == q else 1, -(x['announcement_count'] + x['twitter_count'])))
    return jsonify(results[:20])

@app.route('/share/<company>')
def detail(company):
    df = get_data()
    if df.empty:
        return render_template_string(DETAIL_PAGE, company=company, first_announcement=None, announcements=[], twitter_posts=[])
    
    cd = df[df['COMPANY'].str.lower() == company.lower()]
    if cd.empty:
        cd = df[df['COMPANY'].str.lower().str.contains(company.lower(), na=False)]
    
    actual = cd['COMPANY'].iloc[0] if not cd.empty else company
    
    announcements, twitter_posts = [], []
    for _, row in cd.iterrows():
        summary_text = str(row.get('SUMMARY', ''))
        summary_html = convert_bold(summary_text)
        
        subject = str(row.get('CATEGORY', '')) if pd.notna(row.get('CATEGORY')) else ''
        class_id = classify_announcement(subject)
        class_info = get_classification_info(class_id)
        
        item = {
            'date': str(row.get('DATES', 'N/A')),
            'summary': summary_html,
            'source_link': str(row.get('SOURCE_LINK', '')) if pd.notna(row.get('SOURCE_LINK')) else '',
            'tweet_url': str(row.get('TWEET_URL', '')) if pd.notna(row.get('TWEET_URL')) else '',
            'channel': str(row.get('CHANNEL_NAME', '')) if pd.notna(row.get('CHANNEL_NAME')) else '',
            'category': str(row.get('CATEGORY', '')) if pd.notna(row.get('CATEGORY')) else '',
            'received_time': str(row.get('RECEIVED_TIME', '')) if pd.notna(row.get('RECEIVED_TIME')) else '',
            'pdf_size': str(row.get('PDF_SIZE', '')) if pd.notna(row.get('PDF_SIZE')) else '',
            'classification': {
                'id': class_id,
                'name': class_info['name'],
                'icon': class_info['icon'],
                'color': class_info['color'],
                'bg': class_info['bg']
            }
        }
        if str(row.get('COMPANY TYPE', '')).lower() == 'twitter':
            twitter_posts.append(item)
        else:
            announcements.append(item)
    
    announcements.sort(key=lambda x: x['date'], reverse=True)
    twitter_posts.sort(key=lambda x: x['date'], reverse=True)
    
    return render_template_string(DETAIL_PAGE, 
        company=actual, 
        first_announcement=announcements[0] if announcements else None,
        announcements=announcements, 
        twitter_posts=twitter_posts)

if __name__ == '__main__':
    print("\n" + "="*50)
    print("Stock Announcements Dashboard")
    print("="*50)
    print(f"Data: {DATA_FOLDER}")
    # print(f"Logos: {LOGO_FOLDER}")  # Logo functionality disabled
    print("\nServer: http://localhost:9000")
    print("="*50 + "\n")
    
    df = cache.refresh()
    print(f"Loaded {len(df)} records") if not df.empty else print("No data found!")
    
    app.run(host='0.0.0.0', port=9000, debug=False)
