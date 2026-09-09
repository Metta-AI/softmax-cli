"""Terminal player card: `softmax card`.

Renders a collectible readout of a player's league standings in the terminal's
own foreground, with no ANSI color: the card is drawn in glyphs alone, so it
reads the same piped to a file, pasted into a doc, or on any theme. Standings
come live from the Observatory portfolio and division leaderboards, one card
per player the user owns; `--demo` renders the built-in sample. Plain Unicode
block elements, so it fits any UTF-8 terminal at 80 columns.

Glyph constraint: never mix shade characters (░▒▓) with block elements (█▀▄)
on one line — terminals draw block elements with built-in full-cell glyphs but
take shades from the font, so their heights differ and the seam shows. Weight
is carried by which block is drawn (█ ▀ ▄ ▐ ▌) and emptiness by the dotted ┈
track, never by a shade.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from pydantic import BaseModel

from softmax._http import observatory_client
from softmax.auth import WhoAmIResponse
from softmax.players import PlayerResponse

# 8-row pixel glyphs, 1 bit = 1 column x half text row. Widths vary per glyph.
FONT_NAME = {
    " ": ["00", "00", "00", "00", "00", "00", "00", "00"],
    "A": ["011110", "111111", "110011", "111111", "111111", "110011", "110011", "110011"],
    "B": ["111110", "111111", "110011", "111110", "111110", "110011", "111111", "111110"],
    "C": ["011111", "111111", "110000", "110000", "110000", "110000", "111111", "011111"],
    "D": ["111110", "111111", "110011", "110011", "110011", "110011", "111111", "111110"],
    "E": ["1111111", "1111111", "1100000", "1111100", "1111100", "1100000", "1111111", "1111111"],
    "F": ["111111", "111111", "110000", "111110", "111110", "110000", "110000", "110000"],
    "G": ["011111", "111111", "110000", "110000", "110111", "110011", "111111", "011111"],
    "H": ["1100011", "1100011", "1100011", "1111111", "1111111", "1100011", "1100011", "1100011"],
    "I": ["111111", "111111", "001100", "001100", "001100", "001100", "111111", "111111"],
    "J": ["111111", "111111", "000011", "000011", "000011", "110011", "111111", "011110"],
    "K": ["110011", "110110", "111100", "111000", "111100", "110110", "110011", "110011"],
    "L": ["110000", "110000", "110000", "110000", "110000", "110000", "111111", "111111"],
    "M": ["11000011", "11100111", "11111111", "11011011", "11000011", "11000011", "11000011", "11000011"],
    "N": ["1100011", "1110011", "1111011", "1101111", "1100111", "1100011", "1100011", "1100011"],
    "O": ["0111110", "1111111", "1100011", "1100011", "1100011", "1100011", "1111111", "0111110"],
    "P": ["111110", "111111", "110011", "110011", "111111", "111110", "110000", "110000"],
    "Q": ["0111110", "1111111", "1100011", "1100011", "1101011", "1100111", "1111111", "0111111"],
    "R": ["111110", "111111", "110011", "110011", "111111", "111110", "110110", "110011"],
    "S": ["011111", "111111", "110000", "111110", "011111", "000011", "111111", "111110"],
    "T": ["111111", "111111", "001100", "001100", "001100", "001100", "001100", "001100"],
    "U": ["110011", "110011", "110011", "110011", "110011", "110011", "111111", "011110"],
    "V": ["110011", "110011", "110011", "110011", "110011", "011110", "011110", "001100"],
    "W": ["11000011", "11000011", "11000011", "11011011", "11011011", "11111111", "11100111", "11000011"],
    "X": ["110011", "110011", "011110", "001100", "001100", "011110", "110011", "110011"],
    "Y": ["110011", "110011", "110011", "011110", "001100", "001100", "001100", "001100"],
    "Z": ["111111", "111111", "000110", "001100", "011000", "110000", "111111", "111111"],
    "0": ["011110", "111111", "110011", "110011", "110011", "110011", "111111", "011110"],
    "1": ["001100", "011100", "111100", "001100", "001100", "001100", "111111", "111111"],
    "2": ["011110", "111111", "110011", "000110", "001100", "011000", "111111", "111111"],
    "3": ["111110", "111111", "000011", "011110", "011110", "000011", "111111", "111110"],
    "4": ["110011", "110011", "110011", "111111", "011111", "000011", "000011", "000011"],
    "5": ["111111", "111111", "110000", "111110", "000011", "000011", "111111", "111110"],
    "6": ["011110", "111111", "110000", "111110", "110011", "110011", "111111", "011110"],
    "7": ["111111", "111111", "000011", "000110", "001100", "001100", "001100", "001100"],
    "8": ["011110", "111111", "110011", "011110", "011110", "110011", "111111", "011110"],
    "9": ["011110", "111111", "110011", "110011", "011111", "000011", "111111", "011110"],
    ".": ["00", "00", "00", "00", "00", "00", "11", "11"],
    "-": ["00000", "00000", "00000", "11111", "11111", "00000", "00000", "00000"],
    "_": ["00000", "00000", "00000", "00000", "00000", "00000", "11111", "11111"],
    "'": ["11", "11", "00", "00", "00", "00", "00", "00"],
    ",": ["00", "00", "00", "00", "00", "11", "11", "10"],
    "!": ["11", "11", "11", "11", "11", "00", "11", "11"],
    "?": ["011110", "111111", "110011", "000110", "001100", "000000", "001100", "001100"],
    "+": ["000000", "001100", "001100", "111111", "111111", "001100", "001100", "000000"],
    ":": ["00", "00", "11", "11", "00", "00", "11", "11"],
}

# Condensed cut of the same face: 2px strokes kept, counters squeezed to 1px,
# letter gap 1 instead of 2. The hero drops to it when the regular wordmark
# overflows the content area (~11 letters fit vs ~8). V/X/Y and + reuse the
# regular forms: diagonals and a centered 2px cross cannot lose a column
# without breaking the stroke weight.
FONT_NAME_CONDENSED = {
    " ": ["00", "00", "00", "00", "00", "00", "00", "00"],
    "A": ["01110", "11111", "11011", "11111", "11111", "11011", "11011", "11011"],
    "B": ["11110", "11111", "11011", "11110", "11110", "11011", "11111", "11110"],
    "C": ["01111", "11111", "11000", "11000", "11000", "11000", "11111", "01111"],
    "D": ["11110", "11111", "11011", "11011", "11011", "11011", "11111", "11110"],
    "E": ["11111", "11111", "11000", "11110", "11110", "11000", "11111", "11111"],
    "F": ["11111", "11111", "11000", "11110", "11110", "11000", "11000", "11000"],
    "G": ["01111", "11111", "11000", "11000", "11011", "11011", "11111", "01111"],
    "H": ["11011", "11011", "11011", "11111", "11111", "11011", "11011", "11011"],
    "I": ["1111", "1111", "0110", "0110", "0110", "0110", "1111", "1111"],
    "J": ["11111", "11111", "00011", "00011", "00011", "11011", "11111", "01110"],
    "K": ["11011", "11110", "11100", "11100", "11110", "11011", "11011", "11011"],
    "L": ["11000", "11000", "11000", "11000", "11000", "11000", "11111", "11111"],
    "M": ["1100011", "1110111", "1111111", "1101011", "1100011", "1100011", "1100011", "1100011"],
    "N": ["110011", "111011", "111111", "110111", "110011", "110011", "110011", "110011"],
    "O": ["01110", "11111", "11011", "11011", "11011", "11011", "11111", "01110"],
    "P": ["11110", "11111", "11011", "11011", "11111", "11110", "11000", "11000"],
    "Q": ["01110", "11111", "11011", "11011", "11011", "11011", "11111", "01111"],
    "R": ["11110", "11111", "11011", "11011", "11111", "11110", "11011", "11011"],
    "S": ["01111", "11111", "11000", "11110", "01111", "00011", "11111", "11110"],
    "T": ["1111", "1111", "0110", "0110", "0110", "0110", "0110", "0110"],
    "U": ["11011", "11011", "11011", "11011", "11011", "11011", "11111", "01110"],
    "V": FONT_NAME["V"],
    "W": ["1100011", "1100011", "1100011", "1100011", "1101011", "1111111", "1110111", "1100011"],
    "X": FONT_NAME["X"],
    "Y": FONT_NAME["Y"],
    "Z": ["11111", "11111", "00110", "01100", "01100", "11000", "11111", "11111"],
    "0": ["01110", "11111", "11011", "11011", "11011", "11011", "11111", "01110"],
    "1": ["0110", "1110", "0110", "0110", "0110", "0110", "1111", "1111"],
    "2": ["11110", "11111", "00011", "00110", "01100", "11000", "11111", "11111"],
    "3": ["11110", "11111", "00011", "01110", "01110", "00011", "11111", "11110"],
    "4": ["11011", "11011", "11011", "11111", "01111", "00011", "00011", "00011"],
    "5": ["11111", "11111", "11000", "11110", "00011", "00011", "11111", "11110"],
    "6": ["01111", "11111", "11000", "11110", "11011", "11011", "11111", "01110"],
    "7": ["11111", "11111", "00011", "00110", "00110", "01100", "01100", "01100"],
    "8": ["01110", "11111", "11011", "01110", "01110", "11011", "11111", "01110"],
    "9": ["01110", "11111", "11011", "11011", "01111", "00011", "11111", "11110"],
    ".": ["00", "00", "00", "00", "00", "00", "11", "11"],
    "-": ["0000", "0000", "0000", "1111", "1111", "0000", "0000", "0000"],
    "_": ["0000", "0000", "0000", "0000", "0000", "0000", "1111", "1111"],
    "'": ["11", "11", "00", "00", "00", "00", "00", "00"],
    ",": ["00", "00", "00", "00", "00", "11", "11", "10"],
    "!": ["11", "11", "11", "11", "11", "00", "11", "11"],
    "?": ["11110", "11111", "00011", "00110", "01100", "00000", "01100", "01100"],
    "+": FONT_NAME["+"],
    ":": ["00", "00", "11", "11", "00", "00", "11", "11"],
}
SUPPORTED_NAME_CHARS = frozenset(FONT_NAME)


def _rasterize(text: str, font: dict[str, list[str]], gap: int = 2) -> list[str]:
    lines = ["" for _ in range(8)]
    for i, ch in enumerate(text):
        glyph = font[ch]
        for r in range(8):
            lines[r] += ("0" * gap if i else "") + glyph[r]
    return lines


class GameRow(BaseModel):
    name: str
    policy: str
    rank: int
    total: int
    mmr: str  # preformatted by `_mmr`; `n/a` where the division does not rank by rating
    rounds: int


class PlayerCard(BaseModel):
    title: str = "SOFTMAX CARD"
    name: str  # the player's name as typed; the hero derives its wordmark from it
    creators: str  # the human&agent pair, e.g. "Rob & coding-agent"
    games: list[GameRow]
    joined: str
    leagues: int


# The `--demo` sample, also the render fixture in tests. Every game, policy,
# and stat is invented, so it can never go stale against production; live
# cards are always built from the server by `fetch_player_cards`, and nothing
# here feeds that path. Two rows sit in divisions that rank by something
# other than rating, so they preview the `n/a` state.
DEMO_CARD = PlayerCard(
    name="Echo",
    creators="Rob & coding-agent",
    joined="January 2024",
    leagues=89,
    games=[
        GameRow(name="Endless Attic", policy="stacker:v7", rank=1, total=4, mmr="1151", rounds=96),
        GameRow(name="Hopscotch", policy="dalli:v1", rank=1, total=7, mmr="1173", rounds=84),
        GameRow(name="Terravore", policy="mulch:v268", rank=1, total=15, mmr="1284", rounds=421),
        GameRow(name="Fogline", policy="kutuzov:v98", rank=2, total=30, mmr="1236", rounds=152),
        GameRow(name="Comet Claim", policy="comet-skurge:v9", rank=4, total=6, mmr="n/a", rounds=18),
        GameRow(name="Slugfest", policy="sleepy piston:v1", rank=4, total=5, mmr="n/a", rounds=20),
        GameRow(name="Persistent Yes", policy="yeswalker:v82", rank=5, total=8, mmr="1032", rounds=45),
        GameRow(name="Thornmaze", policy="coolbot:v15", rank=5, total=15, mmr="1095", rounds=60),
        GameRow(name="Mudlark", policy="mudcrew:v21", rank=10, total=18, mmr="1069", rounds=73),
        GameRow(name="Last Lightbulb", policy="stierlitz:v1", rank=11, total=21, mmr="1044", rounds=51),
        GameRow(name="Splattergrid", policy="wideshot:v372", rank=11, total=43, mmr="1121", rounds=132),
        GameRow(name="Gears vs Geese", policy="dinky:v46", rank=12, total=20, mmr="1007", rounds=40),
        GameRow(name="Mudlark Prime", policy="notsus:v272", rank=12, total=20, mmr="1003", rounds=58),
        GameRow(name="Elite Splatter", policy="wideshot:v383", rank=29, total=43, mmr="962", rounds=64),
    ],
)


# Wire models: the subset of the Observatory responses the card consumes.
# Identity endpoints reuse the CLI's own models (`WhoAmIResponse`,
# `PlayerResponse`); only the league surfaces need local ones.
class _Seat(BaseModel):
    player_id: str
    league_id: str
    game_name: str
    division_id: str
    policy_label: str  # server-rendered "name:vN", the same label the web shows
    status: str
    substatus: str | None = None

    @property
    def is_active(self) -> bool:
        """Actively playing, the same gate the backend's round scheduler uses.

        The portfolio only returns live seats, but live includes states that are
        not playing: still qualifying, benched, crashed, or held."""
        return self.status == "competing" and self.substatus == "active"


class _BoardRow(BaseModel):
    rank: int
    player_id: str
    score: float
    score_label: str  # what this division ranks by, e.g. "MMR", "Win %", "tiles"
    rounds_played: int


class _League(BaseModel):
    id: str
    # Set while a team member has paused the league's round runner: the league
    # stays visible but its games are not currently running.
    rounds_paused_at: str | None


def wordmark(name: str) -> str:
    """Uppercase a player name and drop characters the pixel font lacks."""
    mark = " ".join("".join(c for c in name.upper() if c in SUPPORTED_NAME_CHARS).split())
    return mark or "PLAYER"


def fetch_player_cards(
    api_server: str,
    token: str,
    transport: httpx.BaseTransport | None = None,
    on_stage: Callable[[str], None] = lambda _: None,
) -> list[PlayerCard]:
    """One card per player owned by the token's user, default player first.

    Two sweeps: the league-policy-membership portfolio enumerates every live
    (player, division) seat, kept only while actively competing in a league
    whose rounds are running, then the kept divisions' published leaderboards
    are fetched concurrently for rank, rating, and rounds played. What a
    division ranks by is the coworld's choice, so a board ranked by anything
    other than the ladder rating reads `n/a` rather than printing a number
    the `mmr` column would misname.
    Seats whose division has no published board row for the player yet are
    left off the card. A player with no standings at all is dropped while any
    sibling player has some; only when nobody has standings does every player
    still get a card. `on_stage` hears a short human-readable line as each
    fetch phase starts (the CLI loader shows it).
    """
    with observatory_client(server=api_server, token=token, timeout=30.0, transport=transport) as http:
        on_stage("finding your players")
        owner = WhoAmIResponse.model_validate(http.get("/whoami").raise_for_status().json())
        players = [PlayerResponse.model_validate(p) for p in http.get("/players").raise_for_status().json()]
        on_stage("scanning the leagues")
        leagues = [_League.model_validate(item) for item in http.get("/v2/leagues").raise_for_status().json()]
        paused = {league.id for league in leagues if league.rounds_paused_at is not None}
        on_stage("collecting your seats")
        portfolio = http.get("/v2/league-policy-memberships/portfolio", params={"limit": 1000})
        seats = [
            s
            for s in map(_Seat.model_validate, portfolio.raise_for_status().json())
            if s.is_active and s.league_id not in paused
        ]
        boards: dict[str, list[_BoardRow]] = {}
        divisions = sorted({s.division_id for s in seats})
        if divisions:
            # One GET per division and big portfolios span dozens, so they go
            # out concurrently (httpx.Client is thread-safe); each response is
            # checked and validated on the main thread as it lands.
            on_stage(f"reading standings 0/{len(divisions)}")
            with ThreadPoolExecutor(max_workers=min(8, len(divisions))) as pool:
                futures = {
                    pool.submit(http.get, f"/v2/divisions/{d}/leaderboard", params={"include_recent_rounds": False}): d
                    for d in divisions
                }
                for done, future in enumerate(as_completed(futures), start=1):
                    rows = future.result().raise_for_status().json() or []
                    boards[futures[future]] = [_BoardRow.model_validate(r) for r in rows]
                    on_stage(f"reading standings {done}/{len(divisions)}")

    cards = []
    owner_name = owner.name or owner.user_email.split("@")[0]  # email nick when the account has no name
    for player in players:  # /players orders default first, then newest
        mine = [s for s in seats if s.player_id == player.id]
        games = []
        for seat in mine:
            board = boards[seat.division_id]
            row = next((r for r in board if r.player_id == player.id), None)
            if row is None:
                continue
            games.append(
                GameRow(
                    name=seat.game_name,
                    policy=seat.policy_label,
                    rank=row.rank,
                    total=len(board),
                    mmr=_mmr(row.score, row.score_label),
                    rounds=row.rounds_played,
                )
            )
        games.sort(key=lambda g: (g.rank, g.name.lower()))
        cards.append(
            PlayerCard(
                name=player.name,
                creators=f"{owner_name} & coding-agent",
                joined=f"{player.created_at:%B %Y}",
                leagues=len({s.league_id for s in mine}),
                games=games,
            )
        )
    return [c for c in cards if c.games] or cards


INNER = 66  # content columns between the padded borders
PAD = 2  # spaces inside the border

# Standings columns. Field widths include each column's alignment padding;
# game and policy names clip one short of their fields so columns never touch.
GAME_W = 17
POLICY_W = 16
ROUNDS_W = 6
MMR_W = 5
GAP = "  "  # between the numeric columns
RANK_GAP = " "  # rank to its bar: tight, so the two read as one column
# Rank and its bar share the rest of the row as one column. The bar is capped
# at BAR_W and the rank field takes the rest, so a thousand-seat board grows
# its numbers into that slack instead of breaking the frame; only a board too
# wide for even that slack shortens the bar.
BAR_W = 12
STANDING_W = INNER - (GAME_W + POLICY_W + ROUNDS_W + MMR_W + 2 * len(GAP))


def _framed(text: str) -> str:
    """One card line: content padded or clipped to exactly INNER columns, so
    nothing can push the frame out of true."""
    return "╎" + " " * PAD + f"{text[:INNER]:<{INNER}}" + " " * PAD + "╎"


def _blank() -> str:
    return _framed("")


def _rule(edge_l: str, edge_r: str, label: str | None = None) -> str:
    width = INNER + 2 * PAD
    if not label:
        return edge_l + "─" * width + edge_r
    dashes = width - len(label) - 2
    left = dashes // 2
    return edge_l + "─" * left + f" {label} " + "─" * (dashes - left) + edge_r


def _strip_line() -> str:
    """The holographic band. Half blocks at each end let it stop half a cell
    short of the padding, so the band tapers instead of butting the frame."""
    return _framed("▐" + "█" * (INNER - 2) + "▌")


def _hero_lines(card: PlayerCard) -> list[str]:
    """Big pixel name composed with half-blocks. Names wider than the content
    area drop to the condensed face; names wider than even that clip at the
    right edge."""
    mark = wordmark(card.name)
    name_px = _rasterize(mark, FONT_NAME)
    if len(name_px[0]) > INNER:
        name_px = _rasterize(mark, FONT_NAME_CONDENSED, gap=1)

    grid = [[0] * INNER for _ in range(8)]
    for r in range(8):
        for c, bit in enumerate(name_px[r][:INNER]):
            if bit == "1":
                grid[r][c] = 1

    lines = []
    for tr in range(4):
        row = ""
        for col in range(INNER):
            top, bot = grid[2 * tr][col], grid[2 * tr + 1][col]
            row += "█" if top and bot else "▀" if top else "▄" if bot else " "
        lines.append(_framed(row))
    return lines


def _pctile(rank: int, total: int) -> int:
    """Share of the board this rank sits above; the standings bar's fill."""
    return round((total - rank) / (total - 1) * 100) if total > 1 else 100


