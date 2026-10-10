# -*- coding: utf-8 -*-
"""QQ 邮箱 IMAP：隐藏文件夹探测 + 全量邮件头拉取（只读）"""
import imaplib
import json
import re
import sys
import base64
import email
import email.header

USER, CODE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]

M = imaplib.IMAP4_SSL('imap.qq.com', 993)
M.login(USER, CODE)

out = {'hidden_probe': {}, 'folders': {}, 'boundary_tests': {}, 'select_info': {}}


def to_str(x):
    return x.decode('ascii', 'replace') if isinstance(x, bytes) else str(x)


def enc_mutf7(s):
    res = []
    buf = []

    def flush():
        if buf:
            b = ''.join(buf).encode('utf-16-be')
            res.append('&' + base64.b64encode(b).decode('ascii').rstrip('=').replace('/', ',') + '-')
            buf.clear()

    for ch in s:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            res.append('&-' if ch == '&' else ch)
        else:
            buf.append(ch)
    flush()
    return ''.join(res)


def dec_mutf7(s):
    res = []
    i = 0
    while i < len(s):
        if s[i] == '&':
            j = s.find('-', i)
            if j == -1:
                res.append(s[i:])
                break
            if j == i + 1:
                res.append('&')
            else:
                b = s[i + 1:j].replace(',', '/')
                b += '=' * ((4 - len(b) % 4) % 4)
                try:
                    res.append(base64.b64decode(b).decode('utf-16-be'))
                except Exception:
                    res.append(s[i:j + 1])
            i = j + 1
        else:
            res.append(s[i])
            i += 1
    return ''.join(res)


def dec_hdr(s):
    if s is None:
        return ''
    try:
        parts = email.header.decode_header(s)
    except Exception:
        return str(s)
    buf = []
    for b, cs in parts:
        if isinstance(b, bytes):
            for enc in (cs, 'utf-8', 'gb18030', 'big5', 'latin-1'):
                if not enc:
                    continue
                try:
                    buf.append(b.decode(enc))
                    break
                except Exception:
                    continue
            else:
                buf.append(b.decode('utf-8', 'replace'))
        else:
            buf.append(b)
    return ' '.join(''.join(buf).split())


def sel(name):
    typ, cnt = M.select(name, readonly=True)
    info = {}
    for k in ('EXISTS', 'RECENT', 'UIDNEXT', 'UIDVALIDITY'):
        v = M.untagged_responses.get(k)
        if v:
            info[k] = to_str(v[-1])
    info['resp'] = typ
    info['count'] = to_str(cnt[0]) if cnt and cnt[0] else '0'
    out['select_info'][name] = info
    return typ


def fetch(uids):
    rows = []
    strs = [to_str(u) for u in uids]
    for i in range(0, len(strs), 15):
        chunk = strs[i:i + 15]
        typ, data = M.uid('fetch', ','.join(chunk), '(BODY.PEEK[HEADER.FIELDS (DATE FROM SUBJECT TO)])')
        if not data:
            continue
        for d in data:
            if isinstance(d, tuple) and len(d) >= 2:
                meta = to_str(d[0])
                mm = re.search(r'\(UID (\d+)', meta)
                msg = email.message_from_bytes(d[1])
                rows.append({
                    'uid': mm.group(1) if mm else '?',
                    'date': dec_hdr(msg.get('Date')),
                    'from': dec_hdr(msg.get('From')),
                    'subject': dec_hdr(msg.get('Subject')),
                    'to': dec_hdr(msg.get('To')),
                })
    return rows


# ---- 1. 隐藏文件夹探测 ----
candidates = ['广告邮件', '订阅邮件', '垃圾邮件', '已发送', '草稿箱', '已删除', '回收站',
              '其他文件夹/广告邮件', '其他文件夹/订阅邮件', 'INBOX.广告邮件',
              'Junk/广告邮件', '&Xn9USpCuTvY-', '&i6KWBZCuTvY-']
for c in candidates:
    attempts = {}
    for label, name in (('raw', c), ('mutf7', enc_mutf7(c))):
        nm = name if (' ' not in name and all(ord(ch) < 128 for ch in name)) else '"%s"' % name
        try:
            typ, cnt = M.select(nm, readonly=True)
            n = to_str(cnt[0]) if cnt and cnt[0] else '?'
            attempts[label] = '%s/%s' % (typ, n)
            if typ == 'OK':
                out['hidden_probe'].setdefault(c, {})['FOUND_' + label] = nm
        except Exception as e:
            attempts[label] = 'ERR %s' % type(e).__name__
    out['hidden_probe'][c] = attempts

# ---- 2. 全部文件夹拉取 ----
FOLDERS = {
    'INBOX': 'INBOX',
    'Junk': 'Junk',
    'Drafts': 'Drafts',
    'Sent Messages': '"Sent Messages"',
    'Deleted Messages': '"Deleted Messages"',
}

for label, imapname in FOLDERS.items():
    item = {}
    try:
        sel(imapname)
        typ, u = M.uid('search', None, 'UNSEEN')
        unseen = u[0].split() if u and u[0] else []
        typ, s = M.uid('search', None, 'SEEN')
        seen = s[0].split() if s and s[0] else []
        item['unseen_count'] = len(unseen)
        item['seen_count'] = len(seen)
        item['unseen'] = fetch(sorted(unseen, key=lambda x: int(to_str(x))))
        item['seen'] = fetch(sorted(seen, key=lambda x: int(to_str(x))))
    except Exception as e:
        item['error'] = '%s: %s' % (type(e).__name__, e)
    out['folders'][label] = item
    print('  %s -> unseen=%s seen=%s' % (label, item.get('unseen_count'), item.get('seen_count')))

# ---- 3. 边界测试 ----
sel('INBOX')


def cnt(crit):
    try:
        typ, d = M.uid('search', None, crit)
        return len(d[0].split()) if d and d[0] else 0
    except Exception as e:
        return 'ERR ' + type(e).__name__


for crit in ['ALL', 'UNSEEN', 'SINCE 01-Jan-2026', 'SINCE 01-Sep-2026',
             'BEFORE 30-Aug-2026', 'BEFORE 01-Sep-2026', 'SINCE 01-Jan-2025 BEFORE 31-Dec-2025']:
    out['boundary_tests'][crit] = cnt(crit)

M.logout()
with open(OUT, 'w', encoding='utf-8') as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print('DONE')
