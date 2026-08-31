#!/usr/bin/env python3
"""Pull recent client ground-disturbance .xlsx from Gmail (IMAP) -> workorders.json.
Per SOURCE (David Hoppe/Keyera, Nils/Plains, Trevor/Plains) we take the LATEST sheet of the
3 most-recent emails = 3 weeks (newest email = this week). Env:
  GMAIL_USER, GMAIL_APP_PASSWORD, WO_QUERY (optional Gmail search)."""
import os, sys, imaplib, email, tempfile, json, datetime
from email.utils import parsedate_to_datetime
import parse_workorders as P

USER=os.environ['GMAIL_USER']; PWD=os.environ['GMAIL_APP_PASSWORD']
QUERY=os.environ.get('WO_QUERY') or 'has:attachment filename:xlsx newer_than:40d'

def main():
    M=imaplib.IMAP4_SSL('imap.gmail.com'); M.login(USER, PWD)
    M.select('"[Gmail]/All Mail"', readonly=True)
    typ,data=M.search(None,'X-GM-RAW','"%s"'%QUERY)
    ids=data[0].split()
    if not ids:
        print('No matching emails for query:', QUERY); return 0
    # collect (date, from, message-id) then process newest-first
    metas=[]
    for mid in ids[-40:]:
        typ,md=M.fetch(mid,'(BODY.PEEK[HEADER.FIELDS (FROM DATE)])')
        hdr=email.message_from_bytes(md[0][1]) if md and md[0] else None
        if not hdr: continue
        try: dt=parsedate_to_datetime(hdr.get('Date'))
        except Exception: dt=None
        metas.append((dt or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc), hdr.get('From',''), mid))
    metas.sort(key=lambda x:x[0], reverse=True)   # newest first

    allo=[]; rank={}; emails=[]
    for dt, frm, mid in metas:
        src=P.source_label(frm)
        r=rank.get(src,0)
        if r>=3: continue                          # 3 weeks per source
        typ,md=M.fetch(mid,'(RFC822)')
        if not md or not md[0]: continue
        msg=email.message_from_bytes(md[0][1])
        got=False
        for part in msg.walk():
            fn=part.get_filename()
            if fn and fn.lower().endswith('.xlsx'):
                payload=part.get_payload(decode=True)
                if not payload: continue
                tf=tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False); tf.write(payload); tf.close()
                try:
                    for o in P.latest_sheet_orders(tf.name, source=fn, src=src):
                        o['wi']=r; allo.append(o)
                    got=True
                except Exception as e: print('parse error on', fn, ':', e)
        if got:
            rank[src]=r+1
            emails.append({'source':src or '', 'date':(dt.isoformat() if getattr(dt,'year',0)>2000 else ''), 'week':r})
            print(f"  email {dt:%Y-%m-%d} from '{frm[:40]}' -> {src or '?'} (week {r})")
    M.logout()
    orders=P.merge(allo)
    emails.sort(key=lambda e:e['date'] or '', reverse=True)
    doc={'updated':datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
         'emails':emails, 'orders':orders}
    json.dump(doc, open('workorders.json','w'), indent=1)
    print('wrote workorders.json:', len(orders), 'orders;', len(emails), 'emails; weeks/source:', rank)
    return 0

if __name__=='__main__':
    sys.exit(main())
