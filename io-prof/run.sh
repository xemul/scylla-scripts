#!/bin/bash

DUR=80
PAUS=10
MOD="rand"
DIR="/home/xfs/io_tester"

function do_measure {
    ./build/dev/apps/io_tester/io_tester --directory ${DIR} --conf conf.yaml -c1 --duration $DUR | awk 'BEGIN{all=""}/throughput:/{tot+=$2;all=all":"int($2/1000)}END{print tot/1000 all}'
    sleep $PAUS
}

PRLS="1 2 4 8 16 32"

function measure_equal {
    echo -n "${1}/${2}"
    for prl in $PRLS; do
        cat tmpl.yaml | sed -e 's/LD1/'${MOD}${1}'/' -e 's/LD2/'${MOD}${2}'/' -e 's/PRL1/'${prl}'/' -e 's/PRL2/'${prl}'/' > conf.yaml
        res=$(do_measure)
        echo -n " ${res}"
    done
    echo ""
}

function measure_shifted {
    if [ "${1}" == "0" ]; then
        echo -n "read-/write+"
    else
        echo -n "read+/write-"
    fi

    for prl in $PRLS; do
        if [ "$prl" == "1" ]; then
            echo -n " 0"
            continue
        fi

        if [ "${1}" == "0" ]; then
            prlr=$((prl/2))
            prlw=$((prl + prl/2))
        else
            prlr=$((prl + prl/2))
            prlw=$((prl/2))
        fi
        cat tmpl.yaml | sed -e 's/LD1/'${MOD}'read/' -e 's/LD2/'${MOD}'write/' -e 's/PRL1/'${prlr}'/' -e 's/PRL2/'${prlw}'/' > conf.yaml
        res=$(do_measure)
        echo -n " ${res}"
    done
    echo ""
}

# parallelizm 1 2 4 8 16 32 64 128
# rr          . . . . . . . .
# ww          . . . . . . . .
# 50-50

echo -n "parallelizm"
for prl in $PRLS; do
    echo -n "             ${prl}"
done
echo ""

#measure_shifted 1
#measure_shifted 0

measure_equal "read" "read"
measure_equal "read" "write"
measure_equal "write" "write"
