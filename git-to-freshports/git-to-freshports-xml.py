#!/usr/local/bin/python

# Copyright 2019-2020 Serhii (Sergey) Kozlov
# All rights reserved
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted providing that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
# IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""Transform GIT commit entries into XML digestible by FreshPorts."""

import logging as log
import logging.config
import argparse
import pygit2
import datetime
import shutil
import sys
import tempfile
import os

from pathlib import Path
from lxml    import etree as ET


FORMAT_VERSION  = '1.5.0.0'
SYSLOG_ADDRESS  = '/var/run/log'  # Or UDP socket like ('1.2.3.4', 514)
SYSLOG_FACILITY = 'local3'

# A special git hash that denotes an empty repo. Present in every git repo.
GIT_NULL_COMMIT = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def get_config() -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-p', '--path',     type=Path, required=True, help="Path to the repository")
    parser.add_argument('-O', '--output',   type=Path, required=True, help="Output directory. Must already exist")
    parser.add_argument('-S', '--spooling', type=Path, required=True, help="Spooling directory. Must already exist and be on the same filesystem as --output")
    parser.add_argument('-r', '--repo',     required=True,            help="Repository we're working on: ports, src or doc")
    parser.add_argument('-o', '--os',       default='FreeBSD',        help="OS we're working on. Defaults to 'FreeBSD'")
    parser.add_argument('-f', '--force',    action='store_true',      help="Overwrite commit XML files if they already exist")
    parser.add_argument('-v', '--verbose',  action='store_const', const='DEBUG', default='INFO', dest='log_level', 
                                                                      help="Print more debug information")
    parser.add_argument('-l', '--log-dest', choices={'syslog', 'stderr'}, default='syslog', dest='log_destination',
                        help="Logging destination. Defaults to 'syslog'")
    parser.add_argument('-b', '--branch',   type=str, help='The branch upon which this commit occurs')

    commit_group = parser.add_mutually_exclusive_group(required=True)
    commit_group.add_argument('-c', '--commit',        help="Commit to process the tree since, up to the local HEAD. Equivalent to '--commit-range=<commit>..HEAD'. git fetch does not move the local HEAD, so in the ingress repos use --commit-range instead")
    commit_group.add_argument('-s', '--single-commit', help="Process only the supplied commit")
    commit_group.add_argument('-R', '--commit-range',  help="Range of commits to process in git format (FROM..TO)")

    return vars(parser.parse_args())


def configure_logging(log_level: str, log_destination: str) -> None:
    log_config = {
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            # Filled later
        },
        'handlers': {
            # Filled later
        },
        'loggers': {
            '': {
                'handlers': [
                    # Filler later
                ],
                'level': log_level,
                'propagate': True,
            },
        }
    }

    if log_destination == 'syslog':
        log_config['formatters']['syslog'] = {
            'format': f'{os.path.basename(sys.argv[0])}[{os.getpid()}]:[%(levelname)s] %(message)s'
        }
        log_config['handlers']['syslog'] = {
            'class': 'logging.handlers.SysLogHandler',
            'address': SYSLOG_ADDRESS,
            'facility': SYSLOG_FACILITY,
            'formatter': 'syslog',
        }
        log_config['loggers']['']['handlers'] = ['syslog']
    elif log_destination == 'stderr':
        log_config['formatters']['stderr'] = {
            'format': '%(asctime)s:[%(levelname)s]: %(message)s'
        }
        log_config['handlers']['stderr'] = {
            'class': 'logging.StreamHandler',
            'formatter': 'stderr'
        }
        log_config['loggers']['']['handlers'] = ['stderr']
    else:
        assert False, f"Unknown log_destination: {log_destination}"

    logging.config.dictConfig(log_config)


