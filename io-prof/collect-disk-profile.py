#!/bin/env python3

import yaml
import time
import subprocess

latency_goal = 1.0 # msec
data_size = '32MB'
duration_sec = 1
pause_sec = 1
io_tester = '../../seastar/build/dev/apps/io_tester/io_tester'
storage = '/home/xfs/io_tester'


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
        print(f"------[ {self._name} ]------")
        rs = list(self._rs)
        rs.sort()
        ws = list(self._ws)
        ws.sort()
        print('-- ' + ' '.join([f'w{w}' for w in ws ])) # header
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
    def __init__(self):
        self._config = []
        self._data_size = data_size
        self._duration = f'{duration_sec}'
        self._pause = pause_sec

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
        self._proc = subprocess.Popen([io_tester, '--storage', storage, '-c1', '--conf', 'conf.yaml', '--duration', self._duration], stdout=subprocess.PIPE)
        res = self._proc.communicate()
        time.sleep(self._pause)
        res = res[0].split(b'---\n')[1]
        return yaml.safe_load(res)[0]


class profile:
    def __init__(self, typ, rq_size):
        self._typ = typ
        self._req_size = rq_size
        self._delays = table('delays')
        self._reads = table('read iops')
        self._writes = table('write iops')
        self._threshold = latency_goal

    def _do_pure(self, direction):
        prl = 1
        while True:
            m = measurement()
            name = m.add_workload(self._typ + direction, self._req_size, prl)
            res = m.run()
            iops = float(res[name]['IOPS'])
            delay = prl / iops * 1000
            print(f'{name} {iops} {delay} ms')
            if direction == 'read':
                self._delays.add(prl, 0, delay)
                self._reads.add(prl, 0, iops)
            if direction == 'write':
                self._delays.add(0, prl, delay)
                self._writes.add(0, prl, iops)
            prl *= 2
            if delay > self._threshold or prl > 1024:
                break

    def _do_mixed(self):
        rprl = 1
        wprl = 1
        while True:
            m = measurement()
            rname = m.add_workload(self._typ + 'read', self._req_size, rprl)
            wname = m.add_workload(self._typ + 'write', self._req_size, wprl)
            res = m.run()
            riops = float(res[rname]['IOPS'])
            wiops = float(res[wname]['IOPS'])
            delay = (rprl / riops + wprl / wiops) * 1000
            print(f'{rname} {riops} {wname} {wiops} {delay} ms')
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
        self._do_pure('read')
        self._do_pure('write')
        self._do_mixed()

    def show(self, full = True):
        print(f"========[ {self._typ}:{self._req_size} ]========")
        self._delays.show()
        if full:
            self._reads.show()
            self._writes.show()


p_throughput = profile('seq', '128kB')
p_throughput.collect()
p_iops = profile('rand', '4kB')
p_iops.collect()

p_throughput.show()
p_iops.show()
