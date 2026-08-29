#!/usr/bin/env python3
"""Pull the latest client ground-disturbance .xlsx attachments from Gmail (IMAP) and
build workorders.json for EasyLSD. Runs in GitHub Actions. Credentials come from env:
  GMAIL_USER, GMAIL_APP_PASSWORD  (a Google App Password, not your login password)
  WO_QUERY  (optional Gmail search; default targets recent xlsx attachments)"""
import os, sys, imaplib, email, tempfile, json, datetime
import parse_workorders as P

USER=os.environ['GMAIL_USER']; PWD=os.environ['GMAIL_APP_PASSWORD']
QUERY=os.environ.get('WO_QUERY') or 'has:attachment filename:xlsx newer_than:21d'

def main():
    M=imaplib.IMAP4_SSL('imap.gmail.com'); M.login(USER, PWD)
    M.select('"[Gmail]/All Mail"', readonly=True)
    typ,data=M.search(None,'X-GM-RAW','"%s"'%QUERY)
    ids=data[0].split()
    if not ids:
        print('No matching emails for query:', QUERY); return 0
    allo=[]; used=set()
    for mid in reversed(ids[-12:]):                     # a few most-recent, newest first
        typ,md=M.fetch(mid,'(RFC822)')
        if not md or not md[0]: continue
        msg=email.message_from_bytes(md[0][1])
        for part in msg.walk():
            fn=part.get_filename()
            if fn and fn.lower().endswith('.xlsx') and fn not in used:
                used.add(fn)
                payload=part.get_payload(decode=True)
                if not payload: continue
                tf=tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
                tf.write(payload); tf.close()
                try: allo+=P.parse_file(tf.name, source=fn)
                except Exception as e: print('parse error on', fn, ':', e)
    M.logout()
    orders=P.merge(allo)
    doc={'updated':datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
         'orders':orders}
    json.dump(doc, open('workorders.json','w'), indent=1)
    print('wrote workorders.json:', len(orders), 'orders from', len(used), 'file(s):', sorted(used))
    return 0

if __name__=='__main__':
    sys.exit(main())
