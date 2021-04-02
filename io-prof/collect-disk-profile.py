#!/bin/env python3

import yaml
import time
import subprocess
import argparse

parser = argparse.ArgumentParser(description='Disk profile collector')
parser.add_argument('-w', dest='wloads', action='append', help='Workloads to run (throughput or iops or $type:$request_size_in_kB)')
parser.add_argument('-p', dest='prl', choices=['dense', 'sparse'], default='dense', help='Parallelizm handling (default dense)')
parser.add_argument('-s', dest='storage', default='/mnt', help='Storage to work on (default /mnt)')
parser.add_argument('-l', dest='latency_goal', type=float, default=1.0, help='Latency goal (ms, default 1.0)')
parser.add_argument('-S', dest='data_size', default='64GB', help='Data size (default 64GB)')
parser.add_argument('-D', dest='duration', default=120, help='Duration of a single measurement (sec, default 120)')
parser.add_argument('-P', dest='pause', default=16.0, type=float, help='Pause between measuremenets (sec, default 16)')
parser.add_argument('-F', dest='fast', action='store_true', help='Fast (and inaccurate) measurement (-d 32MB -D 1 -P 0.1)')
args = parser.parse_args()

if args.fast:
    args.data_size = '32MB'
    args.duration = 1
    args.pause = 0.1

class table:
    def __init__(self, name, default = 0.0):
        self._name = name
        self._res = { (0, 0): default }
        self._rs = set([0])
        self._ws = set([0])
        self._def = default

    def add(self, rprl, wprl, t):
        self._res[(rprl, wprl)] = t
        self._rs.add(rprl)
        self._ws.add(wprl)

    def show(self):
        print(f"------------")
        rs = list(self._rs)
        rs.sort()
        ws = list(self._ws)
        ws.sort()
        print(self._name + ' ' + ' '.join([f'w{w}' for w in ws ])) # header
        for rprl in rs:
            ln = f'r{rprl}'
            skip = ''
            for wprl in ws:
                if (rprl, wprl) in self._res:
                    ln = ln + skip + f' {self._res[(rprl, wprl)]}'
                    skip = ''
                else:
                    skip = skip + f' {self._def}'
            print(ln)

    def test_fill(self):
        self.add(1, 0, "1-0")
        self.add(2, 0, "2-0")
        self.add(4, 0, "4-0")
        self.add(0, 1, "0-1")
        self.add(0, 2, "0-2")
        self.add(1, 1, "1-1")
        self.add(4, 2, "4-2")
        self.add(2, 4, "2-4")
        self.show()


class measurement:
    def __init__(self, data_size, duration_sec, pause_sec):
        self._config = []
        self._data_size = data_size
        self._duration = duration_sec
        self._pause = pause_sec
        self._io_tester = '../../seastar/build/dev/apps/io_tester/io_tester'

    def add_workload(self, typ, rqsz, prl):
        self._config.append({
            'name': f'{len(self._config)}_{typ}_{prl}',
            'shards': 'all',
            'data_size': self._data_size,
            'type': typ,
            'shard_info': {
                'parallelism': prl,
                'reqsize': rqsz,
                'shares': 100
            }
        })
        return self._config[-1]['name']

    def run(self):
        yaml.dump(self._config, open('conf.yaml', 'w'))
        self._proc = subprocess.Popen([self._io_tester, '--storage', args.storage, '-c1', '--conf', 'conf.yaml', '--duration', f'{self._duration}'], stdout=subprocess.PIPE)
        res = self._proc.communicate()
        time.sleep(self._pause)
        res = res[0].split(b'---\n')[1]
        return yaml.safe_load(res)[0]


class profile:
    class dense:
        def __init__(self):
            pass

        def add_workloads(self, m, typ, rqsz, prl):
            self._name = m.add_workload(typ, rqsz, prl)

        def get_iops(self, res):
            return float(res[self._name]['IOPS'])

        def name(self):
            return 'd' + self._name

    class sparse:
        def __init__(self):
            self._names = []
            self._max_workloads = 4

        def add_workloads(self, m, typ, rqsz, prl):
            self._typ = typ
            self._prl = prl

            if prl <= self._max_workloads:
                for i in range(0, prl):
                    nm = m.add_workload(typ, rqsz, 1)
                    self._names.append(nm)
            else:
                com = int(prl / self._max_workloads)
                rem = prl % self._max_workloads
                for i in range(0, self._max_workloads):
                    nm = m.add_workload(typ, rqsz, com + (1 if i < rem else 0))
                    self._names.append(nm)

        def get_iops(self, res):
            return sum([ float(res[n]['IOPS']) for n in self._names ])

        def name(self):
            return f's{len(self._names)}_{self._typ}_{self._prl}'

    def __init__(self, typ, rq_size, args):
        self._typ = typ
        self._req_size = rq_size
        self._delays = table(f'delays:{typ}:{rq_size}:{args.prl}')
        self._reads = table('read_iops')
        self._writes = table('write_iops')
        self._threshold = args.latency_goal
        self._prl = None
        if args.prl == 'dense':
            self._prl = self.dense
        if args.prl == 'sparse':
            self._prl = self.sparse

        self._data_size = args.data_size
        self._duration = args.duration
        self._pause = args.pause

    def _do_pure(self, direction, wtype):
        prl = 1
        while True:
            m = measurement(self._data_size, self._duration, self._pause)
            wt = wtype()
            wt.add_workloads(m, self._typ + direction, self._req_size, prl)
            res = m.run()
            iops = wt.get_iops(res)
            delay = prl / iops * 1000
            print(f'{wt.name()} {iops} {delay} ms')
            if direction == 'read':
                self._delays.add(prl, 0, delay)
                self._reads.add(prl, 0, iops)
            if direction == 'write':
                self._delays.add(0, prl, delay)
                self._writes.add(0, prl, iops)
            prl *= 2
            if delay > self._threshold or prl > 1024:
                break

    def _do_mixed(self, wtype):
        rprl = 1
        wprl = 1
        while True:
            m = measurement(self._data_size, self._duration, self._pause)
            reads = wtype()
            reads.add_workloads(m, self._typ + 'read', self._req_size, rprl)
            writes = wtype()
            writes.add_workloads(m, self._typ + 'write', self._req_size, wprl)
            res = m.run()
            riops = reads.get_iops(res)
            wiops = writes.get_iops(res)
            delay = (rprl / riops + wprl / wiops) * 1000
            print(f'{reads.name()} {riops} {writes.name()} {wiops} {delay} ms')
            self._delays.add(rprl, wprl, delay)
            self._reads.add(rprl, wprl, riops)
            self._writes.add(rprl, wprl, wiops)

            wprl *= 2
            if delay > self._threshold or wprl > 1024:
                if wprl == 2 or rprl > 1024:
                    break

                rprl *= 2
                wprl = 1

    def collect(self):
        self._do_pure('read', self._prl)
        self._do_pure('write', self._prl)
        self._do_mixed(self._prl)

    def show(self, full = True):
        print(f"========[ {self._typ}:{self._req_size} ]========")
        self._delays.show()
        if full:
            self._reads.show()
            self._writes.show()

profs = []
for w in args.wloads:
    if w == 'throughput':
        profs.append(profile('seq', '128kB', args))
    elif w == 'iops':
        profs.append(profile('rand', '4kB', args))
    else:
        wp = w.split(':')
        profs.append(profile(wp[0], wp[1]+'kB', args))

for wl in profs:
    wl.collect()
for wl in profs:
    wl.show()
