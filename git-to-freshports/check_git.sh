#!/bin/sh

# This script exists mainly to redirect the output of git-delta.sh to a logfile.
#

if [ ! -f /usr/local/etc/freshports/config.sh ]
then
	echo "/usr/local/etc/freshports/config.sh not found by $0"
	exit 1
fi

. /usr/local/etc/freshports/config.sh

LOGGERTAG="check_git.sh[$$]"

${LOGGER} -t ${LOGGERTAG} $0 has started

#
# Remove the flag first, then fetch.  A flag set while git-delta.sh runs
# is then still there when it finishes, and job-waiting.pl, which loops
# until no flag is left, runs this again for the commits pushed since the
# fetch.  The flag used to be removed afterwards, which threw that request
# away: those commits waited for the next touch from cron.
#
/bin/rm -f ${CHECKGITFILE}

# redirect everything into the file
# the "quotes" around REPOS_TO_CHECK_GIT are required because it is a string as a single parameter
${SCRIPTDIR}/git-delta.sh "$REPOS_TO_CHECK_GIT" >> ${GITLOG} 2>&1
status=$?

# pass git-delta.sh's status on, so job-waiting.pl reports a failure as one
${LOGGER} -t ${LOGGERTAG} $0 has finished, git-delta.sh exited $status

exit $status
