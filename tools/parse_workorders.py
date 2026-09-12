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
    if not title: return None
    mos=[MONTHS[w[:3].lower()] for w in re.findall(r'[A-Za-z]{3,}', title) if w[:3].lower() in MONTHS]
    nums=re.findall(r'\d+', title)
    days=[int(n) for n in nums if len(n)<=2]; years=[int(n) for n in nums if len(n)==4]
    if not mos or not days or not years: return None
    try: return datetime.date(years[-1], mos[-1], days[-1])   # end of the range
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

def _hdr_cols(row):
    cells=[(str(c).strip().lower() if c not in (None,'') else '') for c in row]
    if not any(c.startswith('lsd') or c=='map ref' for c in cells): return None
    if not any(c=='pipeline' for c in cells): return None
    cols={}
    for i,c in enumerate(cells):
        if (c.startswith('lsd') or c=='map ref') and 'lsd' not in cols: cols['lsd']=i
        elif c=='pipeline' and 'pipe' not in cols: cols['pipe']=i
        elif 'description' in c and 'desc' not in cols: cols['desc']=i
        elif 'line status' in c and 'line' not in cols: cols['line']=i
        elif 'work status' in c and 'work' not in cols: cols['work']=i
    return cols
def parse_sheet(ws, source, src):
    orders=[]; reporter=''
    cols={'lsd':0,'pipe':1,'desc':2,'line':3,'work':4}    # default layout
    for row in ws.iter_rows(values_only=True):
        hdr=_hdr_cols(row)
        if hdr: cols=hdr; continue
        def g(key):
            i=cols.get(key)
            if i is None: return ''
            v=row[i] if len(row)>i else None
            return str(v).strip() if v not in (None,'') else ''
        a=row[cols['lsd']] if len(row)>cols.get('lsd',0) else None
        a0=row[0] if len(row)>0 else None                 # column A -> patroller-name rows
        got=False
        if a:
            for frag in re.split(r'\s*(?:,|;|&|\band\b|\n)\s*', str(a), flags=re.I):
                frag=frag.strip()
                if not frag: continue
                lsd=parse_lsd(frag)
                if lsd:
                    orders.append({'raw':frag,**lsd,'reporter':reporter,'src':src,
                      'pipeline':g('pipe'),'desc':g('desc'),'line':g('line'),'work':g('work'),'week':ws.title,'source':source})
                    got=True
        if not got and a0 and str(a0).strip().upper() not in ('LSD','MAP REF','TICKET ID') and _is_name(a0) and not g('pipe') and not g('line'):
            reporter=str(a0).strip()
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
