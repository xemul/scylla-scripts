#!/bin/bash
fgrep 'testing time' | fgrep case | sed -e 's/us;//' | awk '{print $5, $8/1000000}' | sort -k2n
