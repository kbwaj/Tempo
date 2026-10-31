"""Cold-start request lower bound under the declared catalog API contract.

Each product requires one item-bound inventory receipt and one write. Every
needed immutable lookup key requires a server-issued receipt. A lookup request
covers at most batch_size keys of ONE kind, tenant and snapshot. Therefore:
2*N + sum_over_lookup_scopes(ceil(unique_keys / batch_size)) is a lower bound.
No retries are required in the primary quota-only demo. Hitting the bound there
establishes request-count optimality within this contract, not global latency
optimality, production equivalence or superiority to any named product.
"""
import math
from catalog.model import items_for


def lower_bound(scenario):
    scopes={}
    for item in items_for(scenario):
        for kind,key in [('category',item.category),('fx',item.currency)]:
            scopes.setdefault((kind,item.tenant,item.snapshot),set()).add(key)
    groups=[{'kind':kind,'tenant':tenant,'snapshot':snapshot,'unique_keys':len(keys),
             'minimum_requests':math.ceil(len(keys)/scenario.batch_size)} for (kind,tenant,snapshot),keys in sorted(scopes.items())]
    enrichment=sum(g['minimum_requests'] for g in groups)
    return {'minimum_inventory_requests':scenario.jobs,'minimum_write_requests':scenario.jobs,
            'minimum_enrichment_requests':enrichment,'minimum_total_requests':2*scenario.jobs+enrichment,
            'lookup_scopes':groups,'assumptions':['Cold server/client state for each run','One item-bound inventory read and one write per output',
                'Required lookup receipts must be obtained from provider','Bulk requests contain one kind/tenant/snapshot and at most batch_size keys',
                'Category and FX are immutable within explicit tenant/snapshot','One quota unit per request, including a bulk lookup'],
            'scope':'Request-count lower bound under the declared API; not a latency-optimality or production claim.'}
