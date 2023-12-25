#!/bin/sh

# Dump the latest processed commits.
# based upon git-delta.sh
# They should be kept in sync.
#

if [ ! -f /usr/local/etc/freshports/config.sh ]
then
	echo "/usr/local/etc/freshports/config.sh.sh not found by $0"
	exit 1
fi

. /usr/local/etc/freshports/config.sh

# this can be a space separated list of repositories to check
# e.g. "doc ports src"
repos="${REPOS_TO_CHECK_GIT}"

LOGGERTAG='git-delta.sh'

# what remote are we using on this repo?
REMOTE='origin'

# where we do dump the XML files which we create?
XML="${INGRESS_MSGDIR}/incoming"

result=0

for repo in ${repos}
do
   # convert the repo label to a physical directory on disk
   dir=$(convert_repo_label_to_directory ${repo})

   # empty means error
   if [  "${dir}" == "" ]; then
      logfile "FATAL error, repo='${repo}' is unknown: cannot translate it to a directory name"
      continue
   fi

   # where is the repo directory?
   # This is the directory which contains the repos.
   REPODIR="${INGRESS_PORTS_DIR_BASE}/${dir}"

   if [ -d ${REPODIR} ]; then
   else
      logfile "FATAL error, REPODIR='${REPODIR}' is not a directory"
      continue
   fi

   # on with the work

   cd ${REPODIR}

   NAME_OF_HEAD="main"
   NAME_OF_REMOTE=$REMOTE
   MAIN_BRANCH="$NAME_OF_REMOTE/$NAME_OF_HEAD"

   ${GIT} for-each-ref --format '%(objecttype) %(refname)' \
      | sed -n 's/^commit refs\/remotes\///p' \
      | while read -r refname
   do
      case $refname in
         origin/main)
            ;;

         origin/2[01][0-9][0-9]Q[1-4])
            ;;

         *)
            continue
            ;;
      esac

      ref=$(${GIT} rev-parse freshports/$refname^{})
      echo "$repo:freshports/$refname:$ref"

   done
done
logger things

exit $result
