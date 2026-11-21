import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


APP = Path(__file__).resolve().parents[1] / "badge" / "apps" / "reality_dojo" / "__init__.py"


class Badge:
    ticks = 0
    ticks_delta = 100

    def __init__(self):
        self.presses = set()
        self.holds = set()
        self.acceleration = (0, -16384, 0)

    def pressed(self, button):
        return button in self.presses

    def held(self, button):
        return button in self.holds

    def imu(self):
        return self.acceleration + (0, 0, 0)


class Screen:
    width = 160
    height = 120
    clip = None

    def rectangle(self, *args):
        pass

    def text(self, *args):
        pass


class State:
    data = {}

    @classmethod
    def load(cls, key, target):
        target.update(cls.data)

    @classmethod
    def save(cls, key, source):
        cls.data = dict(source)


class Link:
    def __init__(self, central):
        self.central = central
        self.linked = True
        self.inbox = []
        self.peer = None

    def send(self, data):
        self.peer.inbox.append(data)
        return True

    def receive(self):
        result, self.inbox = self.inbox, []
        return result

    def pump(self):
        pass

    def update(self):
        pass

    def close(self):
        self.linked = False


def load_app():
    badge = Badge()
    globals_ = {"badge": badge, "screen": Screen(),
                "font": types.SimpleNamespace(nope=object()),
                "color": types.SimpleNamespace(rgb=lambda *args: args),
                "run": lambda update: None}
    for name in ("UP", "DOWN", "LEFT", "RIGHT", "SELECT", "BACK"):
        globals_["BUTTON_" + name] = name
    with patch.dict(sys.modules, {"badgeware": types.SimpleNamespace(State=State)}), \
            patch.object(sys, "path", [str(APP.parent)] + sys.path):
        app = runpy.run_path(str(APP), init_globals=globals_)
    return app, badge


