# -*- coding: utf-8 -*-
"""QQ 邮箱全维度核查：POP3 探测 + IMAP 全文件夹全状态拉取（只读）"""
import imaplib
import poplib
import json
import re
import sys
import base64
import email
import email.header

USER, CODE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
res = {'pop3': {}, 'imap': {}, 'select_info': {}}


def to_str(x):
    return x.decode('ascii', 'replace') if isinstance(x, bytes) else str(x)


# ================= POP3 探测（看能否突破 30 天窗口）=================
try:
    P = poplib.POP3_SSL('pop.qq.com', 995, timeout=25)
    P.user(USER)
    P.pass_(CODE)
    cnt, size = P.stat()
    listing = P.list()[1]
    res['pop3'] = {
        'status': 'OK',
        'count': cnt,
        'size_bytes': size,
        'list_lines': len(listing),
        'sample': [to_str(x) for x in listing[:3]],
    }
    # 取最早一封的头部（TOP n 0 不下载正文、不改变已读状态）
    try:
        resp, lines, octets = P.top(1, 0)
        hdr = b'\n'.join(lines).decode('utf-8', 'replace')
        res['pop3']['oldest_1_header'] = hdr[:1200]
    except Exception as e:
        res['pop3']['oldest_1_header'] = 'ERR %s' % e
    try:
        resp, lines, octets = P.top(cnt, 0)
        hdr = b'\n'.join(lines).decode('utf-8', 'replace')
        res['pop3']['newest_1_header'] = hdr[:1200]
    except Exception as e:
        res['pop3']['newest_1_header'] = 'ERR %s' % e
    P.quit()
except Exception as e:
    res['pop3'] = {'status': 'ERR', 'msg': '%s: %s' % (type(e).__name__, e)}

# ================= IMAP 全量拉取 =================
M = imaplib.IMAP4_SSL('imap.qq.com', 993)
M.login(USER, CODE)


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
    res['select_info'][name] = info
    return typ


def fetch_all(uids):
    rows = []
    strs = [to_str(u) for u in uids]
    for i in range(0, len(strs), 15):
        chunk = strs[i:i + 15]
        typ, data = M.uid(
            'fetch', ','.join(chunk),
            '(UID RFC822.SIZE BODY.PEEK[HEADER.FIELDS (DATE FROM SUBJECT TO CC)])')
        if not data:
            continue
        for d in data:
            if isinstance(d, tuple) and len(d) >= 2:
                meta = to_str(d[0])
                mu = re.search(r'UID (\d+)', meta)
                ms = re.search(r'RFC822\.SIZE (\d+)', meta)
                msg = email.message_from_bytes(d[1])
                rows.append({
                    'uid': mu.group(1) if mu else '?',
                    'size': int(ms.group(1)) if ms else 0,
                    'date': dec_hdr(msg.get('Date')),
                    'from': dec_hdr(msg.get('From')),
                    'to': dec_hdr(msg.get('To')),
                    'cc': dec_hdr(msg.get('Cc')),
                    'subject': dec_hdr(msg.get('Subject')),
                })
    return rows


FOLDERS = {
    'INBOX': 'INBOX',
    'Junk': 'Junk',
    'Drafts': 'Drafts',
    'Sent Messages': '"Sent Messages"',
    'Deleted Messages': '"Deleted Messages"',
}

for label, imapname in FOLDERS.items():
    item = {'imap_name': imapname, 'read': [], 'unread': []}
    try:
        sel(imapname)
        typ, u = M.uid('search', None, 'UNSEEN')
        unseen = u[0].split() if u and u[0] else []
        typ, s = M.uid('search', None, 'SEEN')
        seen = s[0].split() if s and s[0] else []
        item['unseen_count'] = len(unseen)
        item['seen_count'] = len(seen)
        item['unread'] = fetch_all(sorted(unseen, key=lambda x: int(to_str(x))))
        item['read'] = fetch_all(sorted(seen, key=lambda x: int(to_str(x))))
    except Exception as e:
        item['error'] = '%s: %s' % (type(e).__name__, e)
    res['imap'][label] = item
    print('  %-18s unread=%-4s read=%s' % (label, item.get('unseen_count'), item.get('seen_count')))

M.logout()
with open(OUT, 'w', encoding='utf-8') as fh:
    json.dump(res, fh, ensure_ascii=False, indent=2)
print('DONE')
