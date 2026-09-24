from __future__ import annotations
import hashlib, json, os, re, sqlite3, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

UA='VisionPulse/1.0 official venue importer'
YEARS=tuple(int(x) for x in os.getenv('IMPORT_YEARS','2022,2023,2024,2025').split(',') if x.strip())

def norm(s): return ' '.join(re.findall(r'[a-z0-9]+',(s or '').casefold()))
def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=40) as r: return r.read().decode('utf-8','replace')
class Links(HTMLParser):
    def __init__(self): super().__init__(); self.out=[]; self.href=None; self.parts=[]
    def handle_starttag(self,t,a):
        if t=='a': self.href=dict(a).get('href'); self.parts=[]
    def handle_data(self,d):
        if self.href: self.parts.append(d)
    def handle_endtag(self,t):
        if t=='a' and self.href:
            title=' '.join(''.join(self.parts).split())
            if title: self.out.append((title,self.href))
            self.href=None
class Abstract(HTMLParser):
    def __init__(self): super().__init__(); self.depth=0; self.parts=[]
    def handle_starttag(self,t,a):
        m=' '.join(str(v or '') for k,v in a if k in ('id','class')).lower()
        if self.depth and t=='div': self.depth+=1
        elif t=='div' and 'abstract' in m: self.depth=1
    def handle_data(self,d):
        if self.depth: self.parts.append(d)
    def handle_endtag(self,t):
        if self.depth and t=='div': self.depth-=1
    def text(self): return re.sub(r'^abstract\s*:?\s*',' ',' '.join(' '.join(self.parts).split()),flags=re.I).strip()
def collect():
    items=[]
    for venue in ('CVPR','ICCV'):
        for year in YEARS:
            url=f'https://openaccess.thecvf.com/{venue}{year}?day=all'
            try:
                p=Links(); p.feed(get(url))
                for title,href in p.out:
                    if href.endswith('_paper.html'): items.append((title,venue,year,urllib.parse.urljoin(url,href)))
                print('scanned',venue,year)
            except Exception as e: print('failed',venue,year,e)
            time.sleep(1)
    try:
        p=Links(); base='https://www.ecva.net/papers.php'; p.feed(get(base))
        for title,href in p.out:
            m=re.search(r'papers/eccv_(2022|2024)/.*_paper\.php',href,re.I)
            if m and int(m.group(1)) in YEARS: items.append((title,'ECCV',int(m.group(1)),urllib.parse.urljoin(base,href)))
        print('scanned ECCV')
    except Exception as e: print('failed ECCV',e)
    return {norm(t):(t,v,y,u) for t,v,y,u in items if norm(t)}
def main():
    dbpath=Path(os.getenv('VISIONPULSE_DB','/app/data/visionpulse.sqlite3')); idx=collect(); db=sqlite3.connect(dbpath); db.row_factory=sqlite3.Row
    inserted=updated=0
    for key,(title,venue,year,url) in idx.items():
        row=db.execute('select id,abstract from papers where title_normalized=? order by id limit 1',(key,)).fetchone()
        abstract=None
        try:
            p=Abstract(); p.feed(get(url)); abstract=p.text() or None
        except Exception as e: print('page failed',title[:60],e)
        if row:
            if abstract and not (row['abstract'] or '').strip(): db.execute('update papers set abstract=? where id=?',(abstract,row['id'])); updated+=1
        else:
            stable='venue:'+hashlib.sha256(key.encode()).hexdigest()[:32]
            db.execute('insert or ignore into papers(title,title_normalized,authors_json,venue,year,doi,dblp_url,electronic_edition_json,dblp_key,paper_type,abstract,keywords_json,source_query,fetched_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(title,key,'[]',venue,year,None,url,json.dumps([url]),stable,'venue-import',abstract,'[]','official-venue',datetime.now(timezone.utc).isoformat())); inserted+=1
        time.sleep(.1)
    db.commit(); db.close(); print({'source_papers':len(idx),'inserted':inserted,'abstracts_updated':updated})
if __name__=='__main__': main()
