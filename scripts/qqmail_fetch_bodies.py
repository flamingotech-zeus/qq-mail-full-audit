# -*- coding: utf-8 -*-
"""拉取关键邮件正文纯文本摘要（只读）"""
import imaplib
import json
import re
import sys
import email
import email.header
from email.message import Message

USER, CODE, SRC, OUT = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

data = json.load(open(SRC, encoding='utf-8'))

TARGETS = [
    ('INBOX', 'read'),
    ('Sent Messages', 'read'),
    ('Drafts', 'read'),
]

M = imaplib.IMAP4_SSL('imap.qq.com', 993)
M.login(USER, CODE)


def to_str(x):
    return x.decode('ascii', 'replace') if isinstance(x, bytes) else str(x)


def sel(name):
    nm = '"%s"' % name if ' ' in name else name
    M.select(nm, readonly=True)


def text_of(msg: Message):
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        cs = part.get_content_charset() or 'utf-8'
                        body = payload.decode(cs, 'replace')
                        break
                except Exception:
                    continue
        if not body:
            for part in msg.walk():
                if part.get_content_type() == 'text/html':
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            cs = part.get_content_charset() or 'utf-8'
                            html = payload.decode(cs, 'replace')
                            html = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S | re.I)
                            html = re.sub(r'<[^>]+>', ' ', html)
                            html = html.replace('&nbsp;', ' ').replace('&amp;', '&')
                            body = html
                            break
                    except Exception:
                        continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                cs = msg.get_content_charset() or 'utf-8'
                body = payload.decode(cs, 'replace')
            if msg.get_content_type() == 'text/html' and body:
                body = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', body, flags=re.S | re.I)
                body = re.sub(r'<[^>]+>', ' ', body)
        except Exception:
            body = ''
    return ' '.join(body.split())


out = []
for folder, key in TARGETS:
    sel(folder)
    for m in data['imap'][folder].get(key, []):
        uid = m['uid']
        try:
            typ, d = M.uid('fetch', uid, '(BODY.PEEK[])')
            raw = None
            for item in d or []:
                if isinstance(item, tuple) and len(item) >= 2:
                    raw = item[1]
                    break
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            txt = text_of(msg)
            out.append({
                'folder': folder,
                'uid': uid,
                'date': m['date'],
                'from': m['from'],
                'to': m['to'],
                'subject': m['subject'],
                'size': m['size'],
                'body': txt[:1500],
            })
            print('  ok %s %s %s' % (folder, uid, m['subject'][:30]))
        except Exception as e:
            print('  ERR %s %s %s' % (folder, uid, e))

M.logout()
with open(OUT, 'w', encoding='utf-8') as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print('DONE %d' % len(out))
