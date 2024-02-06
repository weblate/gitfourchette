import dataclasses
import urllib
import re
from contextlib import suppress

HTTPS_PORT = 443

REMOTE_URL_PATTERNS = [
    # HTTP/HTTPS
    # http://example.com/user/repo
    # https://example.com/user/repo
    re.compile(r"^https?:\/\/(?P<host>[^\/]+?)\/(?P<path>.+)"),

    # SSH (scp-like syntax)
    # example.com:user/repo
    # git@example.com:user/repo
    re.compile(r"^(\w+?@)?(?P<host>[^\/]+?):(?!\/)(?P<path>.+)"),

    # SSH (full syntax)
    # ssh://example.com/user/repo
    # ssh://git@example.com/user/repo
    # ssh://git@example.com:1234/user/repo
    re.compile(r"^ssh:\/\/(\w+?@)?(?P<host>[^\/]+?)(:\d+)?\/(?P<path>.+)"),

    # Git protocol
    # git://example.com/user/repo
    # git://example.com:1234/user/repo
    re.compile(r"^git:\/\/(?P<host>[^\/]+?)(:\d+)?\/(?P<path>.+)"),
]


@dataclasses.dataclass
class WebHost:
    name: str
    branchPrefix: str
    port: int = HTTPS_PORT

    @staticmethod
    def splitRemoteUrl(url: str):
        for pattern in REMOTE_URL_PATTERNS:
            m = pattern.match(url)
            if m:
                host = m.group("host")
                path = m.group("path")
                return host, path
        return "", ""

    @staticmethod
    def makeLink(remoteUrl: str, branch: str = ""):
        host, path = WebHost.splitRemoteUrl(remoteUrl)

        if not host:
            return "", ""

        path = path.removesuffix(".git")

        try:
            hostInfo = WEB_HOSTS[host]
            hostName = hostInfo.name
        except KeyError:
            hostInfo = WEB_HOSTS["github.com"]  # fall back to GitHub's scheme
            hostName = host

        port = "" if hostInfo.port == HTTPS_PORT else f":{hostInfo.port}"
        suffix = ""

        if branch:
            suffix = hostInfo.branchPrefix + urllib.parse.quote(branch, safe='/')

        return f"https://{host}{port}/{path}{suffix}", hostName


WEB_HOSTS = {
    "github.com": WebHost("GitHub", "/tree/"),
    "gitlab.com": WebHost("GitLab", "/-/tree/"),
    "git.sr.ht": WebHost("Sourcehut", "/tree/"),
    "codeberg.org": WebHost("Codeberg", "/src/branch/"),
    "git.launchpad.net": WebHost("Launchpad", "/log?h="),
    "bitbucket.org": WebHost("Bitbucket", "/src/"),
}
