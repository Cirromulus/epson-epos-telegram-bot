#!/bin/sh

#set -x

root="$(realpath $0)"
root="$(dirname ${root})"
py="venv/bin/python"

name=bonbot

logfile="${root}/${name}.log"
pidfile="${root}/.pid_${name}"

touch ${pidfile}

pid=$(cat ${pidfile})

usage()
{
	echo "Usage: $0 <start,stop>"
	exit
}

stop()
{
	echo "Stopping!"
	echo kill ${name}: ${pid}
	kill ${pid} || true
	echo "" > ${pidfile}
}

start()
{
	if ps -p "${pid}" > /dev/null; then
		echo "${name} already running: ${pid}!"
		stop
	fi

	if [ -z "${logfile}" ]; then
		logfile="/dev/stdout"
	else
		# Python increases the buffer when not in "interactive" mode
		export PYTHONUNBUFFERED=YES
	fi

	echo "Trying to log to ${logfile}"

	cd ${root}
        ${py} ${name}.py ${param} > ${logfile} 2>&1 &
	pid=$!
	cd -

	echo "started ${name} as ${pid}."
	echo ${pid} > ${pidfile}
	
	if ! ps -p "${pid}" > /dev/null; then
		echo "Seems to not be started"
		stop
	fi
}


if [ "$#" -ne 1 ] ; then
	echo "Not enough arguments."
	usage
elif [ "$1" = "stop" ] ; then
	stop
elif [ "$1" = "start" ] ; then
	start
else
	echo "not the correct keywords."
	usage
fi
