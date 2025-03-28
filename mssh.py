#!/bin/env python3

import os
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
    def _user_and_host(self):
        return f'{self._user}@{self._host}' if self._user is not None else self._host

    def _execute_cmd(self, args):
        cmd = ['ssh']
        if self._identity is not None:
            cmd += ['-i', self._identity]
        cmd += [ self._user_and_host() ]
        cmd += args
        return cmd

    def _copy_cmd(self, args):
        cmd = ['scp']
        if self._identity is not None:
            cmd += ['-i', self._identity]
        cmd += [args[0]]
        args.append(os.path.basename(args[0]))
        cmd += [ f'{self._user_and_host()}:{args[1]}' ]
        return cmd

    def _format_command(self):
        def fmt(a):
            return a if not (' ' in a or '\t' in a) else f'"{a}"'
        return ' '.join([ fmt(s) for s in self._command ])

    def __init__(self, user, host, args):
        self._host = host
        self._user = user
        self._identity = args.identity
        if args.command[0] == '--copy':
            self._command = self._copy_cmd(args.command[1:])
        else:
            self._command = self._execute_cmd(args.command)

    def start(self):
        self._sub = subprocess.Popen(self._command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f'Running {self._format_command()}')

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
