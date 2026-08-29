#!/usr/bin/env python3
"""Parse client Ground-Disturbance .xlsx files into workorders.json for EasyLSD.
Handles both known layouts (weekly multi-sheet w/ header + patroller-name rows, and flat
single-sheet). Keeps the 3 most-recent weeks. LSD parsing is best-effort and normalised."""
import re, sys, json, datetime, openpyxl

MONTHS={m:i for i,m in enumerate(
  ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'],1)}

def sheet_date(title):
    m=re.search(r'([A-Za-z]{3,})\.?\s*(\d{1,2})\s*[-\u2013]\s*(\d{1,2}),?\s*(\d{4})', title or '')
    if not m: return None
    mo=MONTHS.get(m.group(1)[:3].lower())
    if not mo: return None
    try: return datetime.date(int(m.group(4)), mo, int(m.group(3)))
    except ValueError: return None

def parse_lsd(s):
    if not s: return None
    s=str(s).strip().upper().replace('\u2014','-').replace('\u2013','-')
    mer=re.search(r'W\s*([1-6])\s*M?\s*$', s)
    if not mer: return None
    m=int(mer.group(1)); body=s[:mer.start()].strip(' -.')
    tr=re.search(r'[-\s](\d{1,3})[-\s](\d{1,3})\s*$', body)
    if not tr: return None
    twp,rge=int(tr.group(1)),int(tr.group(2)); head=body[:tr.start()].strip(' -.')
    quarters=re.findall(r'N[EW]|S[EW]', head)
    nums=re.findall(r'\d+', re.sub(r'N[EW]|S[EW]',' ',head))
    if quarters:
        if not nums: return None
        kind,sub,sec='qtr',quarters[-1],int(nums[0])
    elif len(nums)>=2:
        kind,sub,sec='lsd',int(nums[0]),int(nums[1])
    elif len(nums)==1:
        kind,sub,sec='lsd',1,int(nums[0])
    else: return None
    if not (1<=sec<=36 and 1<=twp<=130 and 1<=rge<=34): return None
    return {'kind':kind,'sub':sub,'sec':sec,'twp':twp,'rge':rge,'mer':m}

def is_name(v):   # patroller-name group row: a couple of words, no digits
    if not v: return False
    v=str(v).strip()
    return bool(re.match(r'^[A-Za-z][A-Za-z.\' ]{1,40}$', v)) and len(v.split())<=4

def parse_sheet(ws, wi, source):
    orders=[]; reporter=''
    for row in ws.iter_rows(values_only=True):
        a=row[0] if len(row)>0 else None
        def g(i):
            v=row[i] if len(row)>i else None
            return str(v).strip() if v not in (None,'') else ''
        lsd=parse_lsd(a)
        if lsd:
            orders.append({'raw':str(a).strip(),**lsd,'reporter':reporter,
              'pipeline':g(1),'desc':g(2),'line':g(3),'work':g(4),
              'week':ws.title,'wi':wi,'source':source})
        elif a and str(a).strip().upper()!='LSD' and is_name(a) and not g(1) and not g(3):
            reporter=str(a).strip()          # a patroller-name group header
    return orders

def parse_file(path, source=None):
    source=source or path.split('/')[-1]
    wb=openpyxl.load_workbook(path, data_only=True)
    dated=[(sheet_date(s.title), s) for s in wb.worksheets]
    withd=sorted([(d,s) for d,s in dated if d], key=lambda x:x[0], reverse=True)
    ordered=[s for _,s in withd]+[s for d,s in dated if not d]
    out=[]
    for wi,s in enumerate(ordered[:3]):     # 3 most-recent weeks
        out+=parse_sheet(s, wi, source)
    return out

def merge(all_orders):
    seen={}; out=[]
    for o in all_orders:
        k=(o['raw'].upper(), o['desc'].lower())
        if k in seen:                        # ongoing work across weeks -> keep the most recent
            if o['wi']<out[seen[k]]['wi']: out[seen[k]]=o
        else:
            seen[k]=len(out); out.append(o)
    return out

if __name__=='__main__':
    import sys, json, datetime
    files=sys.argv[1:]
    allo=[]
    for f in files: allo+=parse_file(f)
    orders=merge(allo)
    doc={'updated':datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),'orders':orders}
    json.dump(doc, open('workorders.json','w'), indent=1)
    print('wrote workorders.json:', len(orders), 'orders')
