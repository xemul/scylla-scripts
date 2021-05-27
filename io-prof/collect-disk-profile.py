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
parser.add_argument('-fast', action='store_true', help='Fast (and inaccurate) measurement (-d 32MB -D 1 -P 0.1)')
parser.add_argument('-full', action='store_true', help='Show full stats at the end')
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
    def __init__(self, args):
        self._config = []
        self._data_size = args.data_size
        self._duration = args.duration
        self._pause = args.pause
        self._io_tester = '../../seastar/build/dev/apps/io_tester/io_tester'

    def add_workload(self, typ, rqsz, prl):
        self._config.append({
            'name': f'workload_{len(self._config)}',
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
        self._proc = subprocess.Popen([self._io_tester, '--storage', args.storage, '-c1', '--conf', 'conf.yaml', '--duration', f'{self._duration}', '--keep-files', 'true'], stdout=subprocess.PIPE)
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

    def __init__(self, typ, rq_size_r, rq_size_w, args):
        self._typ = typ
        self._req_size_r = rq_size_r
        self._req_size_w = rq_size_w
        self._rdelays = table(f'read_delays:{typ}:{rq_size_r}:{rq_size_w}:{args.prl}')
        self._wdelays = table(f'write_delays:{typ}:{rq_size_r}:{rq_size_w}:{args.prl}')
        self._reads = table('read_iops')
        self._writes = table('write_iops')
        self._threshold = args.latency_goal
        self._prl = None
        if args.prl == 'dense':
            self._prl = self.dense
        if args.prl == 'sparse':
            self._prl = self.sparse

        self._args = args

    def _do_pure(self, direction, wtype):
        prl = 1
        if direction == 'read':
            req_size = self._req_size_r
        if direction == 'write':
            req_size = self._req_size_w
        while True:
            m = measurement(self._args)
            wt = wtype()
            wt.add_workloads(m, self._typ + direction, req_size, prl)
            res = m.run()
            iops = wt.get_iops(res)
            delay = prl / iops * 1000
            print(f'{wt.name()} {iops} {delay} ms')
            if direction == 'read':
                self._rdelays.add(prl, 0, delay)
                self._reads.add(prl, 0, iops)
            if direction == 'write':
                self._wdelays.add(0, prl, delay)
                self._writes.add(0, prl, iops)
            prl *= 2
            if delay > self._threshold or prl > 1024:
                break

    def _do_mixed(self, wtype):
        rprl = 1
        wprl = 1
        while True:
            m = measurement(self._args)
            reads = wtype()
            reads.add_workloads(m, self._typ + 'read', self._req_size_r, rprl)
            writes = wtype()
            writes.add_workloads(m, self._typ + 'write', self._req_size_w, wprl)
            res = m.run()
            riops = reads.get_iops(res)
            rdelay = rprl / riops * 1000
            wiops = writes.get_iops(res)
            wdelay = wprl / wiops * 1000
            delay = (rprl / riops + wprl / wiops) * 1000
            print(f'{reads.name()} {rprl} {riops} {rdelay} ms {writes.name()} {wprl} {wiops} {wdelay} ms -> {delay} ms')
            self._rdelays.add(rprl, wprl, rdelay)
            self._reads.add(rprl, wprl, riops)
            self._wdelays.add(rprl, wprl, wdelay)
            self._writes.add(rprl, wprl, wiops)

            wprl *= 2
            if rdelay > self._threshold or wdelay > self._threshold or wprl > 1024:
                if wprl == 2 or rprl > 1024:
                    break

                rprl *= 2
                wprl = 1

    def collect(self):
        #self._do_pure('read', self._prl)
        #self._do_pure('write', self._prl)
        self._do_mixed(self._prl)

    def show(self):
        print(f"========[ {self._typ}:{self._req_size_r}:{self._req_size_w} ]========")
        self._rdelays.show()
        self._wdelays.show()
        if self._args.full:
            self._reads.show()
            self._writes.show()


class sat_row:
    def __init__(self, rqsz, tp):
        self._target = tp
        self._row = [(rqsz, tp)]

    def _deviation(self, val):
        if val > self._target:
            return 0.0
        else:
            return (self._target - val) / self._target

    def add(self, rqsz, tp):
        self._row.append((rqsz, tp))
        dev = self._deviation(tp)
        return dev > 0.04

    def _reqsz(self, sz):
        if sz < 1024:
            return f'{sz}'
        sz = int(sz / 1024)
        if sz < 1024:
            return f'{sz}k'
        sz = int(sz / 1024)
        return f'{sz}M'

    def format(self, typ):
        fmt = f'{typ}: {self._reqsz(self._row[-2][0])}\n'
        fmt += '\n'.join(f'{self._reqsz(x[0])} {x[1]} {int(self._deviation(x[1])*100)}' for x in self._row)
        return fmt

class saturation:
    def __init__(self, args):
        self._args = args

    def _measure_one(self, typ, reqsz):
        while True:
            m = measurement(self._args)
            nm = m.add_workload('seq' + typ, reqsz, 1)
            res = m.run()
            return float(res[nm]['throughput'])

    def _measure(self, typ, init_sz):
        tp_tgt = self._measure_one(typ, init_sz)
        stats = sat_row(init_sz, tp_tgt)

        sz = int(init_sz / 2)
        while sz >= 1024:
            tp = self._measure_one(typ, sz)
            if stats.add(sz, tp):
                break

            sz = int(sz / 2)

        return stats

    def collect(self):
        self._reads = self._measure('read', 32 * 1024 * 1024)
        self._writes = self._measure('write', 2 * 1024 * 1024)

    def show(self):
        print(self._reads.format('read'))
        print(self._writes.format('write'))

profs = []
for w in args.wloads:
    if w == 'saturate':
        profs.append(saturation(args))
    elif w == 'throughput':
        profs.append(profile('seq', '128kB', '128kB', args))
    elif w == 'iops':
        profs.append(profile('rand', '4kB', '4kB', args))
    else:
        wp = w.split(':')
        if len(wp) == 2:
            profs.append(profile(wp[0], wp[1]+'kB', wp[1]+'kB', args))
        if len(wp) == 3:
            profs.append(profile(wp[0], wp[1]+'kB', wp[2]+'kB', args))

for wl in profs:
    wl.collect()
for wl in profs:
    wl.show()
