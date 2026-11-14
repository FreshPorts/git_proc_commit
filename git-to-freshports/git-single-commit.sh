#!/bin/sh

# process a single commit
# based upon https://github.com/FreshPorts/git_proc_commit/issues/3
# An idea from https://github.com/sarcasticadmin

# usage: git-single-commit.sh repo commit [branch]
#
# branch is the branch the commit is on: main, or a quarterly branch such
# as 2026Q4.  It defaults to main.  It used to be left to
# git-to-freshports-xml.py, which took the first remote branch containing
# the commit: a name such as origin/HEAD or origin/2020Q4, which
# xml_munge_git.pm does not know, so the commit was filed under a branch
# of that name.
repo=$1
commit_hash=$2
branch=${3:-main}

echo "$0 starting up with repo='$repo', commit='$commit_hash' and branch='$branch'"

if [ ! -f /usr/local/etc/freshports/config.sh ]
then
	echo "/usr/local/etc/freshports/config.sh not found by $0"
	exit 1
fi

. /usr/local/etc/freshports/config.sh

LOGGERTAG='git-single-commit.sh'

# convert the repo label to a physical directory on disk
dir=$(convert_repo_label_to_directory ${repo})

# empty means error
if [  "${dir}" == "" ]; then
   ${LOGGER} -t ${LOGGERTAG} FATAL error, repo='${repo}' is unknown: cannot translate it to a directory name
   echo "FATAL error, repo='${repo}' is unknown"
   exit 1
fi


# where is the repo directory?
# We may have to pass the repo name in as a parameter.
REPODIR="${INGRESS_PORTS_DIR_BASE}/${dir}"

if [ ! -d ${REPODIR} ]; then
   ${LOGGER} -t ${LOGGERTAG} FATAL error, REPODIR='${REPODIR}' is not a directory
   echo "FATAL error, REPODIR='${REPODIR}' is not a directory"
   exit 1
fi
  

${LOGGER} -t ${LOGGERTAG} has started
logfile "started"

# where we do dump the XML files which we create?
XML="${INGRESS_MSGDIR}/incoming"

logfile "repo is $REPODIR"
logfile "XML dir is $XML"

cd ${REPODIR} || exit 1

logfile "${SCRIPTDIR}/git-to-freshports-xml.py --repo ${repo} --path ${REPODIR} --branch ${branch} --single-commit ${commit_hash} --spooling ${INGRESS_SPOOLINGDIR} --output ${XML}"
         ${SCRIPTDIR}/git-to-freshports-xml.py --repo ${repo} --path ${REPODIR} --branch ${branch} --single-commit ${commit_hash} --spooling ${INGRESS_SPOOLINGDIR} --output ${XML}

status=$?

${LOGGER} -t ${LOGGERTAG} ending, git-to-freshports-xml.py exited $status
logfile "ending, git-to-freshports-xml.py exited $status"

exit $status
