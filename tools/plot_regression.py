#!/usr/bin/env python3
"""Plot regression metrics from /tmp/rounds.json."""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

rounds = json.load(open('/tmp/rounds.json'))
ok = [r for r in rounds if r['status'] == 'ok' and r['elapsed']]

fig, ax = plt.subplots(1, 3, figsize=(16, 4.5))

# 1. wall time per round
ys = [r['elapsed'] for r in ok]
xs = list(range(1, len(ys) + 1))
med = sorted(ys)[len(ys) // 2]
ax[0].plot(xs, ys, marker='o', ms=3, lw=1)
ax[0].axhline(med, ls='--', c='crimson', lw=1)
ax[0].text(1, med + 6, 'median %ds' % med, color='crimson', fontsize=9)
ax[0].set_title('Wall time per round (n=%d)' % len(ys))
ax[0].set_xlabel('round\nspikes are server-side latency, not board overhead')
ax[0].set_ylabel('seconds')

# 2. request growth inside one round
sample = max(ok, key=lambda r: len(r['sizes']))
sz = sample['sizes']
ax[1].plot(range(len(sz)), sz, marker='o')
ax[1].plot([len(sz) - 1], [sz[-1]], marker='o', ms=12,
           mfc='none', mec='crimson', mew=2)
ax[1].text(len(sz) - 1, sz[-1] - 700, 'OOM point', color='crimson',
           ha='right', fontsize=9)
ax[1].set_title('Request body within one round')
ax[1].set_xlabel('iteration')
ax[1].set_ylabel('bytes')

# 3. first request per round
firsts = [r['sizes'][0] for r in rounds if r['sizes']]
fx = list(range(1, len(firsts) + 1))
ax[2].plot(fx, firsts, marker='o', ms=3, lw=1, label='after fix')
# Measured, not extrapolated: the pre-fix run only ever reached
# three rounds before the session history made serialization fail.
before = [7492, 7752, 8012]
ax[2].plot([1, 2, 3], before, ls='--', marker='s', ms=5, c='gray',
           lw=1.2, label='before fix (measured)')
ax[2].annotate('round 3: OOM,\nno further rounds',
               xy=(3, 8012), xytext=(7, 8600), color='crimson',
               fontsize=9,
               arrowprops=dict(arrowstyle='->', color='crimson', lw=1))
ax[2].set_ylim(7000, max(max(firsts), 9000) * 1.05)
ax[2].set_title('First request per round')
ax[2].set_xlabel('round')
ax[2].set_ylabel('bytes')
ax[2].legend(fontsize=8)

plt.tight_layout()
plt.savefig('docs/evidence/2026-09-18/regression.png', dpi=140)
print('saved -> docs/evidence/2026-09-18/regression.png')
