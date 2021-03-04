#!/bin/bash

FROM=${1:-master}
CURRENT=$(git rev-parse --abbrev-ref HEAD)
echo "Will build ${FROM}..${CURRENT}"
COMMITS=$(git log ${FROM}.. | awk '/^commit /{print $2}' | tac)

BFAILS=""
TFAILS=""

do_build() {
    if [ $(basename $(pwd)) == "seastar" ]; then
        ninja -j48 -C build/dev
    else
        ninja -j48 dev-build
    fi
}

do_test() {
    if [ "x${NO_TEST}" == "x" ]; then
        ./test.py --mode=dev
    fi
}

for CMT in ${COMMITS}; do
    echo "======== Check ${CMT} ========"
    git checkout ${CMT}

    echo "-------- Build ${CMT} --------"
    if ! do_build ; then
        BFAILS="${BFAILS} $CMT"
    fi
done

echo "======== Final Grand Check ========"
git checkout -f ${CURRENT}
if ! do_build ; then
    BFAILS="${BFAILS} HEAD"
else
    echo "-------- Tests ${CMT} --------"
    if ! do_test ; then
        TFAILS="${TFAILS} HEAD"
    fi
fi

if [ "x${BFAILS}${TFAILS}" == "x" ] ; then
    echo "SUCCESS"
else
    echo "BUILD FAILED: ${BFAILS}"
    echo "TESTS FAILED: ${TFAILS}"
fi
