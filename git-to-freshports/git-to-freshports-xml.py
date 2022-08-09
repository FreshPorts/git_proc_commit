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
    parser.add_argument('-r', '--repo',     required=True,            help="Repository we're working on. Defaults to 'ports'")
    parser.add_argument('-o', '--os',       default='FreeBSD',        help="OS we're working on. Defaults to 'FreeBSD'")
    parser.add_argument('-f', '--force',    action='store_true',      help="Overwrite commit XML files if they already exist")
    parser.add_argument('-v', '--verbose',  action='store_const', const='DEBUG', default='INFO', dest='log_level', 
                                                                      help="Print more debug information")
    parser.add_argument('-l', '--log-dest', choices={'syslog', 'stderr'}, default='syslog', dest='log_destination',
                        help="Logging destination. Defaults to 'sylog'")
    parser.add_argument('-b', '--branch',   type=str, help='The branch upon which this commit occurs')

    commit_group = parser.add_mutually_exclusive_group(required=True)
    commit_group.add_argument('-c', '--commit',        help="Commit to process the tree since. Equivalent to '--commit-range=<commit>..HEAD'")
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
    start_commit = repo.revparse_single(start_commit_ref)
    end_commit   = repo.revparse_single(end_commit_ref)

    walker = repo.walk(end_commit.oid)
    walker.simplify_first_parent()  # Avoid wandering off to merged branches. Same as 'git log --first-parent'

    result = []
    for commit in walker:
        if commit == start_commit:
            break
        result.append(commit)

    return list(reversed(result))


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
        log.info(f"Processing commit '{commit.hex} {commit.message.splitlines()[0]}'")
        root = ET.Element('UPDATES', Version=FORMAT_VERSION, Source='git')
        update = ET.SubElement(root, 'UPDATE')

        log.debug("Getting commit datetime")
        commit_datetime = datetime.datetime.utcfromtimestamp(commit.commit_time)
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
                log.error(f"Unable to get branch name for commit {commit.hex}. "
                          f"Make sure that the local tracking branch exists for the remote branch.")
                continue
            elif commit_branches_num > 1:
                log.warning(f"Ambiguity in getting branch name for commit {commit.hex}. Got branches: {commit_branches}."
                            f"Using the first one: {commit_branches[0]}")
            ET.SubElement(update, 'OS', Repo=config['repo'], Id=config['os'], Branch=commit_branches[0])

        log.debug("Writing commit message")
        text = ET.SubElement(update, 'LOG')
        text.text = commit.message.strip().encode('utf-8', 'ignore').decode('utf-8', 'ignore')

        log.debug("Writing author")
        people = ET.SubElement(update, 'PEOPLE')

        ET.SubElement(people, 'COMMITTER', CommitterName=f"{commit.committer.name}", CommitterEmail=f"{commit.committer.email}")

        ET.SubElement(people, 'AUTHOR',    AuthorName=f"{commit.author.name}",       AuthorEmail=f"{commit.author.email}")

        log.debug("Writing commit hash")
        ET.SubElement(update, 'COMMIT', Hash=commit.hex, HashShort=commit.short_id,
                      Subject=commit.message.splitlines()[0], EncodingLoses="false", Repository=config['repo'])

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
                ET.SubElement(files, 'FILE', Action='Add', Path=diff_delta.new_file.path)
            elif change_type == 'D':
                log.debug(f"Writing change: {diff_delta.old_file.path} -> <deleted>")
                ET.SubElement(files, 'FILE', Action='Delete', Path=diff_delta.old_file.path)
            elif change_type == 'R':
                log.debug(f"Writing change: {diff_delta.old_file.path} -> {diff_delta.new_file.path}")
                ET.SubElement(files, 'FILE', Action='Rename', Path=diff_delta.old_file.path, Destination=diff_delta.new_file.path)
            else:  # M and T types
                log.debug(f"Writing change: {diff_delta.old_file.path}")
                ET.SubElement(files, 'FILE', Action='Modify', Path=diff_delta.old_file.path)

        file_name = (f"{commit_datetime.year}.{commit_datetime.month:02d}.{commit_datetime.day:02d}."
                     f"{commit_datetime.hour:02d}.{commit_datetime.minute:02d}.{commit_datetime.second:02d}."
                     f"{order_number:06d}.{commit.hex}.xml")
        file_mode = 'wb' if config['force'] else 'xb'
        log.debug("Dumping XML")
        try:
            with tempfile.NamedTemporaryFile(prefix='FreshPorts.ingress.', dir=config['spooling'], delete=False) as temp_file:
                temp_file.write(ET.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True))
                temp_file.close()

                # write to a spooling directory to avoid race conditions with ingress writing and freshports reading.
                # we chmod 0644 so ingress and freshports can both write.
                # then we move.
                os.chmod(temp_file.name, 0o664)
                shutil.move(temp_file.name, Path(config['output'], file_name))
        except FileExistsError as e:
            log.warning(f"{e}, if you want to overwrite it - please specify '--force' flag")
        
        log.debug("Processing complete")


if __name__ == '__main__':
    main()
