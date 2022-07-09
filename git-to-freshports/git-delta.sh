#!/bin/sh

# Let's review this code.
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

logfile "has started. Will check these repos: '${repos}'"

# what remote are we using on this repo?
REMOTE='origin'

# where we do dump the XML files which we create?
XML="${INGRESS_MSGDIR}/incoming"

logfile "XML dir is $XML"

result=0

for repo in ${repos}
do
   if [ "${repo}" != "ports" ]
   then
#      continue
   fi
   logfile "Now processing repo: ${repo} ---------------"

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
   LATEST_FILE="${INGRESS_PORTS_DIR_BASE}/latest.${dir}"

   if [ -d ${REPODIR} ]; then
      logfile "REPODIR='${REPODIR}' exists"
   else
      logfile "FATAL error, REPODIR='${REPODIR}' is not a directory"
      continue
   fi

   logfile "Repodir is $REPODIR"
   # on with the work

   cd ${REPODIR}

   # Bring local branch up-to-date with the local remote
   logfile "Running: ${GIT} fetch:"
   ${GIT} fetch
   logfile "fetch completed."

   NAME_OF_HEAD="main"
   NAME_OF_REMOTE=$REMOTE
   MAIN_BRANCH="$NAME_OF_REMOTE/$NAME_OF_HEAD"

   git for-each-ref --format '%(objecttype) %(refname)' \
      | sed -n 's/^commit refs\/remotes\///p' \
      | while read -r refname
   do
# if we mention all these, and we are skipping most of them, that's a
# lot of log lines to scroll past
#      logfile "looking at $refname"
      # for now, when testing, only this branch please
      if [ "$refname" != "origin/2021Q2" ] && [ "$refname" != "origin/2021Q3" ] && [ "$refname" != "$MAIN_BRANCH" ]
      then
         continue
      fi

      logfile "working on '$refname'"
      logfile "Is freshports/$refname defined on the repo '${repo}'?"
      logfile "running: git rev-parse -q --verify freshports/$refname^{}"

      if ! git rev-parse -q --verify freshports/$refname^{}
      then
         if [ "$refname" == "$MAIN_BRANCH" ]
         then
            logfile "FATAL - '$MAIN_BRANCH' must have tag 'freshports/$refname' set manually  - special case the main branch because the best merge base is the most recent commit"
            exit
         fi
         logfile "'git rev-parse -q --verify freshports/$refname^{}'" found nothing
         logfile "Let's find the first commit in this branch"
         first_ref=$(git merge-base $NAME_OF_REMOTE/$NAME_OF_HEAD $refname)
         logfile "First ref is '$first_ref'"
         # get the first commit of that branch and create a tag.
         logfile "tagging that now:"
         git tag -m "first known commit of $refname" -f freshports/$refname $first_ref
      fi

      logfile "the latest commit we have for freshports/$refname is:"
      # not sent to logfile so it output is not prefixed with a timestamp
      # and therefore is aligned with the output of 'git rev-parse -q --verify' above.
      # This makes it easier to view in the logs.
      git rev-parse freshports/$refname^{}

      # get list of commits, if only to document them here
      logfile "Running: ${GIT} rev-list freshports/$refname..$refname"
      commits=$(${GIT} rev-list freshports/$refname..$refname)
      logfile "Done."

      if [ -z "$commits" ]
      then
         logfile "No commits were found"
      else
         logfile "The commits found are:"
         for commit in $commits
         do
            logfile "$commit"
         done

         #
         # get the commit hashes associated with each of these tags
         # git-to-freshports-xml.py needs hashes, not tags
         # see https://stackoverflow.com/questions/1862423/how-to-tell-which-commit-a-tag-points-to-in-git/1862542#1862542
         #     https://news.freshports.org/2021/06/27/putting-the-new-git-delta-sh-into-use-on-devgit-freshports-org/
         #
         # for ^{} https://gitirc.eu/gitrevisions.html
         # "A suffix ^ followed by an empty brace pair means the object could be a tag, and dereference the tag recursively until a non-tag object is found. "
         #
         STARTPOINT=$(git rev-parse -q freshports/${refname}^{})
         ENDPOINT=$(git rev-list -n 1 $refname)
         BRANCH=$(echo $refname | sed -n -n 's/^${NAME_OF_REMOTE}\///p')
         BRANCH=${refname#$NAME_OF_REMOTE/}
         logfile "${SCRIPTDIR}/git-to-freshports-xml.py --repo ${repo} --path ${REPODIR} --branch $BRANCH --commit-range $STARTPOINT..$ENDPOINT --spooling ${INGRESS_SPOOLINGDIR} --output ${XML}"
                  ${SCRIPTDIR}/git-to-freshports-xml.py --repo ${repo} --path ${REPODIR} --branch $BRANCH --commit-range $STARTPOINT..$ENDPOINT --spooling ${INGRESS_SPOOLINGDIR} --output ${XML}

         result=$?
         logfile "${SCRIPTDIR}/git-to-freshports-xml.py result: $result"
         if [ "$result" == "0" ]
         then
            logfile "new_latest = $(${GIT} rev-parse ${refname})"

            # echo $new_latest > ${LATEST_FILE}
            # Store the last known commit that we just processed.
            git tag -m "last known commit of ${refname}" -f freshports/${refname} ${refname}
         else
            logfatal "FATAL eror with git-to-freshports-xml.py result: $result"
         fi
      fi

   done
done

logfile "Ending"

exit $result