def _fit(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _num(n: int, width: int) -> str:
    """Right-align n in exactly width columns, abbreviating when it cannot fit
    (3497970 in 4 columns becomes 3.5M) so stat columns never shift the frame."""
    if len(str(n)) <= width:
        return f"{n:>{width}}"
    for div, unit in ((1_000, "k"), (1_000_000, "M"), (1_000_000_000, "B")):
        for text in (f"{n / div:.1f}{unit}", f"{round(n / div)}{unit}"):
            if len(text) <= width:
                return f"{text:>{width}}"
    return str(n)[:width]


# The platform ladder publishes its rating column as "MMR"; boards snapshotted
# before that wire rename still say "Elo" for the same number, and app_backend's
# `published_board_is_platform_mmr` reads both labels as one rating.
MMR_LABELS = ("MMR", "Elo")


def _mmr(score: float, score_label: str) -> str:
    """The row's matchmaking rating, or `n/a` on a board ranked by something
    else. Each coworld picks what its division ranks by (win rate, tiles held,
    its own score) and only the ladder rating is an MMR, so every other
    headline column reads as no rating rather than as a wrong one."""
    if score_label not in MMR_LABELS:
        return "n/a"
    return _num(round(score), MMR_W).strip()


def _rank_field(rank: int, total: int) -> str:
    """`1/09`: rank as written, board size zero-padded to at least two digits so
    the two halves stay distinct at a glance."""
    return f"{rank}/{total:0{max(2, len(str(total)))}d}"


def _bar_w(games: list[GameRow]) -> int:
    """The bar's width. It stops at BAR_W so the rank and its bar read as one
    group rather than a stripe across the card; a board whose rank fields are
    wider than the slack takes the difference back out of the bar."""
    widest = max((len(_rank_field(g.rank, g.total)) for g in games), default=5)
    return min(BAR_W, STANDING_W - widest - len(RANK_GAP))


def _header(games: list[GameRow]) -> str:
    """Column labels. `game` runs with its names; the rest are centered over
    their fields, and `rank` straddles the seam between the rank numbers and
    their bar, because the label names both."""
    seam = STANDING_W - _bar_w(games)
    return (
        f"{'game':<{GAME_W}}{'policy':^{POLICY_W}}{'rounds':^{ROUNDS_W}}{GAP}"
        f"{'mmr':^{MMR_W}}{GAP}{'rank':>{seam + len('rank') // 2}}"
    )


def _game_rows(card: PlayerCard) -> list[str]:
    if not card.games:
        return [_framed("no league standings yet")]
    bar_w = _bar_w(card.games)
    rank_w = STANDING_W - bar_w - len(RANK_GAP)
    rows = []
    for g in card.games:
        fill = round(_pctile(g.rank, g.total) / 100 * bar_w)
        rows.append(
            _framed(
                f"{_fit(g.name, GAME_W - 1):<{GAME_W}}"
                f"{_fit(g.policy, POLICY_W - 1):<{POLICY_W}}"
                f"{_num(g.rounds, ROUNDS_W)}{GAP}"
                f"{g.mmr:>{MMR_W}}{GAP}"
                f"{_rank_field(g.rank, g.total):>{rank_w}}{RANK_GAP}"
                f"{'█' * fill}{'┈' * (bar_w - fill)}"
            )
        )
    return rows


def build_lines(card: PlayerCard) -> list[str]:
    total_rounds = sum(g.rounds for g in card.games)
    footer = f"Joined {card.joined} ∙ {card.leagues} leagues ∙ {total_rounds} rounds"
    return [
        _rule("┌", "┐", card.title),
        _blank(),
        _strip_line(),
        _blank(),
        *_hero_lines(card),
        _blank(),
        _framed("Player: " + _fit(card.name, INNER - len("Player: "))),
        _framed("Creators: " + _fit(card.creators, INNER - len("Creators: "))),
        _blank(),
        _strip_line(),
        _blank(),
        _framed(_header(card.games)),
        _framed("┈" * INNER),
        *_game_rows(card),
        _blank(),
        _framed(_fit(footer, INNER)),
        _blank(),
        _rule("└", "┘"),
    ]


def render(card: PlayerCard) -> str:
    """The card as printable text, indented off the left edge of the terminal."""
    return "\n".join("  " + line for line in build_lines(card))
