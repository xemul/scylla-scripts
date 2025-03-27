#!/bin/env python3

import argparse
import subprocess
import colorama

colorama.init(autoreset=True)

parser = argparse.ArgumentParser(description='MSSH options')
parser.add_argument('hosts', type=str, help='List of hosts (colon-separated)')
parser.add_argument('-i', dest='identity', type=str, help='Identity file (passed to ssh as is)')
parser.add_argument('command', nargs=argparse.REMAINDER)
args = parser.parse_args()

class remote:
    def __init__(self, user, host, args):
        self._host = host
        self._user = user
        self._identity = args.identity
        self._command = args.command

    def start(self):
        cmd = ['ssh']
        if self._identity is not None:
            cmd += ['-i', self._identity]
        if self._user is not None:
            cmd += [f'{self._user}@{self._host}']
        else:
            cmd += [self._host]
        cmd += self._command
        self._sub = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f'Running {cmd}')

    def join(self):
        out, err = self._sub.communicate()
        self._out = out
        self._err = err

    def report(self):
        ret = self._sub.wait()
        if ret == 0:
            print(colorama.Fore.GREEN + f'Host {self._host} finished')
        else:
            print(colorama.Fore.RED + f'Host {self._host} finished with {ret}')
        print(colorama.Fore.CYAN + 'stdout ' + '-'*80)
        print(self._out.decode('utf-8'))
        print(colorama.Fore.CYAN + 'stderr' + '-'*80)
        print(self._err.decode('utf-8'))

remotes = []
user_and_hosts = args.hosts.split('@', 2)
user = user_and_hosts[0] if len(user_and_hosts) == 2 else ''
hosts = user_and_hosts[-1]

for h in hosts.split(':'):
    remotes.append(remote(user, h, args))

for r in remotes:
    r.start()

for r in remotes:
    r.join()

for r in remotes:
    r.report()
