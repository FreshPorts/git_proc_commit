git_proc_commit turns commits in the FreeBSD git repositories (ports, src
and doc) into the XML files which the FreshPorts ingress loads into its
database.

Everything is in git-to-freshports/:

* check_git.sh runs git-delta.sh, when the check_git flag is set, and
  appends its output to the git log.
* git-delta.sh fetches each repository, and for main and each quarterly
  branch turns the commits since the last one processed into XML.  Where
  it got to is kept in latest_commits.txt (latest-commits.sh, in the
  ingress-scripts repo).
* git-to-freshports-xml.py writes one XML file per commit.
* git-single-commit.sh and git-range-of-commits.sh do the same for one
  commit, or a range, by hand.

See git-to-freshports/README.md for how to run it and its tests.

This started in 2019 as a proof of concept, with a few GitPython scripts
which have since been removed.  Background:

* https://twitter.com/DLangille/status/1172119720486723590
* https://news.freshports.org/2019/09/18/moving-towards-commit-hooks/
* https://docs.freshports.org
* https://news.freshports.org/2020/06/21/git-the-next-freshports-project/
