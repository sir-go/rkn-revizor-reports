#!/bin/bash

script_path=/opt/revizor-check
run_timeout=300

script=${script_path}/check_revizor.py
email='//@//.//'

repfile=${script_path}/tmp/unpacked/report.csv

s=`which sleep`
p3=`which python3`
to=`which timeout`
i=`which iconv`
t=`which tail`
m=`which mail`
e=`which echo`

sleep_from=1
sleep_to=15
${s}  $[ ( ${RANDOM} % ${sleep_to} ) + ${sleep_from} ]m

(cd ${script_path} && ${to} ${run_timeout} ${p3} ${script} yesterday && ${e} 'OK' | ${m} -s 'revizor-check OK' ${email}) || \
(${i} -f cp1251 -t utf8 ${repfile} -o ${repfile}; ${t} -n +1 ${repfile} | ${m} -s 'revizor-check FAILED' ${email})
