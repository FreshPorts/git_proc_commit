#!/usr/bin/env python3

# Copyright 2019 Serhii (Sergey) Kozlov
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
import git
import datetime
import sys
import os
from pathlib import Path
from lxml import etree as ET


FORMAT_VERSION = '1.4.0.0'
SYSLOG_ADDRESS = '/dev/log'  # Or UDP socket like ('1.2.3.4', 514)
SYSLOG_FACILITY = 'local3'


def get_config() -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-p', '--path', type=Path, required=True, help="Path to the repository")
    parser.add_argument('-O', '--output', type=Path, required=True, help="Output directory. Must already exist")
    parser.add_argument('-r', '--repo', default='ports', help="Repository we're working on. Defaults to 'ports'")
    parser.add_argument('-o', '--os', default='FreeBSD', help="OS we're working on. Defaults to 'FreeBSD'")
    parser.add_argument('-f', '--force', action='store_true', help="Overwrite commit XML files if they already exist")
    parser.add_argument('-v', '--verbose', action='store_const', const='DEBUG', default='INFO', dest='log_level',
                        help="Print more debug information")

    commit_group = parser.add_mutually_exclusive_group(required=True)
    commit_group.add_argument('-c', '--commit',
                              help="Commit to process the tree since. Equivalent to '--commit-range=<commit>..HEAD'")
    commit_group.add_argument('-s', '--single-commit', help="Process only the supplied commit")
    commit_group.add_argument('-R', '--commit-range', help="Range of commits to process in git format (FROM..TO)")

    return vars(parser.parse_args())


def configure_logging(log_level: str) -> None:
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            'syslog': {
                'format': f'{os.path.basename(sys.argv[0])}[{os.getpid()}]:[%(levelname)s] %(message)s'
            }
        },
        'handlers': {
            'syslog': {
                'class': 'logging.handlers.SysLogHandler',
                'address': SYSLOG_ADDRESS,
                'facility': SYSLOG_FACILITY,
                'formatter': 'syslog',
            },
        },
        'loggers': {
            '': {
                'handlers': ['syslog'],
                'level': log_level,
                'propagate': True,
            },
        }
    })


def main():
    config = get_config()
    configure_logging(config['log_level'])
    log.debug(f"Config is: {config}")

    repo = git.Repo(str(config['path']))

    if config['commit']:
        commits = reversed(list(repo.iter_commits(f"{config['commit']}..HEAD")))
    elif config['commit_range']:
        commits = reversed(list(repo.iter_commits(config['commit_range'])))
    elif config['single_commit']:
        commits = [repo.commit(config['single_commit'])]
    else:
        assert False  # This should not happen

    for order_number, commit in enumerate(commits):
        log.info(f"Processing commit '{commit.message.splitlines()[0]}'")
        root = ET.Element('UPDATES', Version=FORMAT_VERSION)
        update = ET.SubElement(root, 'UPDATE')

        log.debug("Getting commit datetime")
        commit_datetime = commit.committed_datetime.astimezone(datetime.timezone.utc)
        log.debug(f"Commit datetime: {commit_datetime}")

        log.debug("Writing commit date")
        ET.SubElement(update, 'DATE', Year=str(commit_datetime.year), Month=str(commit_datetime.month),
                      Day=str(commit_datetime.day))
        log.debug("Writing commit time")
        ET.SubElement(update, 'TIME', Timezone='UTC', Hour=str(commit_datetime.hour),
                      Minute=str(commit_datetime.minute), Second=str(commit_datetime.second))
        log.debug("Writing OS entry")
        ET.SubElement(update, 'OS', Repo=config['repo'], Id=config['os'], Branch=str(repo.active_branch))

        log.debug("Writing commit message")
        text = ET.SubElement(update, 'LOG')
        text.text = commit.message.strip()

        log.debug("Writing author")
        people = ET.SubElement(update, 'PEOPLE')
        ET.SubElement(people, 'UPDATER', Handle=f"{commit.author.name} <{commit.author.email}>")

        log.debug("Writing commit hash")
        ET.SubElement(update, 'COMMIT', Hash=commit.hexsha, EncodingLoses="false", Repository=config['repo'])

        files = ET.SubElement(update, 'FILES')
        log.debug("Writing changes")
        for file_change in commit.parents[0].diff(commit):
            log.debug(f"Writing change: {file_change}")
            if file_change.change_type == 'A':
                ET.SubElement(files, 'FILE', Action='Add', Path=file_change.b_path)
            elif file_change.change_type == 'D':
                ET.SubElement(files, 'FILE', Action='Delete', Path=file_change.a_path)
            elif file_change.change_type == 'R':
                ET.SubElement(files, 'FILE', Action='Rename', Path=file_change.a_path, Destination=file_change.b_path)
            else:  # M and T types
                ET.SubElement(files, 'FILE', Action='Modify', Path=file_change.a_path)

        file_name = (f"{commit_datetime.year}.{commit_datetime.month:02d}.{commit_datetime.day:02d}."
                     f"{commit_datetime.hour:02d}.{commit_datetime.minute:02d}.{commit_datetime.second:02d}."
                     f"{order_number:06d}.{commit.hexsha}.xml")
        file_mode = 'wb' if config['force'] else 'xb'
        log.debug("Dumping XML")
        try:
            with open(Path(config['output'], file_name), file_mode) as out_file:
                out_file.write(ET.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True))
        except FileExistsError as e:
            log.warning(f"{e}, if you want to overwrite it - please specify '--force' flag")
        log.debug("Processing complete")


if __name__ == '__main__':
    main()
