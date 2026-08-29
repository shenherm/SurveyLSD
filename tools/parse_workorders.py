#!/usr/bin/env python3
"""Parse client Ground-Disturbance .xlsx into work-order records for EasyLSD.
Week ranking is EMAIL-based (assigned by the fetcher): for each source we keep the latest
sheet of the 3 most-recent emails = 3 weeks. LSD parsing is best-effort + normalised."""
import re, datetime, openpyxl

MONTHS={m:i for i,m in enumerate(
  ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'],1)}

def source_label(s):
    s=(s or '').lower()
    if 'hoppe' in s or "dave" in s: return 'David Hoppe (Keyera)'
    if 'nils'  in s: return 'Nils (Plains)'
    if 'trevor' in s: return 'Trevor (Plains)'
    return (s or '').strip()

def sheet_date(title):
    m=re.search(r'([A-Za-z]{3,})\.?\s*(\d{1,2})\s*[-\u2013]\s*(\d{1,2}),?\s*(\d{4})', title or '')
    if not m: return None
    mo=MONTHS.get(m.group(1)[:3].lower())
    if not mo: return None
    try: return datetime.date(int(m.group(4)), mo, int(m.group(3)))
    except ValueError: return None

def sheets_newest_first(wb):
    dated=[(sheet_date(s.title), s) for s in wb.worksheets]
    withd=sorted([(d,s) for d,s in dated if d], key=lambda x:x[0], reverse=True)
    return [s for _,s in withd] + [s for d,s in dated if not d]

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
    elif len(nums)>=2: kind,sub,sec='lsd',int(nums[0]),int(nums[1])
    elif len(nums)==1: kind,sub,sec='lsd',1,int(nums[0])
    else: return None
    if not (1<=sec<=36 and 1<=twp<=130 and 1<=rge<=34): return None
    return {'kind':kind,'sub':sub,'sec':sec,'twp':twp,'rge':rge,'mer':m}

def _is_name(v):
    if not v: return False
    v=str(v).strip()
    return bool(re.match(r"^[A-Za-z][A-Za-z.' ]{1,40}$", v)) and len(v.split())<=4

def parse_sheet(ws, source, src):
    orders=[]; reporter=''
    for row in ws.iter_rows(values_only=True):
        a=row[0] if len(row)>0 else None
        def g(i):
            v=row[i] if len(row)>i else None
            return str(v).strip() if v not in (None,'') else ''
        lsd=parse_lsd(a)
        if lsd:
            orders.append({'raw':str(a).strip(),**lsd,'reporter':reporter,'src':src,
              'pipeline':g(1),'desc':g(2),'line':g(3),'work':g(4),'week':ws.title,'source':source})
        elif a and str(a).strip().upper()!='LSD' and _is_name(a) and not g(1) and not g(3):
            reporter=str(a).strip()
    return orders

def latest_sheet_orders(path, source, src):
    """Most-recent sheet only (the client rule for Dave's multi-week files)."""
    wb=openpyxl.load_workbook(path, data_only=True)
    sheets=sheets_newest_first(wb)
    return parse_sheet(sheets[0], source, src) if sheets else []

def merge(all_orders):
    seen={}; out=[]
    for o in all_orders:
        k=(o['raw'].upper(), o['desc'].lower(), o.get('src',''))
        if k in seen:
            if o['wi']<out[seen[k]]['wi']: out[seen[k]]=o
        else:
            seen[k]=len(out); out.append(o)
    return out
