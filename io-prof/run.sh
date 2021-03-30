#!/bin/bash

set -e

DUR=80
PAUS=10
DIR="/mnt"
IOT="../../seastar/build/dev/apps/io_tester/io_tester"

function do_measure {
    $IOT --storage ${DIR} --conf conf.yaml -c1 --duration $DUR | awk '/IOPS/{res=res" "$2}END{print res}'
    sleep $PAUS
}

PRLS="1 2 4 8 16 32 64 128 256"

for prl in $PRLS; do
	echo -n "read ${prl} "
        cat tmpl-p.yaml | sed -e 's/LD/seqread/' -e 's/PRL/'${prl}'/' > conf.yaml
	do_measure
done

for prl in $PRLS; do
	echo -n "write ${prl} "
        cat tmpl-p.yaml | sed -e 's/LD/seqwrite/' -e 's/PRL/'${prl}'/' > conf.yaml
	do_measure
done

for rprl in $PRLS; do
	for wprl in $PRLS; do
		echo -n "read ${rprl} write ${wprl} "
		cat tmpl.yaml | sed -e 's/LD1/seqread/' -e 's/LD2/seqwrite/' -e 's/PRL1/'${rprl}'/' -e 's/PRL2/'${wprl}'/' > conf.yaml
		do_measure
	done
done
