import json
import re

with open('response.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Find __NEXT_DATA__
pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
match = re.search(pattern, html, re.DOTALL)
if match:
    data = json.loads(match.group(1))
    props = data.get('props', {}).get('pageProps', {}).get('data', {})
    
    print('Keys in data:', list(props.keys()))
    
    # Check for lists
    recommend_txt = props.get('recommendTxt', [])
    recommend_img = props.get('recommendImg', [])
    
    print(f'Found {len(recommend_txt)} recommendTxt sections')
    print(f'Found {len(recommend_img)} recommendImg items')
    
    if recommend_img:
        print('Sample recommend_img item keys:', list(recommend_img[0].keys())[:10])
        print('First item name:', recommend_img[0].get('name'))
        print('First item link:', recommend_img[0].get('link'))
        
    # Flatten recommendTxt
    all_txt = []
    for section in recommend_txt:
        if isinstance(section, list):
            all_txt.extend(section)
    
    print(f'Total text items found: {len(all_txt)}')
    if all_txt:
        print('Sample text item keys:', list(all_txt[0].keys())[:10])
        print('First text item name:', all_txt[0].get('name'))
        print('First text item link:', all_txt[0].get('link'))
else:
    print('__NEXT_DATA__ not found')

