#!/bin/sh

# process the new commits
# based upon https://github.com/FreshPorts/git_proc_commit/issues/3
# An idea from https://github.com/sarcasticadmin

if [ ! -f /usr/local/etc/freshports/config.sh ]
then
	echo "/usr/local/etc/freshports/config.sh.sh not found by $0"
	exit 1
fi

# this can be a space separated list of repositories to check
# e.g. "doc ports src"
repos=$1


. /usr/local/etc/freshports/config.sh

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

   # Bring local branch up-to-date with the local remote
#   ${GIT} fetch

   NAME_OF_HEAD="main"
   NAME_OF_REMOTE=$REMOTE
   MAIN_BRANCH="$NAME_OF_REMOTE/$NAME_OF_HEAD"

   ${GIT} for-each-ref --format '%(objecttype) %(refname)' \
      | sed -n 's/^commit refs\/remotes\///p' \
      | while read -r refname
   do
      case $refname in
         origin/main)
#            echo $refname 'processing ****'
            ;;

         origin/2[01][0-9][0-9]Q[1-4])
#            echo $refname 'processing ****'
            ;;

         *)
#            echo $refname skipping
            continue
            ;;
      esac

      ref=$(${GIT} rev-parse -q --verify freshports/$refname^{})
#      echo $ref

      echo -n "$repo:freshports/$refname:"
      # not sent to logfile so it output is not prefixed with a timestamp
      # and therefore is aligned with the output of 'git rev-parse -q --verify' above.
      # This makes it easier to view in the logs.
      ref=$(${GIT} rev-parse freshports/$refname^{})
      echo "$ref"

   done
done

exit $result
