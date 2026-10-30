"""Command policy: the security choke point."""

from __future__ import annotations

import os

import pytest

from lightpanel.domain.errors import CommandRejectedError
from lightpanel.services.command_policy import CommandPolicy


@pytest.fixture
def policy() -> CommandPolicy:
    return CommandPolicy(allowed_binaries=("docker",), default_timeout=30.0, max_timeout=600.0)


def test_allow_listed_binary_passes(policy):
    assert policy.validate_argv(["docker", "ps"]) == ("docker", "ps")


def test_binary_outside_allow_list_is_rejected(policy):
    with pytest.raises(CommandRejectedError):
        policy.validate_argv(["rm", "-rf", "/"])


def test_absolute_path_is_matched_by_basename(policy):
    assert policy.validate_argv(["/usr/bin/docker", "ps"])[0] == "/usr/bin/docker"


def test_interpreters_are_rejected_as_entrypoint(policy):
    # Only argv[0] is checked: `docker exec <c> sh -c ...` is a legitimate use.
    with pytest.raises(CommandRejectedError):
        policy.validate_argv(["sh", "-c", "echo hi"])
    assert policy.validate_argv(["docker", "exec", "web", "sh", "-c", "echo hi"])[0] == "docker"


def test_shell_metacharacters_are_rejected(policy):
    for token in ("a;rm", "a|b", "a&&b", "$(id)", "`id`", "a>b", "a<b", "a\nb"):
        with pytest.raises(CommandRejectedError):
            policy.validate_argv(["docker", token])


def test_empty_argv_is_rejected(policy):
    with pytest.raises(CommandRejectedError):
        policy.validate_argv([])


def test_empty_argument_is_rejected(policy):
    with pytest.raises(CommandRejectedError):
        policy.validate_argv(["docker", "   "])


def test_timeout_clamped_to_maximum(policy):
    assert policy.resolve_timeout(None) == 30.0
    assert policy.resolve_timeout(10_000) == 600.0


def test_negative_timeout_rejected(policy):
    with pytest.raises(CommandRejectedError):
        policy.resolve_timeout(-1)


def test_cwd_must_be_absolute_and_exist(policy, tmp_path):
    assert policy.validate_cwd(str(tmp_path)) == str(tmp_path)
    assert policy.validate_cwd(None) is None
    with pytest.raises(CommandRejectedError):
        policy.validate_cwd("relative/path")
    with pytest.raises(CommandRejectedError):
        policy.validate_cwd(os.path.join(str(tmp_path), "missing"))


def test_ad_hoc_can_be_disabled():
    policy = CommandPolicy(allow_ad_hoc_argv=False)
    with pytest.raises(CommandRejectedError):
        policy.ensure_ad_hoc_allowed()


def test_open_allow_list_accepts_anything():
    policy = CommandPolicy(allowed_binaries=())
    assert policy.validate_argv(["/bin/true"])[0] == "/bin/true"
