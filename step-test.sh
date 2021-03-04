#!/bin/bash
TNAME=${1}
FNAMES=""
for t in $(./build/dev/test/${TNAME} --list_content 2>&1  | fgrep test_ | sed -e 's/*.*$//'); do
    echo $t;
    if ! ./build/dev/test/${TNAME} -t $t; then
        FNAMES="${FNAMES} $t"
        echo $t case failed
    fi
done

echo Failed cases: ${FNAMES}
