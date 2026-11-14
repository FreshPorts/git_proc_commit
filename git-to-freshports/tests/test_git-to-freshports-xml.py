import pytest
import pygit2
import sys
from unittest.mock import patch, Mock
from tempfile import TemporaryDirectory
from pathlib import Path


MODULE_UNDER_TEST = __import__('git-to-freshports-xml')


@pytest.fixture(scope='module')
def git_repo() -> pygit2.Repository:

    with TemporaryDirectory() as repo_dir:
        repo_dir = Path(repo_dir)
        repo = pygit2.init_repository(repo_dir, flags=0)

        author = pygit2.Signature('Alice Author', 'alice@authors.tld')
        committer = pygit2.Signature('Cecil Committer', 'cecil@committers.tld')
        parent = None

        for f in ('1.txt', '2.txt', '3.txt', '4.txt', '5.txt'):
            (repo_dir / f).open('wb').close()
            repo.index.add_all()
            repo.index.write()
            tree = repo.index.write_tree()
            parents = [parent] if parent else []
            # 'HEAD', not 'refs/heads/master': the first commit creates the
            # branch HEAD names, which depends on init.defaultBranch, so
            # HEAD~ below always finds these commits
            parent = repo.create_commit(
                'HEAD',
                author,
                committer,
                f"Create {f}",
                tree,
                parents
            )

        yield repo


@pytest.fixture(autouse=True)
def disable_logger(monkeypatch):
    monkeypatch.setattr(MODULE_UNDER_TEST, 'configure_logging', Mock())


def hash_of(commit) -> str:
    # commit.hex went away in pygit2 1.15; str(commit.id) is the same text
    return str(commit.id)


def run(git_repo: pygit2.Repository, tmp_path: Path, *selection) -> list:
    """Run the script with --branch=main and return the XML files it wrote, in name order.

    --branch is given because without it the script looks for a remote
    branch holding the commit, and this repo has no remote, so it wrote
    nothing.  The files are sorted because iterdir() promises no order.
    """
    call_args = ['git-to-freshports-xml',
                 f'--path={git_repo.workdir}',
                 *selection,
                 '--branch=main',
                 f'--output={tmp_path}',
                 f'--spooling={tmp_path}',
                 '--repo=ports']

    with patch.object(sys, 'argv', call_args):
        MODULE_UNDER_TEST.main()

    return sorted(tmp_path.iterdir())


def test_single_commit(git_repo: pygit2.Repository, tmp_path: Path):
    commit = git_repo.revparse_single('HEAD~')

    result_files = run(git_repo, tmp_path, f'--single-commit={hash_of(commit)}')
    assert len(result_files) == 1, "Must be exactly one commit"

    commit_filename = result_files[0].name
    assert hash_of(commit) in commit_filename


def test_commit_range(git_repo: pygit2.Repository, tmp_path: Path):
    first_commit = git_repo.revparse_single('HEAD~3')
    second_commit = git_repo.revparse_single('HEAD~1')

    result_files = run(git_repo, tmp_path, f'--commit-range={hash_of(first_commit)}..{hash_of(second_commit)}')
    assert len(result_files) == 2, "Must be exactly two commits"

    commit_filenames = [x.name for x in result_files]
    assert hash_of(git_repo.revparse_single('HEAD~2')) in commit_filenames[0]
    assert hash_of(second_commit) in commit_filenames[1]


def test_commit_to_head(git_repo: pygit2.Repository, tmp_path: Path):
    commit = git_repo.revparse_single('HEAD~3')

    result_files = run(git_repo, tmp_path, f'--commit={hash_of(commit)}')
    assert len(result_files) == 3, "Must be exactly three commits"
    assert hash_of(git_repo.revparse_single('HEAD~2')) in result_files[0].name


def test_range_not_on_the_line_is_refused(git_repo: pygit2.Repository, tmp_path: Path):
    # FROM and TO swapped: the start is not on the end's first-parent line
    newer = git_repo.revparse_single('HEAD~1')
    older = git_repo.revparse_single('HEAD~3')

    with pytest.raises(SystemExit) as exit_info:
        run(git_repo, tmp_path, f'--commit-range={hash_of(newer)}..{hash_of(older)}')
    assert exit_info.value.code == 1
    assert list(tmp_path.iterdir()) == [], "Nothing may be written for a refused range"
