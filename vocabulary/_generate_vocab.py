import os
import re
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.parse
import time

# Configuration
VOCAB_DIR = os.path.dirname(os.path.abspath(__file__))
RAWDATA_DIR = os.path.join(VOCAB_DIR, 'rawdata')
MAX_WORKERS = 5  # Reduced workers to avoid being blocked
TIMEOUT = 10

def get_word_info(word):
    """
    Fetches word information from Youdao Dictionary.
    Returns a dictionary with word, ipa, audio, definition, and usage.
    """
    word = word.strip()
    if not word:
        return None
        
    url = f"http://dict.youdao.com/w/{urllib.parse.quote(word)}"
    try:
        # User-Agent to avoid simple blocking
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
        }
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"Failed to fetch {word}: Status {r.status_code}")
            return None
            
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # 1. Phonetic (IPA)
        # Youdao usually has <span class="phonetic">...</span>. 
        # Sometimes there are two (UK/US). We'll take the first one or specifically US if labeled.
        phonetics = soup.select('span.phonetic')
        ipa = phonetics[0].text if phonetics else ""
        
        # 2. Audio
        # Youdao audio API: type=1 (UK), type=2 (US)
        audio_url = f"https://dict.youdao.com/dictvoice?audio={word}&type=2"
        
        # 3. Definition (Chinese)
        # Usually in <div class="trans-container"> <ul> <li>...</li> </ul> </div>
        trans_container = soup.find('div', class_='trans-container')
        definitions = []
        if trans_container:
            ul = trans_container.find('ul')
            if ul:
                for li in ul.find_all('li'):
                    text = li.get_text(strip=True)
                    if text:
                        definitions.append(text)
        
        # Take top 3 definitions to keep it clean
        definition_str = "<br>".join(definitions[:3])
        
        # 4. Common Usage / Phrases
        # Usually in <div id="wordGroup"> or <div id="webPhrase">
        # We prefer "wordGroup" (Phrase/Collocations) over "webPhrase" (Network definitions)
        phrases = []
        word_group = soup.find('div', id='wordGroup')
        if word_group:
            for p in word_group.find_all('p', class_='wordGroup'):
                # Extract text, usually "phrase: translation"
                # Need to be careful with formatting. 
                # Structure: <p class="wordGroup"> <a ...>phrase</a> translation </p> (varies)
                text = p.get_text(" ", strip=True)
                phrases.append(text)
        
        # Fallback to examples if no word group? 
        # For now, just usage.
        usage_str = "<br>".join(phrases[:3])
        
        return {
            'word': word,
            'ipa': ipa,
            'audio': audio_url,
            'definition': definition_str,
            'usage': usage_str
        }
        
    except Exception as e:
        print(f"Error processing {word}: {e}")
        return None

def process_md_file(md_path):
    print(f"Reading {md_path}...")
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if not lines:
        print(f"Skipping empty file: {md_path}")
        return

    first_line = lines[0].strip()
    
    # Check if first line points to rawdata
    # Expected format: > rawdata/filename or similar
    if 'rawdata/' not in first_line:
        print(f"Skipping {md_path}: First line does not contain 'rawdata/'")
        return

    # Extract filename. Assuming "rawdata/filename.txt" is present
    match = re.search(r'rawdata/([^/\s]+)', first_line)
    if not match:
        print(f"Could not parse filename from header: {first_line}")
        return
        
    raw_filename = match.group(1)
    
    # Handle potential filename mismatches (e.g. _txt.txt vs .txt)
    # Try exact match first
    raw_path = os.path.join(RAWDATA_DIR, raw_filename)
    
    if not os.path.exists(raw_path):
        # Try finding a similar file
        print(f"Raw file {raw_filename} not found. Searching for close matches...")
        possible_files = os.listdir(RAWDATA_DIR)
        # Simple heuristic: remove extension and _txt suffix and compare
        base_name = raw_filename.replace('_txt.txt', '').replace('.txt', '')
        found = False
        for f in possible_files:
            if base_name in f:
                raw_path = os.path.join(RAWDATA_DIR, f)
                print(f"Found match: {f}")
                found = True
                break
        if not found:
            print(f"Error: Could not find rawdata file for {md_path}")
            return

    print(f"Using raw data source: {raw_path}")
    
    # Read words
    with open(raw_path, 'r', encoding='utf-8') as f:
        words = [line.strip() for line in f if line.strip()]
    
    print(f"Found {len(words)} words. Fetching details... (This may take time)")
    
    # Process words in parallel
    table_rows = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_word = {executor.submit(get_word_info, word): word for word in words}
        
        # We want to maintain order, but futures complete in any order.
        # So we store results in a dict and reconstruct list later.
        results = {}
        completed = 0
        total = len(words)
        
        for future in as_completed(future_to_word):
            word = future_to_word[future]
            data = future.result()
            results[word] = data
            completed += 1
            if completed % 10 == 0:
                print(f"Progress: {completed}/{total}", end='\r')
    
    print(f"\nFinished fetching data for {md_path}")

    # Build Markdown Table
    # Header
    md_lines = [lines[0].strip(), "", "| 单词 | 音标 | 中文释义 | 常见搭配/用法 |", "|---|---|---|---|"]
    
    for word in words:
        info = results.get(word)
        if info:
            # Use a span with a class for audio playback instead of a direct link
            # The click event is handled by a global listener in index.html
            ipa_link = f"{info['ipa']} <span class='play-audio-btn' data-url='{info['audio']}' style='cursor:pointer'>🔊</span>" if info['ipa'] else ""
            row = f"| {info['word']} | {ipa_link} | {info['definition']} | {info['usage']} |"
            md_lines.append(row)
        else:
            # Fallback for failed words
            md_lines.append(f"| {word} | - | - | - |")
            
    # Write back to file
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(md_lines))
    
    print(f"Successfully updated {md_path}")

def main():
    if not os.path.exists(RAWDATA_DIR):
        print(f"Error: Rawdata directory not found at {RAWDATA_DIR}")
        return

    # Find all .md files in VOCAB_DIR
    for filename in os.listdir(VOCAB_DIR):
        if filename.endswith('.md') and filename != 'README.md':
            file_path = os.path.join(VOCAB_DIR, filename)
            process_md_file(file_path)

if __name__ == "__main__":
    # Check for dependencies
    try:
        import requests
        import bs4
    except ImportError:
        print("Missing dependencies. Please run: pip install requests beautifulsoup4")
        exit(1)
        
    main()