def commit_range(repo: pygit2.Repository, commit_range: str):
    start_commit_ref, end_commit_ref = commit_range.split('..')
    start_commit = repo.revparse_single(start_commit_ref).peel(pygit2.Commit)
    end_commit   = repo.revparse_single(end_commit_ref).peel(pygit2.Commit)

    #
    # Walk first parents back from END, hiding START and everything before
    # it.  When START is on END's first-parent line, that gives exactly the
    # commits after START, as before.
    #
    # The walk used to stop only on reaching START.  When START was not on
    # that line -- a force-push, a merge whose first parent is not the old
    # tip, or FROM and TO swapped -- it never did, and every commit back to
    # the root was written out: hundreds of thousands of XML files, and
    # git-delta.sh then recorded END as done.  hide() keeps the walk short,
    # and the check below refuses such a range before anything is written.
    #
    walker = repo.walk(end_commit.id)
    walker.simplify_first_parent()  # Avoid wandering off to merged branches. Same as 'git log --first-parent'
    walker.hide(start_commit.id)

    result = list(walker)

    if result:
        oldest = result[-1]
        on_line = bool(oldest.parents) and oldest.parents[0].id == start_commit.id
    else:
        on_line = end_commit.id == start_commit.id

    if not on_line:
        log.error(f"{start_commit.id} is not on the first-parent line of {end_commit.id}: "
                  f"refusing the range {commit_range} rather than guessing where it starts")
        sys.exit(1)

    return list(reversed(result))

# as taken from https://tousu.in/qa/?qa=986000/xml-filtering-out-certain-bytes-in-python

def valid_xml_char_ordinal(c):
    codepoint = ord(c)
    # conditions ordered by presumed frequency
    return (
        0x20 <= codepoint <= 0xD7FF or
        codepoint in (0x9, 0xA, 0xD) or
        0xE000 <= codepoint <= 0xFFFD or
        0x10000 <= codepoint <= 0x10FFFF
        )

def xml_text(s) -> str:
    """Drop the characters XML cannot hold, e.g. ESC from pasted terminal output.

    lxml refuses them with ValueError ("All strings must be XML
    compatible").  Only LOG used to be filtered, so one such character in a
    subject, a name, an email or a path stopped the whole run, every later
    run stopped on the same commit, and that branch was stuck until someone
    stepped in.  A path which is not UTF-8 reaches us with lone surrogates
    for its odd bytes; those are dropped too.
    """
    return ''.join(c for c in str(s) if valid_xml_char_ordinal(c))

def commit_subject(message: str) -> str:
    """The first non-blank line of the message, or '' for an empty message.

    message.splitlines()[0] raised IndexError on an empty message, which git
    allows (--allow-empty-message), with the same stuck branch as above.
    """
    for line in message.strip().splitlines():
        return xml_text(line)
    return ''

