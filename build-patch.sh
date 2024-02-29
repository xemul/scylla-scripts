#!/bin/bash

FILES=$(git diff -p HEAD $1 | lsdiff -p1 | egrep '.cc|.hh' | sed -e 's#^#build/dev/#' -e 's#\.cc$#.o#' -e 's#\.hh#.hh.o#')
echo ${FILES}
ninja -j24 ${FILES}
