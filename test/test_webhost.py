# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import pytest

from gitfourchette.webhost import WebHost

EXAMPLE_REMOTE_URLS = [
    "https://example.com/user/repo",
    "https://personal!access_token-1234@example.com/user/repo",
    "example.com:user/repo",
    "example.com:user/repo.git",
    "git@example.com:user/repo",
    "git@example.com:user/repo.git",
    "git!1234@example.com:user/repo",
    "ssh://example.com/user/repo",
    "ssh://git@example.com/user/repo",
    "ssh://git@example.com:1234/user/repo",
    "ssh://git_1234@example.com:1234/user/repo",
    "ssh://git!1234@example.com:1234/user/repo",
    "git://example.com/user/repo",
    "git://example.com:1234/user/repo",
]


@pytest.mark.parametrize("exampleUrl", EXAMPLE_REMOTE_URLS)
def testWebHostRegexes(exampleUrl):
    remoteUrl = exampleUrl
    web, host = WebHost.makeLink(remoteUrl)
    assert host == "example.com"
    assert web == "https://example.com/user/repo"

    # Test fallback branch URL
    web, host = WebHost.makeLink(remoteUrl, "branch")
    assert host == "example.com"
    assert web == "https://example.com/user/repo/tree/branch"

    # Test a couple predefined hosts
    remoteUrl = exampleUrl.replace("example.com", "github.com")
    web, host = WebHost.makeLink(remoteUrl, "branch")
    assert host == "GitHub"
    assert web == "https://github.com/user/repo/tree/branch"

    remoteUrl = exampleUrl.replace("example.com", "codeberg.org")
    web, host = WebHost.makeLink(remoteUrl, "branch")
    assert host == "Codeberg"
    assert web == "https://codeberg.org/user/repo/src/branch/branch"
