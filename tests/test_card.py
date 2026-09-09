"""Tests for `softmax card`: standings fetch mapping and render invariants."""

import httpx

from softmax import card

PLAYERS = [
    {"id": "ply_a", "name": "Pawel Sysiak", "is_default": True, "created_at": "2025-03-05T12:00:00Z"},
    {"id": "ply_b", "name": "Ralph 2.0", "is_default": False, "created_at": "2025-06-01T08:00:00Z"},
]
PORTFOLIO = [
    {
        "player_id": "ply_a",
        "league_id": "lg_1",
        "game_name": "Agricogla",
        "division_id": "div_1",
        "policy_label": "terra:v7",
        "status": "competing",
        "substatus": "active",
    },
    {
        "player_id": "ply_a",
        "league_id": "lg_2",
        "game_name": "A Very Long Game Name Indeed",
        "division_id": "div_2",
        "policy_label": "longshot:v1",
        "status": "competing",
        "substatus": "active",
    },
    {
        # Live but crashed: on the leaderboard, yet not actively playing, so the
        # card must leave it (and its league) off entirely.
        "player_id": "ply_a",
        "league_id": "lg_3",
        "game_name": "Muster",
        "division_id": "div_3",
        "policy_label": "ilya:v1",
        "status": "competing",
        "substatus": "crash",
    },
    {
        # Actively competing, but its league's rounds are paused: the game is
        # not currently running, so the card must leave it off too.
        "player_id": "ply_a",
        "league_id": "lg_4",
        "game_name": "Nightshift",
        "division_id": "div_4",
        "policy_label": "nochnitsa:v2",
        "status": "competing",
        "substatus": "active",
    },
    {
        "player_id": "ply_b",
        "league_id": "lg_1",
        "game_name": "Agricogla",
        "division_id": "div_1",
        "policy_label": "ralphbot:v3",
        "status": "competing",
        "substatus": "active",
    },
]
LEAGUES = [
    {"id": "lg_1", "rounds_paused_at": None},
    {"id": "lg_2", "rounds_paused_at": None},
    {"id": "lg_3", "rounds_paused_at": None},
    {"id": "lg_4", "rounds_paused_at": "2026-09-01T00:00:00Z"},  # rounds paused: not currently running
]
BOARDS = {
    "div_1": [
        {"rank": 1, "player_id": "ply_b", "score": 1300.0, "score_label": "MMR", "rounds_played": 50},
        {"rank": 2, "player_id": "ply_a", "score": 1234.6, "score_label": "MMR", "rounds_played": 40},
        {"rank": 3, "player_id": "ply_c", "score": 990.0, "score_label": "MMR", "rounds_played": 12},
    ],
    "div_2": None,  # membership exists but no board published yet
}


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/observatory/whoami":
        return httpx.Response(200, json={"user_email": "pawsys@example.com", "name": "Pawel Sysiak"})
    if path == "/observatory/players":
        return httpx.Response(200, json=PLAYERS)
    if path == "/observatory/v2/leagues":
        return httpx.Response(200, json=LEAGUES)
    if path == "/observatory/v2/league-policy-memberships/portfolio":
        return httpx.Response(200, json=PORTFOLIO)
    if path.startswith("/observatory/v2/divisions/") and path.endswith("/leaderboard"):
        board = BOARDS[path.split("/")[-2]]
        if board is None:
            # The backend sends a literal `null` body for unpublished boards.
            return httpx.Response(200, content=b"null", headers={"content-type": "application/json"})
        return httpx.Response(200, json=board)
    raise AssertionError(f"unexpected request: {path}")


def _fetch() -> list[card.PlayerCard]:
    return card.fetch_player_cards("https://api.test", "tok", transport=httpx.MockTransport(_handler))


def test_fetch_orders_default_player_first_and_maps_standings():
    cards = _fetch()
    assert [c.name for c in cards] == ["Pawel Sysiak", "Ralph 2.0"]

    mine = cards[0]
    assert mine.creators == "Pawel Sysiak & coding-agent"
    assert mine.joined == "March 2025"
    # The unpublished-board league counts; the crashed seat's league and the
    # paused league do not.
    assert mine.leagues == 2
    assert len(mine.games) == 1  # div_2 has no published board, so that seat is left off
    # div_3 (crashed seat) and div_4 (paused league) exist only in PORTFOLIO:
    # absent from BOARDS, so this also proves the fetch never asks for dropped
    # seats' leaderboards.
    row = mine.games[0]
    assert (row.name, row.policy) == ("Agricogla", "terra:v7")
    assert (row.rank, row.total, row.mmr, row.rounds) == (2, 3, "1235", 40)

    ralph = cards[1]
    assert ralph.games[0].rank == 1
    assert ralph.leagues == 1


