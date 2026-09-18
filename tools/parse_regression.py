#!/usr/bin/env python3
"""Extract per-round metrics from a board serial log."""
import re
import sys
import json

def main(path):
    rounds = []
    cur = None

    for line in open(path, encoding='utf-8', errors='replace'):
        if 'BEGIN chat=heartbeat' in line:
            cur = {'sizes': [], 'status': None, 'elapsed': None,
                   'tools': None, 'hb': []}
            rounds.append(cur)
            continue
        if cur is None:
            continue

        m = re.search(r'with tools \(model: \S+, (\d+) bytes\)', line)
        if m:
            cur['sizes'].append(int(m.group(1)))

        m = re.search(r'END status=(\w+) iters=(\d+) tools=(\d+) '
                      r'llm_ms=(\d+) elapsed=(\d+)s', line)
        if m:
            cur['status'] = m.group(1)
            cur['tools'] = int(m.group(3))
            cur['llm_ms'] = int(m.group(4))
            cur['elapsed'] = int(m.group(5))
            cur = None

    # The first round runs before the clock is corrected from the HTTP
    # Date header, so its elapsed field holds an absolute epoch instead
    # of a delta. Drop anything longer than an hour.
    for r in rounds:
        if r['elapsed'] and r['elapsed'] > 3600:
            r['elapsed'] = None

    ok = [r for r in rounds if r['status'] == 'ok']
    fail = [r for r in rounds if r['status'] == 'fail']

    print('total   :', len(rounds))
    print('ok      :', len(ok))
    print('fail    :', len(fail))
    if ok:
        e = sorted(r['elapsed'] for r in ok if r['elapsed'])
        print('elapsed : min %d  median %d  max %d' %
              (e[0], e[len(e)//2], e[-1]))
    json.dump(rounds, open('/tmp/rounds.json', 'w'))
    print('-> /tmp/rounds.json')

if __name__ == '__main__':
    main(sys.argv[1])