def main():
    config = get_config()
    configure_logging(config['log_level'], config['log_destination'])
    log.debug(f"Config is: {config}")

    repo = pygit2.Repository(str(config['path']))


    num_commits = 0
    if config['commit']:
        commits = commit_range(repo, f"{config['commit']}..HEAD")
        num_commits = len(commits)
    elif config['commit_range']:
        commits = commit_range(repo, config['commit_range'])
        num_commits = len(commits)
    elif config['single_commit']:
        commits = [repo.revparse_single(config['single_commit'])]
        num_commits = 1
    else:
        assert False  # This should not happen

    if (num_commits == 0):
        log.info(f"No commits found for: {config['repo']}");

    for order_number, commit in enumerate(commits):
        commit: pygit2.Commit
        subject = commit_subject(commit.message)
        log.info(f"Processing commit '{str(commit.id)} {subject}'")
        root = ET.Element('UPDATES', Version=FORMAT_VERSION, Source='git')
        update = ET.SubElement(root, 'UPDATE')

        log.debug("Getting commit datetime")
        commit_datetime = datetime.datetime.fromtimestamp(commit.commit_time, tz=datetime.UTC)
        log.debug(f"Commit datetime: {commit_datetime}")

        log.debug("Writing commit date")
        ET.SubElement(update, 'DATE', Year=str(commit_datetime.year), Month=str(commit_datetime.month),
                      Day=str(commit_datetime.day))
        log.debug("Writing commit time")
        ET.SubElement(update, 'TIME', Timezone='UTC', Hour=str(commit_datetime.hour),
                      Minute=str(commit_datetime.minute), Second=str(commit_datetime.second))
        log.debug("Writing OS entry")

        if config['branch']:
            ET.SubElement(update, 'OS', Repo=config['repo'], Id=config['os'], Branch=config['branch'])
        else:
            commit_branches = list(repo.branches.remote.with_commit(commit))
            commit_branches_num = len(commit_branches)
            if commit_branches_num == 0:
                log.error(f"Unable to get branch name for commit {str(commit.id)}: "
                          f"no remote branch contains it.  Pass --branch.")
                continue
            elif commit_branches_num > 1:
                log.warning(f"Ambiguity in getting branch name for commit {str(commit.id)}. Got branches: {commit_branches}."
                            f"Using the first one: {commit_branches[0]}")
            ET.SubElement(update, 'OS', Repo=config['repo'], Id=config['os'], Branch=commit_branches[0])

        log.debug("Writing commit message")
        text = ET.SubElement(update, 'LOG')
        # strip out any non-XML characters
        text.text = xml_text(commit.message.strip())

        log.debug("Writing author")
        people = ET.SubElement(update, 'PEOPLE')

        ET.SubElement(people, 'COMMITTER', CommitterName=xml_text(commit.committer.name), CommitterEmail=xml_text(commit.committer.email))

        ET.SubElement(people, 'AUTHOR',    AuthorName=xml_text(commit.author.name),       AuthorEmail=xml_text(commit.author.email))

        log.debug("Writing commit hash")
        ET.SubElement(update, 'COMMIT', Hash=str(commit.id), HashShort=commit.short_id,
                      Subject=subject, EncodingLosses="false", Repository=config['repo'])

        files = ET.SubElement(update, 'FILES')

        try:
            diff = repo.diff(commit.parents[0], commit)
        except IndexError:
            # commit is a root commit and has no parents
            # In this case we diff against git "null" commit
            diff = repo.diff(GIT_NULL_COMMIT, commit)

        log.debug("Writing changes")
        for diff_delta in diff.deltas:
            change_type = diff_delta.status_char()
            if change_type == 'A':
                log.debug(f"Writing change: <new> -> {diff_delta.new_file.path}")
                ET.SubElement(files, 'FILE', Action='Add', Path=xml_text(diff_delta.new_file.path))
            elif change_type == 'D':
                log.debug(f"Writing change: {diff_delta.old_file.path} -> <deleted>")
                ET.SubElement(files, 'FILE', Action='Delete', Path=xml_text(diff_delta.old_file.path))
            # No 'R': without diff.find_similar() git reports a rename as a
            # delete plus an add, which xml_munge_git.pm handles.  The branch
            # which wrote Action='Rename' could never run, and has gone; had
            # it run, xml_munge_git.pm accepts Rename but never reads
            # Destination, so the new path would have been lost.
            else:  # M and T types
                log.debug(f"Writing change: {diff_delta.old_file.path}")
                ET.SubElement(files, 'FILE', Action='Modify', Path=xml_text(diff_delta.old_file.path))

        file_name = (f"{commit_datetime.year}.{commit_datetime.month:02d}.{commit_datetime.day:02d}."
                     f"{commit_datetime.hour:02d}.{commit_datetime.minute:02d}.{commit_datetime.second:02d}."
                     f"{order_number:06d}.{str(commit.id)}.xml")
        destination = Path(config['output'], file_name)

        #
        # An XML file already waiting in the output directory is left alone
        # unless --force is given.  That was always the intent, but
        # shutil.move() overwrites without complaint, so the FileExistsError
        # handler never ran and --force made no difference: the file was
        # always replaced.
        #
        if destination.exists() and not config['force']:
            log.warning(f"{destination} already exists; not replacing it.  Use --force to replace it.")
            continue

        log.debug("Dumping XML")

        # Write to the spooling directory, then move into the output
        # directory, so the loader never reads a half-written file.  0664 so
        # that both ingress and freshports can write to it.
        temp_file = tempfile.NamedTemporaryFile(prefix='FreshPorts.ingress.', dir=config['spooling'], delete=False)
        try:
            with temp_file:
                temp_file.write(ET.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True))
            os.chmod(temp_file.name, 0o664)
            shutil.move(temp_file.name, destination)
        finally:
            # After a successful move this finds nothing.  After a failure
            # it removes the half-made FreshPorts.ingress.* file, which used
            # to be left in the spooling directory.
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)

        log.debug("Processing complete")


if __name__ == '__main__':
    main()
