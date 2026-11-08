#!/bin/sh

# Let's review this code.
# process the new commits
# based upon https://github.com/FreshPorts/git_proc_commit/issues/3
# An idea from https://github.com/sarcasticadmin
#
# Where we got to, for each repo and branch, is kept in a file: see
# latest-commits.sh in the scripts repo.
#

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

# latest_commit_get and latest_commit_set: where we got to, for each repo and branch
if [ ! -r ${SCRIPTDIR}/latest-commits.sh ]
then
	logfatal "${SCRIPTDIR}/latest-commits.sh not found by $0"
	exit 1
fi

. ${SCRIPTDIR}/latest-commits.sh

logfile "has started. Will check these repos: '${repos}'"

# what remote are we using on this repo?
REMOTE='origin'

# where we do dump the XML files which we create?
XML="${INGRESS_MSGDIR}/incoming"

logfile "XML dir is $XML"

result=0

for repo in ${repos}
do
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
   if [ "$?" -ne "0" ]; then
	logfile "Fatal error on git fetch: $?"
	break;
   fi
   logfile "fetch completed."

   NAME_OF_HEAD="main"
   NAME_OF_REMOTE=$REMOTE
   MAIN_BRANCH="$NAME_OF_REMOTE/$NAME_OF_HEAD"

   ${GIT} for-each-ref --format '%(objecttype) %(refname)' \
      | sed -n 's/^commit refs\/remotes\///p' \
      | while read -r refname
   do
      case $refname in
         origin/main)
            echo $refname 'processing ****'
            ;;

         origin/2[01][0-9][0-9]Q[1-4])
            echo $refname 'processing ****'
            ;;

         *)
            echo $refname skipping
            continue
            ;;
      esac

      logfile "working on '$refname'"
      # TRANSITION ONLY: the file and the tag must agree before either is used.
      # Remove with the tags.
      if ! mismatch=$(latest_commit_check ${repo} $refname ${REPODIR})
      then
         logfatal "FATAL - not processing $refname of repo '${repo}': $mismatch"
         continue
      fi

      logfile "Is $refname of repo '${repo}' in ${LATEST_COMMITS_FILE}?"

      STARTPOINT=$(latest_commit_get ${repo} $refname)
      if [ -z "$STARTPOINT" ]
      then
         if [ "$refname" == "$MAIN_BRANCH" ]
         then
            logfile "FATAL - '$MAIN_BRANCH' of repo '${repo}' must be set manually in ${LATEST_COMMITS_FILE} - special case the main branch because the best merge base is the most recent commit"
            exit
         fi
         logfile "Not found. Let's find the first commit in this branch"
         first_ref=$(${GIT} merge-base $NAME_OF_REMOTE/$NAME_OF_HEAD $refname)
         logfile "First ref is '$first_ref'"
         logfile "recording that now:"
         if ! latest_commit_set ${repo} $refname $first_ref
         then
            logfatal "FATAL - could not record '$first_ref' for $refname of repo '${repo}' in ${LATEST_COMMITS_FILE}"
            continue
         fi
         # Transition: still kept in the repo too, so the previous release can
         # be put back.  To be removed in the next release.
         ${GIT} tag -m "first known commit of $refname" -f freshports/$refname $first_ref
         STARTPOINT=$first_ref
      fi

      logfile "the latest commit we have for $refname is: $STARTPOINT"

      # e.g. a repo cloned again, and not yet fetched as far as the file says
      if ! ${GIT} cat-file -e "${STARTPOINT}^{commit}"
      then
         logfatal "FATAL - '$STARTPOINT' for $refname, from ${LATEST_COMMITS_FILE}, is not a commit in ${REPODIR}"
         continue
      fi

      # get list of commits, if only to document them here
      logfile "Running: ${GIT} rev-list $STARTPOINT..$refname"
      commits=$(${GIT} rev-list $STARTPOINT..$refname)
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
         # git-to-freshports-xml.py needs hashes, not refs.
         # STARTPOINT is already one; see https://news.freshports.org/2021/06/27/putting-the-new-git-delta-sh-into-use-on-devgit-freshports-org/
         #
         ENDPOINT=$(${GIT} rev-list -n 1 $refname)
         BRANCH=$(echo $refname | sed -n -n 's/^${NAME_OF_REMOTE}\///p')
         BRANCH=${refname#$NAME_OF_REMOTE/}
         logfile "${SCRIPTDIR}/git-to-freshports-xml.py --repo ${repo} --path ${REPODIR} --branch $BRANCH --commit-range $STARTPOINT..$ENDPOINT --spooling ${INGRESS_SPOOLINGDIR} --output ${XML}"
                  ${SCRIPTDIR}/git-to-freshports-xml.py --repo ${repo} --path ${REPODIR} --branch $BRANCH --commit-range $STARTPOINT..$ENDPOINT --spooling ${INGRESS_SPOOLINGDIR} --output ${XML}

         result=$?
         logfile "${SCRIPTDIR}/git-to-freshports-xml.py result: $result"
         if [ "$result" == "0" ]
         then
            logfile "new_latest = ${ENDPOINT}"

            # Store the last known commit that we just processed.
            # ENDPOINT, not ${refname}: that is what was processed.
            if ! latest_commit_set ${repo} ${refname} ${ENDPOINT}
            then
               logfatal "FATAL - could not record '${ENDPOINT}' for ${refname} of repo '${repo}' in ${LATEST_COMMITS_FILE}: these commits will be processed again"
            fi

            # Transition: still kept in the repo too, so the previous release can
            # be put back.  To be removed in the next release.
            ${GIT} tag -m "last known commit of ${refname}" -f freshports/${refname} ${ENDPOINT}

            # TRANSITION ONLY: and they still agree.  Remove with the tags.
            if ! mismatch=$(latest_commit_check ${repo} ${refname} ${REPODIR})
            then
               logfatal "FATAL - after recording $refname of repo '${repo}': $mismatch"
            fi
         else
            logfatal "FATAL eror with git-to-freshports-xml.py result: $result"
         fi
      fi

   done
done

logfile "Ending"

exit $result
