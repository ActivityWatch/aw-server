from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import logging
import requests
from dataclasses import dataclass

from .__about__ import __version__

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    title: str
    description: str
    url: str
    timestamp: datetime = datetime.now()
    icon: str = 'star'


def get_latest_release(include_prereleases=False) -> Dict:
    r = requests.get('https://api.github.com/repos/ActivityWatch/activitywatch/releases')
    releases = r.json()
    if not include_prereleases:
        releases = [release for release in releases if not release['prerelease']]
    return releases[0]


def is_newer_version(version):
    # TODO: Don't notify about beta releases if running a stable release
    return version > __version__


def get_notifications() -> List[Notification]:
    notifs = []

    first_run = True
    if first_run:
        n = Notification(title='Welcome to ActivityWatch!',
                         description='',
                         url='',
                         timestamp=datetime.now())
        notifs.append(n)

    no_browser_extension = True
    if no_browser_extension:
        # TODO: Better link
        n = Notification(title="Looks like you don't have a browser extension reporting data",
                         description='Click here to get one!',
                         url='https://github.com/ActivityWatch/aw-watcher-web')
        notifs.append(n)

    week_old_user = True
    if week_old_user:
        # TODO: Create page that URL links to
        n = Notification(title='Support us!',
                         description='Do you like ActivityWatch and want to help it become even better? Click here to find out about the many ways you can help out!',
                         url='https://activitywatch.net/support-us/')
        notifs.append(n)

    month_old_user = True
    if month_old_user:
        n = Notification(title="You've used ActivityWatch for over a month!",
                         description='Do you use ActivityWatch in your work? Do you look forward to amazing updates? Support us by donating!',
                         url='https://activitywatch.net/donate/')
        notifs.append(n)

    latest_release = get_latest_release(include_prereleases='b' in __version__)
    if is_newer_version(latest_release['tag_name']):
        n = Notification(title=f"There's a newer version available! ({latest_release['tag_name']})",
                         description="Click here to see what's new",
                         url=latest_release['html_url'])
        notifs.append(n)

    return notifs
