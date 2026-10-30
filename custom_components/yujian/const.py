"""Constants for the 玉简 integration."""

DOMAIN = "yujian"

# mDNS service types broadcast by the TV app.
#
# The app currently announces ``_tvnotify._tcp.local.``; the type was renamed
# to ``_yujian._tcp.local.`` afterwards. Both are listened for so the
# integration works with every app version out there.
ZEROCONF_TYPES = ("_yujian._tcp.local.", "_tvnotify._tcp.local.")

# TXT record keys broadcast by the TV app.
TXT_VERSION = "version"
TXT_PATH = "path"
TXT_TOKEN = "token"
TXT_MODEL = "model"

# Default HTTP port of the TV app's notification server.
DEFAULT_PORT = 8791

# Path appended to the token to build the notify endpoint: /{token}/notify
NOTIFY_PATH_TEMPLATE = "/{token}/notify"

# Path of the token-less health probe: GET /health
HEALTH_PATH = "/health"

# Path of the token-protected dismiss endpoint: POST /{token}/dismiss
DISMISS_PATH_TEMPLATE = "/{token}/dismiss"

# Android package / component of the app on the TV, used to revive it via
# ADB. These belong to the installed app and must not be renamed here.
TV_PACKAGE = "com.zqc.tvnotify"
TV_SERVICE = "com.zqc.tvnotify/.NotifyService"

# Seconds to wait after reviving the service before retrying the HTTP call.
REVIVE_DELAY_SEC = 2.0

# Default banner duration in seconds.
DEFAULT_DURATION = 5

# Chinese display name shown for the integration, its config entry, the
# device and the notify entity.
DISPLAY_NAME = "玉简"

# Names used by earlier versions for the same thing. Entries created by those
# versions stored one of these, and they are shown as DISPLAY_NAME instead so
# existing installs get the current name without a data migration.
LEGACY_NAMES = ("TVNotify", "电视通知")

# Banner duration bounds accepted by the TV app.
MIN_DURATION = 1
MAX_DURATION = 30

# Bounds of the sticky fallback duration (``maxDuration``) accepted by the
# TV app: how long a sticky banner may stay up at most.
MIN_MAX_DURATION = 30
MAX_MAX_DURATION = 3600