def test_fetch_reports_stages_for_the_loader():
    stages: list[str] = []
    card.fetch_player_cards("https://api.test", "tok", transport=httpx.MockTransport(_handler), on_stage=stages.append)
    assert stages == [
        "finding your players",
        "scanning the leagues",
        "collecting your seats",
        "reading standings 0/2",  # div_1 and div_2 only: dropped seats fetch no boards
        "reading standings 1/2",
        "reading standings 2/2",
    ]


def test_creators_fall_back_to_the_email_nick_when_the_account_has_no_name():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/observatory/whoami":
            return httpx.Response(200, json={"user_email": "pawsys@gmail.com"})
        return _handler(request)

    cards = card.fetch_player_cards("https://api.test", "tok", transport=httpx.MockTransport(handler))
    assert cards[0].creators == "pawsys & coding-agent"


def test_players_with_no_standings_are_hidden_when_another_player_has_some():
    quiet_portfolio = [s for s in PORTFOLIO if s["player_id"] != "ply_b"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/observatory/v2/league-policy-memberships/portfolio":
            return httpx.Response(200, json=quiet_portfolio)
        return _handler(request)

    cards = card.fetch_player_cards("https://api.test", "tok", transport=httpx.MockTransport(handler))
    assert [c.name for c in cards] == ["Pawel Sysiak"]


def test_every_player_renders_when_none_have_standings():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/observatory/v2/league-policy-memberships/portfolio":
            return httpx.Response(200, json=[])
        return _handler(request)

    cards = card.fetch_player_cards("https://api.test", "tok", transport=httpx.MockTransport(handler))
    assert [c.name for c in cards] == ["Pawel Sysiak", "Ralph 2.0"]
    assert all(not c.games for c in cards)


def test_a_division_ranked_by_something_other_than_rating_reads_n_a():
    by_win_rate = [{**row, "score": 0.62, "score_label": "Win %"} for row in BOARDS["div_1"]]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/div_1/leaderboard"):
            return httpx.Response(200, json=by_win_rate)
        return _handler(request)

    cards = card.fetch_player_cards("https://api.test", "tok", transport=httpx.MockTransport(handler))
    assert cards[0].games[0].mmr == "n/a"  # the rank is still real, the rating is not


def test_the_mmr_column_holds_a_rating_or_nothing():
    assert card._mmr(1234.6, "MMR") == "1235"
    assert card._mmr(1042.0, "Elo") == "1042"  # boards snapshotted before the wire rename
    assert card._mmr(3497970.0, "MMR") == "3498k"  # abbreviated rather than widening the column
    assert card._mmr(0.62, "Win %") == "n/a"
    assert card._mmr(0.0, "Score") == "n/a"  # a coworld's own score is not a rating


def test_wordmark_keeps_digits_and_signs_but_drops_the_rest():
    assert card.wordmark("Ralph 2.0") == "RALPH 2.0"
    assert card.wordmark("eck-star.b") == "ECK-STAR.B"
    assert card.wordmark("d'Artagnan_77") == "D'ARTAGNAN_77"
    assert card.wordmark("Ok, go! Ready? 1+1:2") == "OK, GO! READY? 1+1:2"
    assert card.wordmark("émile") == "MILE"
    assert card.wordmark("@#%") == "PLAYER"


def test_both_faces_cover_the_same_glyphs_at_consistent_widths():
    assert set(card.FONT_NAME_CONDENSED) == set(card.FONT_NAME)
    for font in (card.FONT_NAME, card.FONT_NAME_CONDENSED):
        for glyph in font.values():
            assert len(glyph) == 8
            assert len({len(row) for row in glyph}) == 1


def test_hero_drops_to_condensed_when_the_regular_face_overflows():
    name = "VON HOUCK"
    assert len(card._rasterize(name, card.FONT_NAME)[0]) > card.INNER
    assert len(card._rasterize(name, card.FONT_NAME_CONDENSED, gap=1)[0]) <= card.INNER
    hero = card._hero_lines(card.DEMO_CARD.model_copy(update={"name": name}))
    ink = max(i for line in hero for i, ch in enumerate(line) if ch in "█▀▄")
    # The clipped regular face would ink out to the frame edge; condensed ends early.
    assert ink < 60


def test_hero_still_clips_names_wider_than_both_faces():
    data = card.DEMO_CARD.model_copy(update={"name": "ECKHARDT SCHEFFER"})
    assert len(card._rasterize(data.name, card.FONT_NAME_CONDENSED, gap=1)[0]) > card.INNER
    assert {len(line) for line in card.render(data).splitlines()} == {74}


def test_identity_block_labels_player_and_creators():
    out = card.render(card.DEMO_CARD)
    assert "Player: Echo" in out
    assert "Creators: Rob & coding-agent" in out


def test_hero_wordmarks_the_raw_name():
    data = card.DEMO_CARD.model_copy(update={"name": "émile b."})
    out = card.render(data)
    assert "Player: émile b." in out  # the text line keeps what the pixel font drops
    assert {len(line) for line in out.splitlines()} == {74}


def test_fetched_cards_render_at_uniform_width():
    for c in _fetch():
        widths = {len(line) for line in card.render(c).splitlines()}
        assert widths == {74}


def test_long_game_names_truncate_inside_the_frame():
    long = card.GameRow(name="A Very Long Game Name Indeed", policy="p:v1", rank=1, total=2, mmr="1000", rounds=5)
    long_games = [long]
    data = card.DEMO_CARD.model_copy(update={"games": long_games})
    out = card.render(data)
    clipped = "A Very Long Game Name Indeed"[: card.GAME_W - 2] + "…"  # one short of the field
    assert clipped in out
    assert {len(line) for line in out.splitlines()} == {74}


def test_num_right_aligns_and_abbreviates_to_width():
    assert card._num(638, 4) == " 638"
    assert card._num(10000, 4) == " 10k"
    assert card._num(3497970, 4) == "3.5M"
    assert card._num(1234567, 6) == " 1235k"


def test_huge_stats_abbreviate_instead_of_breaking_the_frame():
    huge = card._mmr(3497970.0, "MMR")
    rows = [card.GameRow(name="Muster", policy="ilya_muromets:v1", rank=7, total=10, mmr=huge, rounds=1234567)]
    out = card.render(card.DEMO_CARD.model_copy(update={"games": rows}))
    assert "3498k" in out
    assert "1235k" in out
    assert {len(line) for line in out.splitlines()} == {74}


def test_rank_pairs_a_plain_rank_with_a_padded_board_size():
    rows = [
        card.GameRow(name="Ninepin", policy="dalli:v1", rank=1, total=9, mmr="1173", rounds=84),
        card.GameRow(name="Wideboard", policy="steady:v4", rank=10, total=13, mmr="998", rounds=27),
    ]
    lines = card.render(card.DEMO_CARD.model_copy(update={"games": rows})).splitlines()
    nine = next(line for line in lines if "Ninepin" in line)
    wide = next(line for line in lines if "Wideboard" in line)
    assert " 1/09 " in nine  # the rank as written, never "01"; the board size padded to two digits
    assert "10/13 " in wide
    assert nine.index("/") == wide.index("/")  # right-aligned, so every bar starts in one column


def test_thousand_seat_boards_pad_beside_small_ones_inside_the_frame():
    rows = [
        card.GameRow(name="Mega", policy="p:v1", rank=1, total=1000, mmr="1000", rounds=10),
        card.GameRow(name="Boutique", policy="p:v2", rank=2, total=6, mmr="1000", rounds=10),
    ]
    out = card.render(card.DEMO_CARD.model_copy(update={"games": rows}))
    assert "1/1000 " in out
    assert "2/06 " in out  # a six-seat board reads as six, not "0006" borrowed from its neighbour
    assert {len(line) for line in out.splitlines()} == {74}


def test_the_rank_bar_runs_to_the_frame_with_no_percent_column():
    rows = [
        card.GameRow(name="Topseed", policy="p:v1", rank=1, total=4, mmr="1000", rounds=10),
        card.GameRow(name="Bottom", policy="p:v2", rank=4, total=4, mmr="900", rounds=10),
    ]
    lines = card.render(card.DEMO_CARD.model_copy(update={"games": rows})).splitlines()
    header, top, bottom = (next(line for line in lines if key in line) for key in ("policy", "Topseed", "Bottom"))
    assert header.rstrip(" ╎").endswith("rank")  # rank is the last label: no %outranked column
    assert top.rstrip(" ╎").endswith("█")  # first of the board fills the bar to the frame
    assert bottom.rstrip(" ╎").endswith("┈")  # last of the board leaves the whole track empty
    assert "%" not in top and "%" not in bottom


def test_framed_clips_content_that_would_break_the_frame():
    assert len(card._framed("x" * 200)) == len(card._framed(""))


def test_empty_standings_render_placeholder():
    data = card.DEMO_CARD.model_copy(update={"games": []})
    out = card.render(data)
    assert "no league standings yet" in out
    assert {len(line) for line in out.splitlines()} == {74}
