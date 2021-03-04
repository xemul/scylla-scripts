#!/bin/bash

FILES=$(git diff -p HEAD $1 | lsdiff -p1 | fgrep .cc | sed -e 's#^#build/dev/#' -e 's#\.cc$#.o#')
echo ${FILES}
ninja -j24 ${FILES}
