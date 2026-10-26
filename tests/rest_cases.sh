A=http://localhost:8080; P=0; F=0; J='Content-Type: application/json'
curl -s $A/health >/dev/null || { echo "server not running: start ./start.sh"; exit 1; }
run(){ curl -s -X POST $A/containers -H "$J" -d "$1" >/dev/null; }
del(){ curl -s -X DELETE $A/containers/$1 >/dev/null; }
logs(){ for i in 1 2 3 4 5 6 7 8 9 10; do o=$(curl -s $A/containers/$1/logs); echo "$o" | grep -q '"logs": ".' && break; sleep 1; done; echo "$o"; }
st(){ curl -s $A/containers | grep -o "\"name\": \"$1\", \"image\": \"[a-z]*\", \"status\": \"[a-z]*\"" | grep -o 'status": "[a-z]*' | cut -d'"' -f3; }
res(){ if [ "$2" = ok ]; then echo "PASS $1"; P=$((P+1)); else echo "FAIL $1"; F=$((F+1)); fi; }

del blog-demo; run '{"name":"blog-demo","image":"blog","command":["/bin/cat","/opt/index.html"]}'
L=$(logs blog-demo); echo "$L" | grep -qi 'doctype html' && r=ok || r=bad
res "B1 blog image runs cat, logs show html" $r; del blog-demo

del runner-test; run '{"name":"runner-test","image":"runner","command":["python3","-c","print(\"runner works\")"]}'
L=$(logs runner-test); sleep 2; S=$(st runner-test)
echo "$L" | grep -q 'runner works' && [ "$S" = stopped ] && r=ok || r=bad
res "B2 runner runs python, exits stopped" $r; del runner-test

del c1; run '{"name":"c1","image":"blog","command":["/bin/sh","-c","sleep 120"]}'; sleep 2; S1=$(st c1)
curl -s -X POST $A/containers/c1/stop >/dev/null; sleep 2; S2=$(st c1)
[ "$S1" = running ] && [ "$S2" = stopped ] && r=ok || r=bad
res "C1 api create running, stop makes stopped" $r; del c1

del c2; run '{"name":"c2","image":"runner","memory":"128M","command":["python3","-c","x=b\"a\"*(300*1024*1024);print(\"survived\")"]}'
sleep 6; L=$(curl -s $A/containers/c2/logs); S=$(st c2)
echo "$L" | grep -q survived && r=bad || r=ok
[ "$S" = stopped ] || r=bad
res "C2 memory limit enforced, 300MB hog killed at 128MB" $r; del c2

rm -f /tmp/test.txt; del w1; run '{"name":"w1","image":"blog","command":["/bin/sh","-c","echo hello > /tmp/test.txt && cat /tmp/test.txt"]}'
L=$(logs w1); H=clean; [ -e /tmp/test.txt ] && H=leak
echo "$L" | grep -q hello && [ "$H" = clean ] && r=ok || r=bad
res "A1 file written inside, not on host" $r; del w1

del iso1; del iso2
run '{"name":"iso1","image":"blog","command":["/bin/hostname"]}'; run '{"name":"iso2","image":"blog","command":["/bin/hostname"]}'
L1=$(logs iso1); L2=$(logs iso2); HN=$(hostname)
echo "$L1" | grep -q iso1 && echo "$L2" | grep -q iso2 && r=ok || r=bad
echo "$L1$L2" | grep -q "$HN" && r=bad
res "A2 each container has its own hostname" $r; del iso1; del iso2

echo "RESULT $P/$((P+F)) passed"; [ "$F" = 0 ]
