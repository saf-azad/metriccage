"""Parse cached fighter pages: pro record + every listed bout date (to detect history before the 2010 data window)."""
import re, pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[2]; rows=[]
for p in sorted((ROOT/'data/raw/fighters').glob('*.html')):
    html=p.read_text(errors='ignore')
    m=re.search(r'Record:\s*(\d+)-(\d+)-(\d+)',html)
    dates=re.findall(r'([A-Z][a-z]{2}\. \d{2}, \d{4})',html)
    # bout rows only: count rows with a fight-details link
    n_listed=len(set(re.findall(r'data-link="http://ufcstats.com/fight-details/([0-9a-f]+)"',html)))
    ds=pd.to_datetime(pd.Series(dates),format='%b. %d, %Y',errors='coerce').dropna()
    rows.append(dict(fighter_id=p.stem,pro_w=int(m.group(1)) if m else None,pro_l=int(m.group(2)) if m else None,pro_d=int(m.group(3)) if m else None,n_listed=n_listed,first_listed=ds.min() if len(ds) else pd.NaT))
d=pd.DataFrame(rows); d.to_parquet('data_out/fighter_pages.parquet'); print(d.describe(include='all').T.to_string())
