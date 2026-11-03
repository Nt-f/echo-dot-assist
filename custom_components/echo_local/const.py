"""Echo Local: the Echo's own alarms in Home Assistant (alarms.c on the Echo)"""
DOMAIN = "echo_local"
CONF_KEY = "key"                        # this integration's X25519 private key, approved on the Echo
CONF_NODE = "node"
CONF_MAC = "mac"
SCAN_INTERVAL_S = 30
CARD_URL = "/echo_local/echo-local-alarms-card.js"
PANEL_PATH = "echo-local"                    # the sidebar panel (frontend/panel.js): /echo-local
PANEL_URL = "/echo_local/panel.js"
WALL_URL = "/echo_local/wall.html"            # the kiosk's wall panel (frontend/wall.html), a page of its own

# days as alarms.h has them: bit d for tm_wday d (0 Sunday .. 6 Saturday)
DAY_KEYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
