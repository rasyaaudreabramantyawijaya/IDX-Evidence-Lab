"""Bounded ephemeral references to already-computed Portfolio Lab outputs."""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from time import monotonic
from uuid import uuid4
from .studies_adapters import source


class StudyArtifactStore:
    def __init__(self, *, clock=monotonic, limit=16, ttl=3600):
        self.clock,self.limit,self.ttl=clock,limit,ttl
        self.items=OrderedDict();self.lock=RLock()

    def save(self, root, result):
        def paths(value):
            if isinstance(value,str): return [value]
            if isinstance(value,dict): return [p for v in value.values() for p in paths(v)]
            if isinstance(value,list): return [p for v in value for p in paths(v)]
            return []
        item=deepcopy(result)
        files=paths(item.get('provenance',{}).get('sources',{}))
        for ticker in item.get('selection',{}).get('tickers',[]):
            report=f'data/raw/sectors/company_report/{ticker}/company_report.json'
            if (root/report).is_file(): files.append(report)
        item['studies_sources']=[source(root,f) for f in sorted(set(files))]
        ref=uuid4().hex
        with self.lock:
            self.items[ref]=(self.clock(),item)
            while len(self.items)>self.limit:self.items.popitem(last=False)
        return ref

    def get(self, ref):
        with self.lock:
            now=self.clock()
            for key,(time,_) in list(self.items.items()):
                if now-time>=self.ttl:self.items.pop(key)
            value=self.items.get(ref)
            return deepcopy(value[1]) if value else None
