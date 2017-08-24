#!/usr/bin/env python3

import pstats
p = pstats.Stats('profile.out')
p.sort_stats('cumulative').print_stats(100)
