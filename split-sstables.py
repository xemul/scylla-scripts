#!/bin/env python3

import random

nr_nodes = 5                                    # Number of nodes in the cluster
nr_tablets = 8                                  # Number of tablets in a map
nr_records = 37 * 1024                          # Total number of records inserted
max_pkey = 2048                                 # Maximum partition key value (minimum is 0)
node_memtable_size = random.randint(500, 600)   # Maximum number of records in a memtable/sstable
partition_size = random.randint(1, 16)          # Maximum number of rows in a partition

class partition:
    def __init__(self, pkey):
        self._pkey = pkey
        self._rows = {}

    def mutate_row(self, ckey):
        if ckey not in self._rows:
            self._rows[ckey] = 0
        self._rows[ckey] += 1

    def rows(self):
        return len(self._rows)


class sstable:
    sstable_id = 0

    def __init__(self, partitions, origin):
        self._id = sstable.sstable_id
        sstable.sstable_id += 1
        self._partitions = partitions
        self._origin = origin

    def key_range(self):
        return (min(self._partitions), max(self._partitions))

    def nr_partitions(self):
        return len(self._partitions)

    def nr_rows(self):
        return sum([ p.rows() for p in self._partitions.values() ])

    def origin(self):
        return self._origin

    def id(self):
        return self._id


class memtable:
    def __init__(self, origin):
        self._partitions = {}
        self._origin = origin

    def empty(self):
        return len(self._partitions) == 0

    def flush(self):
        part = self._partitions
        self._partitions = {}
        return sstable(part, self._origin)

    def mutate(self, pkey, ckey):
        if pkey not in self._partitions:
            self._partitions[pkey] = partition(pkey)
        self._partitions[pkey].mutate_row(ckey)

    def size(self):
        return sum([ p.rows() for p in self._partitions.values() ])


class node:
    node_id = 0

    def __init__(self, max_memtable_size: int):
        self._memtables = {}
        self._sstables = []
        self._memtable_size = max_memtable_size
        self._id = node.node_id
        node.node_id += 1

    def mutate(self, tid, pkey, ckey):
        if tid not in self._memtables:
            self._memtables[tid] = memtable(self._id)
        mt = self._memtables[tid]
        mt.mutate(pkey, ckey)
        threshold = random.randint(int(self._memtable_size * 0.90), self._memtable_size)
        if mt.size() >= threshold:
            self._flush(mt)

    def _flush(self, mt: memtable):
        self._sstables.append(mt.flush())

    def flush(self):
        for tid in self._memtables:
            mt = self._memtables[tid]
            if not mt.empty():
                self._flush(mt)

    def id(self):
        return self._id

    def sstables(self):
        return self._sstables


class tablet:
    tablet_id = 0

    def __init__(self, pkey, replicas):
        self._id = tablet.tablet_id
        tablet.tablet_id += 1
        self._pkey = pkey
        self._replicas = replicas

    def id(self):
        return self._id

    def rf(self):
        return len(self._replicas)

    def pkey(self):
        return self._pkey

    def has(self, node):
        return node in self._replicas

    def node_ids(self):
        return [ n.id() for n in self._replicas ]

    def mutate(self, pkey, ckey):
        for r in self._replicas:
            r.mutate(self._id, pkey, ckey)


class cluster:
    def __init__(self, memtable_size, rf = 3):
        self._nodes = []
        self._tablets = []
        self._node_memtable_size = memtable_size
        self._rf = rf

    def count_tablet_replicas(self, n):
        ret = 0
        for t in self._tablets:
            if t.has(n):
                ret += 1
        return ret

    def add_tablet(self, pkey):
        assert len(self._nodes) >= self._rf, "Not enough nodes to add tablets"
        self._nodes.sort(key = lambda r: self.count_tablet_replicas(r))
        t = tablet(pkey, self._nodes[:self._rf])
        self._tablets.append(t)
        self._tablets.sort(key = lambda t : t.pkey())

    def add_node(self):
        self._nodes.append(node(self._node_memtable_size))

    def tablet_map(self):
        tmap = {}
        for t in self._tablets:
            tmap[t.pkey()] = t.node_ids()
        return tmap

    def find_tablet(self, pkey):
        for t in self._tablets:
            if pkey <= t.pkey():
                return t

        assert False, f"Cannot find tablet for {pkey}"

    def mutate(self, pkey, ckey):
        t = self.find_tablet(pkey)
        t.mutate(pkey, ckey)

    def flush(self):
        for n in self._nodes:
            n.flush()

    def collect_sstables(self):
        ret = []
        for n in self._nodes:
            ret += n.sstables()
        return ret

    def nodes(self):
        return self._nodes


def pop_overlapping_head(sstables):
    sst = sstables.pop(0)
    rng = sst.key_range()
    ssts = [sst]
    while len(sstables) > 0:
        r = sstables[0].key_range()
        if r[0] < rng[1]:
            ssts.append(sstables.pop(0))
            rng = (rng[0], max(rng[1], r[1]))
        else:
            break
    return (rng, ssts)


def split_sstables_into_buckets(sstables):
    sstables.sort(key = lambda s : s.key_range()[0])
    ranges = []
    while len(sstables) > 0:
        ranges.append(pop_overlapping_head(sstables))
    return ranges


print('Populating cluster')
cl = cluster(node_memtable_size)
for i in range(nr_nodes):
    cl.add_node()

for t in random.sample(range(1, max_pkey-1), k=nr_tablets-1):
    cl.add_tablet(t)
cl.add_tablet(max_pkey)

print('Tablets:')
tmap = cl.tablet_map()
for tid in tmap:
    print(f'\t{tid:3} -> {tmap[tid]}')

print('Filling cluster with records')
for r in range(nr_records):
    pkey = random.randint(0, max_pkey)
    ckey = random.randint(0, partition_size)
    cl.mutate(pkey, ckey)

cl.flush()

print('Nodes:')
for n in cl.nodes():
    print(f'\t{n.id()}: {len(n.sstables())} sstables, replica for {cl.count_tablet_replicas(n)} tablets')


print('Collecting all sstables')
sstables = cl.collect_sstables()
sstables.sort(key = lambda s : s.key_range()[0])
for s in sstables:
    rng = s.key_range()
    print(f'{s.id():3}: {s.nr_partitions():5} partitions, {s.nr_rows():6} rows, range {rng[0]:6}-{rng[1]:<6}, from {s.origin()}')

print('Splitting sstables into new tablet map')
split = split_sstables_into_buckets(sstables)
for r in split:
    print(f'\t{r[0]} -> {[s.id() for s in r[1]]}')
