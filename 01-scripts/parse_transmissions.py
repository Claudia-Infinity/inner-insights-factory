#!/usr/bin/env python3
"""Parse a Transmissions .docx (Claudia's format) into JSON.
Usage: parse_transmissions.py <file.docx> <setname> <out.json>
Header lines look like: MM-DD-YY TRANSMISSION: Title   (colon optional, case-insensitive)
"""
import sys, re, json, zipfile, html
def docx_text(path):
    x = zipfile.ZipFile(path).read('word/document.xml').decode()
    x = re.sub(r'</w:p>', '\n', x); x = re.sub(r'<w:tab/>', '\t', x)
    return html.unescape(re.sub(r'<[^>]+>', '', x))
HDR = re.compile(r'^\s*(\d{2})-(\d{2})-(\d{2})\s+TRANSMISSION\s*:?\s*(.+?)\s*$', re.I)
def parse(text, setname):
    items, cur = [], None
    for l in text.split('\n'):
        m = HDR.match(l)
        if m:
            if cur: items.append(cur)
            mm, dd, yy, title = m.groups()
            cur = {'set': setname, 'date': f'20{yy}-{mm}-{dd}', 'title': title.strip(), 'lines': []}
        elif cur is not None:
            s = l.strip()
            if s and not set(s) <= set('✦ '): cur['lines'].append(s)
    if cur: items.append(cur)
    for it in items:
        it['body'] = '\n'.join(it.pop('lines')); it['words'] = len(it['body'].split())
    return items
if __name__ == '__main__':
    src, setname, out = sys.argv[1:4]
    items = parse(docx_text(src), setname)
    json.dump(items, open(out, 'w'), indent=1, ensure_ascii=False)
    dates = [i['date'] for i in items]
    print(f'{setname}: {len(items)} items {dates[0]} -> {dates[-1]}; dupes={[d for d in set(dates) if dates.count(d)>1]}')