class RealityDojoTests(unittest.TestCase):
    def setUp(self):
        State.data = {}

    def test_japanese_screens_render_without_missing_glyphs(self):
        app, _ = load_app()
        game = app["game"]
        game.draw()
        for message in app["JP_MESSAGES"]:
            game.message = message
            game.draw()
        game.mode = "edit"
        for row in range(len(app["FIELDS"])):
            game.row = row
            for nation in range(len(app["NATIONS"])):
                app["saved"]["nation"] = nation
                game.draw()
        for mode in ("help", "link"):
            game.mode = mode
            game.draw()
        game.start_tutorial()
        for step in range(5):
            game.tutorial_step = step
            game.draw()
        game.start_tournament()
        for round_number in range(3):
            game.round = round_number
            game.player["hp"], game.enemy["hp"] = 100, 0
            game.draw()
        game.player["hp"], game.enemy["hp"] = 0, 100
        game.draw()
        game.player["hp"], game.enemy["hp"] = 0, 0
        game.draw()

    def test_cpu_approaches_without_overlap_and_retreats(self):
        app, badge = load_app()
        game = app["game"]
        game.start_cpu()
        game.player["x"], game.enemy["x"] = 60, 110
        game.ai_wait = 100
        with patch.object(app["random"], "choice", return_value="approach"):
            for _ in range(20):
                game.update()
            self.assertAlmostEqual(game.enemy["x"] - game.player["x"], 26)
            for _ in range(10):
                game.update()
                self.assertAlmostEqual(game.enemy["x"] - game.player["x"], 26)
        game.player["x"] = game.enemy["x"] - 18
        game.update()
        game.update()
        self.assertGreaterEqual(game.enemy["x"] - game.player["x"], 23)
        with patch.object(app["random"], "choice", return_value="retreat"):
            game.ai_decision = 0
            for _ in range(10):
                game.update()
            self.assertAlmostEqual(game.enemy["x"] - game.player["x"], 34)
        with patch.object(app["random"], "choice", return_value="guard"):
            game.ai_decision = 0
            game.update()
            self.assertTrue(game.enemy["guard"])

    def test_shake_requires_two_distinct_impulses_and_has_cooldown(self):
        app, _ = load_app()
        detector = app["ShakeDetector"]()
        rest = (0, -16384, 0)
        small = (4000, -16384, 0)
        shock = (16000, -16384, 0)
        self.assertFalse(detector.update(rest, 0.1))
        for _ in range(10):
            self.assertFalse(detector.update(small, 0.05))
        self.assertFalse(detector.update(shock, 0.05))
        self.assertFalse(detector.update(shock, 0.05))
        self.assertFalse(detector.update(rest, 0.05))
        self.assertTrue(detector.update(shock, 0.05))
        self.assertFalse(detector.update(rest, 0.05))
        self.assertFalse(detector.update(shock, 0.05))
        self.assertFalse(detector.update(rest, 1.1))
        self.assertFalse(detector.update(shock, 0.05))
        self.assertFalse(detector.update(rest, 0.7))
        self.assertFalse(detector.update(shock, 0.05))

    def test_shake_special_consumes_full_meter_only_when_charged(self):
        app, badge = load_app()
        game = app["game"]
        game.start_cpu()
        game.player["x"], game.enemy["x"] = 50, 74
        game.ai_wait, game.ai_decision, game.ai_action = 100, 100, "wait"
        game.player["meter"] = 99
        for x in (0, 16000, 0, -16000):
            badge.acceleration = (x, -16384, 0)
            game.update()
        self.assertEqual(game.player["meter"], 99)
        self.assertEqual(game.enemy["hp"], 100)
        game.shake = app["ShakeDetector"]()
        game.player["meter"] = 100
        for x in (0, 16000, 0, -16000):
            badge.acceleration = (x, -16384, 0)
            game.update()
        self.assertEqual(game.player["meter"], 0)
        self.assertLess(game.enemy["hp"], 100)

    def test_clock_stages_and_unset_clock(self):
        app, _ = load_app()
        for hour, expected in ((5, 0), (11, 1), (17, 2), (22, 3), (4, 3)):
            with patch.object(app["time"], "localtime", return_value=(2026, 1, 1, hour)):
                self.assertEqual(app["current_stage"](), (expected, True))
        with patch.object(app["time"], "localtime", return_value=(2020, 1, 1, 12)):
            self.assertEqual(app["current_stage"](), (1, False))
        with patch.object(app["time"], "localtime", side_effect=OSError("RTC")):
            self.assertEqual(app["current_stage"](), (1, False))

    def test_editor_cancel_then_save(self):
        app, badge = load_app()
        game = app["game"]
        game.menu = 1
        badge.presses = {"SELECT"}
        game.update()
        badge.presses = {"RIGHT"}
        game.update()
        badge.presses = {"BACK"}
        game.update()
        self.assertEqual(app["saved"]["color"], 0)
        badge.presses = {"SELECT"}
        game.update()
        badge.presses = {"RIGHT"}
        game.update()
        badge.presses = {"SELECT"}
        game.update()
        self.assertEqual(State.data["color"], 1)

    def test_existing_save_gets_neutral_new_features(self):
        State.data = {"color": 2, "style": 1, "power": 4}
        app, _ = load_app()
        self.assertEqual(app["saved"], {"color": 2, "style": 1, "power": 4,
                                         "face": 0, "body": 0, "nation": 0})

    def test_editor_saves_new_fields_and_wraps(self):
        app, badge = load_app()
        game = app["game"]
        game.menu = 1
        badge.presses = {"SELECT"}
        game.update()
        for row in (2, 3, 4):
            game.row = row
            badge.presses = {"LEFT"}
            game.update()
        badge.presses = {"SELECT"}
        game.update()
        self.assertEqual((State.data["face"], State.data["body"], State.data["nation"]), (2, 2, 8))

    def test_existing_nationality_ids_and_g7(self):
        State.data = {"color": 0, "style": 0, "power": 3, "nation": 4}
        app, _ = load_app()
        names = app["NATIONS"]
        self.assertEqual(names[app["saved"]["nation"]], "USA")
        for country in ("JAPAN", "FRANCE", "USA", "CANADA", "GERMANY", "ITALY", "UK"):
            self.assertIn(country, names)
        for bonus in app["BONUSES"]:
            self.assertLessEqual(abs(bonus[0]), 1)
            self.assertLessEqual(abs(bonus[1]), 2)

    def test_nationality_tradeoff_affects_damage_and_speed(self):
        app, _ = load_app()
        fighter, step = app["fighter"], app["step_fighter"]
        base = {"color": 0, "style": 0, "power": 3}
        a = fighter(dict(base, nation=1), 50)
        b = fighter(dict(base, nation=2), 65)
        step(a, b, 2, True, 0.1, 1)
        self.assertEqual(b["hp"], 87)
        self.assertAlmostEqual(a["x"], 54.3)
        step(b, a, 2, True, 0.1, 1)
        self.assertEqual(a["hp"], 89)
        self.assertAlmostEqual(b["x"], 69.7)

    def test_cpu_damage_guard_and_midnight(self):
        app, _ = load_app()
        step, fighter = app["step_fighter"], app["fighter"]
        a = fighter({"color": 0, "style": 0, "power": 3}, 50)
        b = fighter({"color": 1, "style": 0, "power": 3}, 65)
        step(a, b, 0, True, 0.1, 3)
        self.assertEqual(b["hp"], 86)
        b["guard"] = True
        step(a, b, 0, True, 0.6, 3)
        self.assertEqual(b["hp"], 82)
        self.assertGreater(b["guard_hit"], 0)
        self.assertGreater(b["hurt"], 0)
        step(b, a, 0, False, 0.5, 3)
        self.assertEqual((b["guard_hit"], b["hurt"]), (0, 0))

    def test_special_charge_hit_miss_and_cooldown(self):
        app, _ = load_app()
        fighter, step = app["fighter"], app["step_fighter"]
        a = fighter({"color": 0, "style": 0, "power": 3}, 50)
        b = fighter({"color": 1, "style": 0, "power": 3}, 65)
        step(a, b, 0, False, 0.1, 1, True)
        self.assertEqual((a["meter"], b["hp"]), (0, 100))
        for _ in range(4):
            step(a, b, 0, True, 0.6, 1)
        self.assertEqual((a["meter"], b["meter"], b["hp"]), (100, 60, 52))
        step(a, b, 0, False, 0.1, 1, True)
        self.assertEqual(a["meter"], 100)
        step(a, b, 0, False, 0.6, 1, True)
        self.assertEqual((a["meter"], b["meter"], b["hp"]), (0, 75, 26))
        self.assertGreater(a["special_flash"], 0)
        a["meter"], b["x"] = 100, 140
        step(a, b, 0, False, 1.0, 1, True)
        self.assertEqual((a["meter"], b["hp"]), (0, 26))

    def test_help_before_fight(self):
        app, badge = load_app()
        game = app["game"]
        badge.presses = {"SELECT"}
        game.update()
        self.assertEqual(game.mode, "help")
        badge.presses = {"BACK"}
        game.update()
        self.assertEqual(game.mode, "menu")
        badge.presses = {"SELECT"}
        game.update()
        game.update()
        self.assertEqual(game.mode, "cpu")

    def test_tournament_progression_and_elimination(self):
        app, badge = load_app()
        game = app["game"]
        game.menu = 3
        badge.presses = {"SELECT"}
        game.update()
        self.assertEqual(game.mode, "help")
        game.update()
        self.assertEqual(game.mode, "tournament")
        self.assertEqual(len(game.opponents), 3)
        for next_round in (1, 2):
            game.player["hp"], game.player["meter"] = 20, 90
            game.enemy["hp"] = 0
            game.update()
            self.assertEqual(game.round, next_round)
            self.assertEqual((game.player["hp"], game.player["meter"]), (100, 0))
        game.enemy["hp"] = 0
        game.update()
        self.assertEqual(game.round, 2)
        game.player["hp"] = 0
        game.enemy["hp"] = 100
        game.update()
        self.assertEqual(game.round, 2)
        badge.presses = {"BACK"}
        game.update()
        self.assertEqual(game.mode, "menu")

    def test_tutorial_requires_each_action(self):
        app, badge = load_app()
        game = app["game"]
        game.menu = 4
        badge.presses = {"SELECT"}
        game.update()
        self.assertEqual(game.mode, "tutorial")
        badge.presses, badge.holds = set(), {"RIGHT"}
        game.update()
        self.assertEqual(game.tutorial_step, 1)
        badge.holds = {"DOWN"}
        game.update()
        self.assertEqual(game.tutorial_step, 2)
        badge.holds, badge.presses = set(), {"UP"}
        game.update()
        self.assertEqual(game.tutorial_step, 2)
        badge.presses = {"SELECT"}
        for _ in range(4):
            game.player["cooldown"] = 0
            game.update()
        self.assertEqual(game.tutorial_step, 3)
        game.player["cooldown"] = 0
        badge.presses = {"UP"}
        game.update()
        self.assertEqual(game.tutorial_step, 4)
        self.assertEqual(game.player["meter"], 0)
        badge.presses = {"SELECT"}
        game.update()
        self.assertEqual(game.mode, "menu")

    def test_two_peers_exchange_fighters_and_sync_fight(self):
        host, host_badge = load_app()
        guest, guest_badge = load_app()
        host["saved"].update(color=0, style=1, power=5, face=2, body=1, nation=1)
        guest["saved"].update(color=2, style=2, power=2, face=1, body=2, nation=8)
        a, b = Link(True), Link(False)
        a.peer, b.peer = b, a
        h, g = host["game"], guest["game"]
        h.mode = g.mode = "link"
        h.link, g.link = a, b
        for tick in range(100, 800, 100):
            h.network(tick, 0.1)
            g.network(tick, 0.1)
        self.assertEqual((h.mode, g.mode), ("host", "guest"))
        self.assertEqual(h.enemy["character"]["color"], 2)
        self.assertEqual(g.enemy["character"]["style"], 1)
        self.assertEqual([h.enemy["character"][key] for key in ("face", "body", "nation")], [1, 2, 8])
        self.assertEqual([g.enemy["character"][key] for key in ("face", "body", "nation")], [2, 1, 1])
        h.player["x"], h.enemy["x"] = 50, 65
        guest_badge.presses = {"SELECT"}
        g.network(800, 0.1)
        guest_badge.presses = set()
        h.network(800, 0.1)
        g.network(900, 0.1)
        self.assertLess(h.player["hp"], 100)
        self.assertEqual(g.enemy["hp"], h.player["hp"])
        health = h.player["hp"]
        h.network(1000, 0.1)
        self.assertEqual(h.player["hp"], health)
        h.enemy["meter"] = 100
        h.enemy["cooldown"] = 0
        h.network(1100, 0.1)
        g.network(1100, 0.1)
        self.assertEqual(g.player["meter"], 100)
        guest_badge.presses = {"UP"}
        g.network(1200, 0.1, special=True)
        guest_badge.presses = set()
        h.network(1200, 0.1)
        g.network(1300, 0.1)
        self.assertEqual((h.enemy["meter"], g.player["meter"]), (0, 0))
        self.assertLess(h.player["hp"], health)
        self.assertEqual(g.enemy["hp"], h.player["hp"])
        self.assertTrue(g.player["special_flash"])
        health = h.player["hp"]
        h.network(1400, 0.1)
        self.assertEqual(h.player["hp"], health)
        host_badge.holds = {"DOWN"}
        h.enemy["cooldown"] = 0
        guest_badge.presses = {"SELECT"}
        g.network(1500, 0.1)
        guest_badge.presses = set()
        h.network(1500, 0.1)
        g.network(1600, 0.1)
        self.assertGreater(h.player["guard_hit"], 0)
        self.assertTrue(g.enemy["guard_hit"])

    def test_invalid_character_extension_is_ignored(self):
        app, _ = load_app()
        game = app["game"]
        game.mode = "link"
        game.link = Link(True)
        game.link.peer = Link(False)
        game.link.inbox = [b"C\x01\x02\x03", b"E\xff\x01\x01"]
        game.network(100, 0.1)
        self.assertEqual(game.mode, "host")
        self.assertEqual(game.enemy["character"]["nation"], 0)
        self.assertEqual(game.enemy["character"]["face"], 0)
        self.assertIn(b"C\x00\x00\x03", game.link.peer.inbox)


if __name__ == "__main__":
    unittest.main()
