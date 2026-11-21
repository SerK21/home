"""A clock-powered fighting game for one or two badges."""

import random
import sys
import time

from badgeware import State

sys.path.insert(0, "/system/apps/reality_dojo")
from japanese_font import GLYPHS


STATE_KEY = "reality_dojo"
GAME_ID = "reality_dojo_v3"
COLORS = ((247, 91, 94), (58, 181, 244), (238, 193, 65), (163, 106, 235))
STAGES = ("MORNING", "DAY", "EVENING", "MIDNIGHT")
SKIES = ((95, 155, 190), (68, 155, 205), (165, 86, 93), (28, 29, 66))
NATIONS = ("NONE", "JAPAN", "BRAZIL", "FRANCE", "USA",
           "CANADA", "GERMANY", "ITALY", "UK")
BONUSES = ((0, 0), (1, -2), (-1, 2), (-1, 2), (1, -2),
           (-1, 2), (1, -2), (-1, 2), (1, -2))
FIELDS = ("color", "style", "face", "body", "nation", "power")
LIMITS = (4, 3, 3, 3, len(NATIONS), 6)
MENU = ("CPU FIGHT", "MAKE FIGHTER", "BADGE FIGHT", "TOURNAMENT", "TUTORIAL")
ROUNDS = ("QUARTERFINAL", "SEMIFINAL", "FINAL")
JP_STAGES = ("朝", "昼", "夕方", "深夜")
JP_NATIONS = ("なし", "日本", "ブラジル", "フランス", "アメリカ",
              "カナダ", "ドイツ", "イタリア", "イギリス")
JP_MENU = ("CPU対戦", "キャラ作成", "バッジ対戦", "トーナメント", "チュートリアル")
JP_ROUNDS = ("準々決勝", "準決勝", "決勝")
JP_MESSAGES = {"SAVED": "保存しました", "LINK UNAVAILABLE": "通信できません",
               "PEER DISCONNECTED": "通信が切れました", "": ""}
JP_PROMPTS = (("左右: 移動", "戻る: 終了"),
              ("下: ガード", "戻る: 終了"),
              ("近づいて攻撃", "決定: SPをためる"),
              ("上/振る: 必殺技", "SP満タンで全消費"),
              ("練習完了!", "決定: メニュー"))


def draw_text(text, x, y):
    for char in text:
        width, rows = GLYPHS[char]
        for dy, row in enumerate(rows):
            start = -1
            for dx in range(width + 1):
                pixel = dx < width and row & (128 >> dx)
                if pixel and start < 0:
                    start = dx
                elif not pixel and start >= 0:
                    screen.rectangle(x + start, y + dy, dx - start, 1)
                    start = -1
        x += width

saved = {"color": 0, "style": 0, "power": 3, "face": 0, "body": 0, "nation": 0}
State.load(STATE_KEY, saved)
for key, limit in zip(FIELDS, LIMITS):
    if not isinstance(saved.get(key), int) or not 0 <= saved[key] < limit:
        saved[key] = 3 if key == "power" else 0
if saved["power"] < 1:
    saved["power"] = 1


class ShakeDetector:
    def __init__(self):
        self.rest = None
        self.gravity = 0
        self.armed = True
        self.window = 0
        self.cooldown = 0

    def update(self, reading, dt):
        self.cooldown = max(0, self.cooldown - dt)
        self.window = max(0, self.window - dt)
        acceleration = reading[:3]
        if self.rest is None:
            gravity = sum(value * value for value in acceleration) ** 0.5
            if gravity > 0:
                self.gravity = gravity
                self.rest = list(acceleration)
            return False
        delta = sum((acceleration[i] - self.rest[i]) ** 2 for i in range(3)) ** 0.5
        if delta < self.gravity * 0.4:
            self.armed = True
        triggered = False
        if self.armed and delta > self.gravity * 0.85:
            self.armed = False
            if self.cooldown == 0:
                if self.window > 0:
                    triggered = True
                    self.window = 0
                    self.cooldown = 1.0
                else:
                    self.window = 0.6
        if delta < self.gravity * 0.85:
            blend = min(1.0, dt / 2.0)
            for i in range(3):
                self.rest[i] += (acceleration[i] - self.rest[i]) * blend
        return triggered


def current_stage():
    try:
        now = time.localtime()
        if now[0] <= 2021 or not 0 <= now[3] < 24:
            return 1, False
        hour = now[3]
        if 5 <= hour < 11:
            return 0, True
        if 11 <= hour < 17:
            return 1, True
        if 17 <= hour < 22:
            return 2, True
        return 3, True
    except (OSError, ValueError, IndexError):
        return 1, False


def fighter(character, x):
    details = {"face": 0, "body": 0, "nation": 0}
    details.update(character)
    return {"character": details, "x": x, "hp": 100, "meter": 0,
            "cooldown": 0, "flash": 0, "special_flash": 0,
            "guard": False, "guard_hit": 0, "moving": False, "hurt": 0}


def controls():
    return ((1 if badge.held(BUTTON_LEFT) else 0) |
            (2 if badge.held(BUTTON_RIGHT) else 0) |
            (4 if badge.held(BUTTON_DOWN) else 0))


def step_fighter(me, other, keys, attack, dt, stage, special=False, move_limit=None):
    me["cooldown"] = max(0, me["cooldown"] - dt)
    me["flash"] = max(0, me["flash"] - dt)
    me["special_flash"] = max(0, me["special_flash"] - dt)
    me["guard_hit"] = max(0, me["guard_hit"] - dt)
    me["hurt"] = max(0, me["hurt"] - dt)
    me["guard"] = bool(keys & 4)
    direction = (1 if keys & 2 else 0) - (1 if keys & 1 else 0)
    bonus_damage, bonus_speed = BONUSES[me["character"]["nation"]]
    speed = 30 + (6 - me["character"]["power"]) * 5 + bonus_speed
    old_x = me["x"]
    movement = speed * dt
    if move_limit is not None:
        movement = min(movement, move_limit)
    me["x"] = max(12, min(148, me["x"] + direction * movement))
    me["moving"] = me["x"] != old_x
    use_special = special and me["meter"] >= 100
    if (attack or use_special) and me["cooldown"] <= 0:
        me["cooldown"] = 0.85 if use_special else 0.55
        me["flash"] = 0.35 if use_special else 0.18
        if use_special:
            me["meter"] = 0
            me["special_flash"] = 0.35
        if abs(me["x"] - other["x"]) <= (40 if use_special else 27):
            damage = 6 + me["character"]["power"] * 2 + bonus_damage
            if use_special:
                damage += 14
            if stage == 3:
                damage += 2
            if other["guard"]:
                damage = max(1, damage // 3)
                other["guard_hit"] = 0.4
            other["hurt"] = 0.25
            other["hp"] = max(0, other["hp"] - damage)
            if not use_special:
                me["meter"] = min(100, me["meter"] + 25)
            other["meter"] = min(100, other["meter"] + 15)


class Game:
    def __init__(self):
        self.mode = "menu"
        self.menu = 0
        self.row = 0
        self.stage, self.clock_ok = current_stage()
        self.link = None
        self.proximity = None
        self.was_linked = False
        self.message = ""
        self.out_at = 0
        self.remote = None
        self.seq = 0
        self.remote_seq = 0
        self.special_seq = 0
        self.remote_special_seq = 0
        self.remote_keys = 0
        self.remote_attack = False
        self.remote_special = False
        self.ai_wait = 0
        self.ai_decision = 0
        self.ai_action = "approach"
        self.shake = ShakeDetector()
        self.player = None
        self.enemy = None
        self.edit_original = None
        self.next_fight = None
        self.round = 0
        self.opponents = []
        self.tutorial_step = 0

    def close_link(self):
        if self.link is not None:
            self.link.close()
            self.link = None
            self.proximity = None
        self.was_linked = False

    def start_cpu(self, character=None, mode="cpu"):
        self.stage, self.clock_ok = current_stage()
        self.shake = ShakeDetector()
        self.player = fighter(saved, 38)
        if character is None:
            character = {"color": (saved["color"] + 1) % 4,
                         "style": (saved["style"] + 1) % 3, "power": 3}
        self.enemy = fighter(character, 122)
        self.ai_wait = 0
        self.ai_decision = 0
        self.ai_action = "approach"
        self.mode = mode

    def start_tournament(self):
        entrants = [{"color": (i + 1) % 4, "style": i % 3, "face": i % 3,
                     "body": (i + 1) % 3, "power": 2 + i % 3,
                     "nation": i + 1} for i in range(7)]
        left_winner = random.choice(entrants[1:3])
        right_winner = random.choice((random.choice(entrants[3:5]),
                                      random.choice(entrants[5:7])))
        self.opponents = [entrants[0], left_winner, right_winner]
        self.round = 0
        self.start_cpu(self.opponents[self.round], "tournament")

    def start_tutorial(self):
        self.start_cpu(mode="tutorial")
        self.player["x"] = 48
        self.enemy["x"] = 72
        self.tutorial_step = 0

    def start_link(self):
        self.shake = ShakeDetector()
        try:
            from badgeware import link as badgelink
            self.link = badgelink.Link(GAME_ID)
            self.proximity = badgelink.Proximity(self.link)
        except (ImportError, OSError) as exc:
            print("Link unavailable:", exc)
            self.message = "LINK UNAVAILABLE"
            self.close_link()
            return
        self.was_linked = False
        self.remote = None
        self.out_at = 0
        self.seq = 0
        self.remote_seq = 0
        self.special_seq = 0
        self.remote_special_seq = 0
        self.remote_keys = 0
        self.remote_attack = False
        self.remote_special = False
        self.mode = "link"
        self.message = ""

    def start_network_match(self):
        self.stage, self.clock_ok = current_stage()
        self.player = fighter(saved, 38)
        self.enemy = fighter(self.remote, 122)
        self.mode = "host"

    def send_character(self):
        self.link.send(b"C" + bytes((saved["color"], saved["style"], saved["power"])))
        self.link.send(b"E" + bytes((saved["face"], saved["body"], saved["nation"])))

    def network(self, now, dt, special=False):
        self.link.pump()
        linked = self.link.linked
        if self.was_linked and not linked:
            self.close_link()
            self.mode = "menu"
            self.message = "PEER DISCONNECTED"
            return
        self.was_linked = linked
        if linked:
            for packet in self.link.receive():
                if packet[:1] == b"C" and len(packet) == 4:
                    c, s, p = packet[1], packet[2], packet[3]
                    if c < 4 and s < 3 and 1 <= p <= 5:
                        if self.remote is None:
                            self.remote = {"face": 0, "body": 0, "nation": 0}
                        self.remote.update(color=c, style=s, power=p)
                elif packet[:1] == b"E" and len(packet) == 4 and self.remote is not None:
                    face, body, nation = packet[1], packet[2], packet[3]
                    if face < 3 and body < 3 and nation < len(NATIONS):
                        self.remote.update(face=face, body=body, nation=nation)
                        if self.enemy is not None and self.mode in ("host", "guest"):
                            self.enemy["character"].update(self.remote)
                elif packet[:1] == b"I" and len(packet) == 4 and self.mode == "host":
                    self.remote_keys = packet[1] & 7
                    if packet[2] != self.remote_seq:
                        self.remote_seq = packet[2]
                        self.remote_attack = True
                    if packet[3] != self.remote_special_seq:
                        self.remote_special_seq = packet[3]
                        self.remote_special = True
                elif packet[:1] == b"S" and len(packet) == 11 and self.remote is not None:
                    stage, x1, x2, hp1, hp2, flags, ack, clock_ok, sp1, sp2 = packet[1:]
                    if stage < 4 and x1 <= 160 and x2 <= 160 and hp1 <= 100 and hp2 <= 100 and sp1 <= 100 and sp2 <= 100:
                        if self.mode == "link":
                            self.player = fighter(saved, x2)
                            self.enemy = fighter(self.remote, x1)
                        self.stage, self.clock_ok = stage, bool(clock_ok)
                        self.player["moving"] = abs(self.player["x"] - x2) > 0.5
                        self.enemy["moving"] = abs(self.enemy["x"] - x1) > 0.5
                        self.player["x"], self.enemy["x"] = x2, x1
                        self.player["hurt"] = 0.25 if hp2 < self.player["hp"] else max(0, self.player["hurt"] - dt)
                        self.enemy["hurt"] = 0.25 if hp1 < self.enemy["hp"] else max(0, self.enemy["hurt"] - dt)
                        self.player["hp"], self.enemy["hp"] = hp2, hp1
                        self.player["meter"], self.enemy["meter"] = sp2, sp1
                        self.player["guard"], self.enemy["guard"] = bool(flags & 2), bool(flags & 1)
                        self.player["flash"], self.enemy["flash"] = bool(flags & 8), bool(flags & 4)
                        self.player["special_flash"], self.enemy["special_flash"] = bool(flags & 32), bool(flags & 16)
                        self.player["guard_hit"], self.enemy["guard_hit"] = bool(flags & 128), bool(flags & 64)
                        self.mode = "guest"

            if self.mode == "link" and self.link.central and self.remote is not None:
                self.start_network_match()
            if self.mode == "host" and self.player["hp"] and self.enemy["hp"]:
                step_fighter(self.player, self.enemy, controls(), badge.pressed(BUTTON_SELECT), dt, self.stage,
                             special)
                if self.enemy["hp"]:
                    step_fighter(self.enemy, self.player, self.remote_keys, self.remote_attack, dt, self.stage,
                                 self.remote_special)
                self.remote_attack = False
                self.remote_special = False
            elif self.mode == "guest":
                if badge.pressed(BUTTON_SELECT):
                    self.seq = (self.seq + 1) % 256
                if special:
                    self.special_seq = (self.special_seq + 1) % 256
            if now - self.out_at >= 100:
                self.out_at = now
                self.send_character()
                if self.mode == "host":
                    flags = ((1 if self.player["guard"] else 0) |
                             (2 if self.enemy["guard"] else 0) |
                             (4 if self.player["flash"] else 0) |
                             (8 if self.enemy["flash"] else 0) |
                             (16 if self.player["special_flash"] else 0) |
                             (32 if self.enemy["special_flash"] else 0) |
                             (64 if self.player["guard_hit"] else 0) |
                             (128 if self.enemy["guard_hit"] else 0))
                    self.link.send(b"S" + bytes((self.stage, int(self.player["x"]), int(self.enemy["x"]),
                                                self.player["hp"], self.enemy["hp"], flags,
                                                self.remote_seq, int(self.clock_ok),
                                                self.player["meter"], self.enemy["meter"])))
                elif self.mode == "guest":
                    self.link.send(b"I" + bytes((controls(), self.seq, self.special_seq)))
        elif self.mode == "link":
            self.proximity.update(now)
        self.link.update()

    def update(self):
        dt = min(badge.ticks_delta, 100) / 1000
        now = badge.ticks
        special = False
        if self.mode in ("cpu", "host", "guest", "tournament", "tutorial"):
            shaken = self.shake.update(badge.imu(), dt)
            special = badge.pressed(BUTTON_UP) or shaken
        if self.mode == "menu":
            if badge.pressed(BUTTON_UP):
                self.menu = (self.menu - 1) % len(MENU)
            if badge.pressed(BUTTON_DOWN):
                self.menu = (self.menu + 1) % len(MENU)
            if badge.pressed(BUTTON_SELECT):
                self.message = ""
                if self.menu == 0:
                    self.next_fight = "cpu"
                    self.mode = "help"
                elif self.menu == 1:
                    self.edit_original = dict(saved)
                    self.mode = "edit"
                elif self.menu == 2:
                    self.next_fight = "link"
                    self.mode = "help"
                elif self.menu == 3:
                    self.next_fight = "tournament"
                    self.mode = "help"
                else:
                    self.start_tutorial()
        elif self.mode == "help":
            if badge.pressed(BUTTON_SELECT):
                if self.next_fight == "cpu":
                    self.start_cpu()
                elif self.next_fight == "tournament":
                    self.start_tournament()
                else:
                    self.start_link()
            elif badge.pressed(BUTTON_BACK):
                self.mode = "menu"
        elif self.mode == "edit":
            if badge.pressed(BUTTON_UP):
                self.row = (self.row - 1) % len(FIELDS)
            if badge.pressed(BUTTON_DOWN):
                self.row = (self.row + 1) % len(FIELDS)
            change = (1 if badge.pressed(BUTTON_RIGHT) else 0) - (1 if badge.pressed(BUTTON_LEFT) else 0)
            if change:
                key = FIELDS[self.row]
                if key == "power":
                    saved[key] = max(1, min(5, saved[key] + change))
                else:
                    saved[key] = (saved[key] + change) % LIMITS[self.row]
            if badge.pressed(BUTTON_SELECT):
                State.save(STATE_KEY, saved)
                self.mode = "menu"
                self.message = "SAVED"
            elif badge.pressed(BUTTON_BACK):
                saved.update(self.edit_original)
                self.mode = "menu"
        elif self.mode in ("link", "host", "guest"):
            if badge.pressed(BUTTON_BACK):
                self.close_link()
                self.mode = "menu"
                return
            self.network(now, dt, special)
        elif self.mode == "tutorial":
            if badge.pressed(BUTTON_BACK):
                self.mode = "menu"
                return
            if self.tutorial_step == 4:
                if badge.pressed(BUTTON_SELECT):
                    self.mode = "menu"
            else:
                keys = controls()
                step_fighter(self.player, self.enemy, keys,
                             self.tutorial_step == 2 and badge.pressed(BUTTON_SELECT),
                             dt, self.stage,
                             self.tutorial_step == 3 and special)
                self.enemy["hp"] = 100
                if self.tutorial_step == 0 and keys & 3:
                    self.tutorial_step = 1
                elif self.tutorial_step == 1 and keys & 4:
                    self.tutorial_step = 2
                elif self.tutorial_step == 2 and self.player["meter"] == 100:
                    self.tutorial_step = 3
                elif self.tutorial_step == 3 and self.player["special_flash"]:
                    self.tutorial_step = 4
        elif self.mode in ("cpu", "tournament"):
            if badge.pressed(BUTTON_BACK):
                self.mode = "menu"
                return
            if (self.mode == "tournament" and self.player["hp"] and not self.enemy["hp"]
                    and self.round < len(ROUNDS) - 1 and badge.pressed(BUTTON_SELECT)):
                self.round += 1
                self.start_cpu(self.opponents[self.round], "tournament")
                return
            if self.player["hp"] and self.enemy["hp"]:
                step_fighter(self.player, self.enemy, controls(), badge.pressed(BUTTON_SELECT), dt, self.stage,
                             special)
                distance = self.player["x"] - self.enemy["x"]
                gap = abs(distance)
                toward = -1 if distance <= 0 else 1
                self.ai_decision -= dt
                if self.ai_decision <= 0:
                    self.ai_action = random.choice(("approach", "approach", "guard", "wait", "retreat"))
                    self.ai_decision = 0.35 + random.random() * 0.45
                direction = 0
                move_limit = 0
                if gap < 23:
                    direction, move_limit = -toward, 24 - gap
                elif self.ai_action == "approach" and gap > 26:
                    direction, move_limit = toward, gap - 26
                elif self.ai_action == "retreat" and gap < 34:
                    direction, move_limit = -toward, 34 - gap
                keys = (1 if direction < 0 else 2 if direction > 0 else 0)
                if self.ai_action == "guard":
                    keys |= 4
                self.ai_wait -= dt
                attack = self.ai_wait <= 0 and gap < 27 and self.ai_action in ("approach", "wait")
                if attack:
                    self.ai_wait = 0.7 + random.random() * 0.5
                if self.enemy["hp"]:
                    step_fighter(self.enemy, self.player, keys, attack, dt, self.stage,
                                 attack and self.enemy["meter"] >= 100, move_limit)
        self.draw()

    def draw_flag(self, nation, x, y):
        stripes = (
            None,
            ((245, 245, 240), (210, 45, 54), (245, 245, 240)),
            ((36, 152, 74), (241, 210, 60), (36, 152, 74)),
            ((45, 78, 177), (245, 245, 240), (220, 48, 62)),
            ((190, 41, 52), (245, 245, 240), (190, 41, 52)),
            ((218, 45, 54), (245, 245, 240), (218, 45, 54)),
            ((28, 29, 34), (215, 44, 49), (238, 190, 57)),
            ((35, 155, 87), (245, 245, 240), (220, 48, 62)),
            ((40, 65, 153), (245, 245, 240), (204, 44, 61)),
        )
        colors = stripes[nation]
        if colors is None:
            return
        vertical = nation in (3, 5, 7)
        for i in range(3):
            screen.pen = color.rgb(*colors[i])
            if vertical:
                screen.rectangle(x + i * 2, y, 2, 4)
            else:
                screen.rectangle(x, y + i, 6, 1)

    def draw_fighter(self, f, y, opponent_x=None):
        x = int(f["x"])
        c = f["character"]
        if not (f["guard"] or f["flash"] or f["moving"]):
            y -= (badge.ticks // 450) % 2
        facing = 1 if opponent_x is None or x < opponent_x else -1
        width = (16, 12, 20)[c["body"]]
        half = width // 2
        stride = (5 if (badge.ticks // 160) % 2 else -5) if f["moving"] else 0
        lift = 2 if stride > 0 else -2 if stride < 0 else 0
        shade = tuple(max(0, v - 50) for v in COLORS[c["color"]])
        screen.pen = color.rgb(21, 24, 35)
        screen.rectangle(x - half - 1, y - 22, width + 2, 27)
        screen.rectangle(x - 7, y - 38, 14, 17)
        screen.rectangle(x - half - stride, y + 3 + lift, 6, 9)
        screen.rectangle(x + half - 6 + stride, y + 3 - lift, 6, 9)
        screen.pen = color.rgb(*shade)
        screen.rectangle(x - half, y - 21, width, 25)
        screen.pen = color.rgb(*COLORS[c["color"]])
        screen.rectangle(x - half + 2, y - 19, width - 4, 15)
        if f["hurt"] and (badge.ticks // 70) % 2:
            screen.pen = color.rgb(255, 245, 220)
            screen.rectangle(x - half + 3, y - 17, width - 6, 3)
            screen.pen = color.rgb(*COLORS[c["color"]])
        screen.rectangle(x - half + 1 - stride, y + 3 + lift, 4, 7)
        screen.rectangle(x + half - 5 + stride, y + 3 - lift, 4, 7)
        screen.pen = color.rgb(240, 218, 175)
        screen.rectangle(x - half, y - 5, width, 2)
        screen.pen = color.rgb(255, 213, 171)
        screen.rectangle(x - 6, y - 36, 12, 13)
        screen.pen = color.rgb(197, 138, 107)
        screen.rectangle(x - 6, y - 27, 12, 3)
        screen.rectangle(x + 1, y - 31, 1, 3)
        screen.pen = color.rgb(32, 30, 37)
        screen.rectangle(x - 4, y - 33, 2, 2)
        screen.rectangle(x + 2, y - 33, 2, 2)
        if c["face"] == 0:
            screen.rectangle(x - 2, y - 25, 4, 1)
        elif c["face"] == 1:
            screen.rectangle(x - 3, y - 25, 6, 1)
            screen.rectangle(x - 3, y - 26, 1, 1)
            screen.rectangle(x + 2, y - 26, 1, 1)
        else:
            screen.rectangle(x - 5, y - 35, 4, 1)
            screen.rectangle(x + 1, y - 35, 4, 1)
            screen.rectangle(x - 2, y - 25, 4, 1)
        if c["style"] == 1:
            screen.rectangle(x - 7, y - 39, 14, 4)
            screen.rectangle(x - 7, y - 35, 3, 4)
        elif c["style"] == 2:
            screen.rectangle(x - 7, y - 39, 14, 3)
            screen.pen = color.rgb(245, 245, 230)
            screen.rectangle(x - 7, y - 36, 14, 2)
        self.draw_flag(c["nation"], x - 3, y - 17)
        screen.pen = color.rgb(*shade)
        screen.rectangle(x - half - 4, y - 20, 4, 14)
        screen.rectangle(x + half, y - 20, 4, 14)
        if f["guard"]:
            guard_x = x + facing * (half + 6)
            screen.pen = color.rgb(255, 213, 171)
            screen.rectangle(x + (half - 2 if facing == 1 else -half - 4), y - 21, 6, 6)
            screen.pen = color.rgb(75, 190, 255)
            screen.rectangle(guard_x - 2, y - 29, 5, 24)
            screen.rectangle(guard_x - 5, y - 26, 11, 3)
            screen.rectangle(guard_x - 5, y - 9, 11, 3)
            if f["guard_hit"]:
                screen.pen = color.rgb(255, 240, 120)
                screen.rectangle(guard_x - 7, y - 25, 3, 3)
                screen.rectangle(guard_x + 5, y - 20, 3, 3)
                screen.rectangle(guard_x - 5, y - 12, 3, 3)
        if f["flash"]:
            screen.pen = color.rgb(255, 213, 171)
            screen.rectangle(x + (half if facing == 1 else -half - 8), y - 20, 8, 6)
            screen.pen = color.rgb(255, 245, 160) if not f["special_flash"] else color.rgb(255, 150, 40)
            size = 14 if f["special_flash"] else 7
            screen.rectangle(x + (half + 3 if facing == 1 else -half - 3 - size), y - 18, size, 6)

    def draw_gauge(self, x, y, value, fill, reverse=False):
        screen.pen = color.rgb(25, 30, 42)
        screen.rectangle(x, y, 65, 6)
        width = 63 * value // 100
        if width:
            screen.pen = fill
            screen.rectangle(x + 1 + (63 - width if reverse else 0), y + 1, width, 4)

    def draw(self):
        screen.font = font.nope
        sky = SKIES[self.stage] if self.mode in ("cpu", "host", "guest", "tournament", "tutorial") else (23, 28, 45)
        screen.pen = color.rgb(*sky)
        screen.rectangle(screen.clip)
        screen.pen = color.rgb(255, 255, 255)
        if self.mode == "menu":
            draw_text("時の道場", 56, 8)
            for i, label in enumerate(JP_MENU):
                draw_text(("> " if self.menu == i else "  ") + label, 22, 25 + i * 15)
            draw_text(JP_MESSAGES[self.message], 10, 105)
        elif self.mode == "edit":
            draw_text("キャラ作成", 8, 5)
            labels = ("色 " + str(saved["color"] + 1),
                      "髪 " + str(saved["style"] + 1),
                      "顔 " + str(saved["face"] + 1),
                      "体型 " + str(saved["body"] + 1),
                      "国 " + JP_NATIONS[saved["nation"]],
                      "力 " + str(saved["power"]))
            start = min(max(0, self.row - 1), len(FIELDS) - 3)
            for i in range(start, start + 3):
                draw_text(("> " if self.row == i else "  ") + labels[i], 4, 24 + (i - start) * 15)
            self.draw_fighter(fighter(saved, 132), 65)
            screen.pen = color.rgb(255, 255, 255)
            damage, speed = BONUSES[saved["nation"]]
            draw_text("攻 " + str(6 + saved["power"] * 2 + damage) +
                      " 速 " + str(30 + (6 - saved["power"]) * 5 + speed), 4, 79)
            draw_text("上下: 項目 左右: 変更", 4, 92)
            draw_text("決定: 保存 戻る: 中止", 4, 106)
        elif self.mode == "help":
            draw_text("操作方法", 48, 6)
            draw_text("左右: 移動", 4, 23)
            draw_text("下: ガード", 4, 38)
            draw_text("決定: 攻撃", 4, 53)
            draw_text("上/振る: 必殺技", 4, 68)
            draw_text("SP満タンで全消費", 4, 83)
            draw_text("決定: 開始 戻る: 中止", 4, 106)
        elif self.mode == "link":
            draw_text("バッジ対戦", 40, 15)
            draw_text("バッジを近づけてください", 10, 43)
            draw_text("戻る: 中止", 40, 75)
        else:
            screen.pen = color.rgb(48, 65, 77)
            screen.rectangle(0, 87, screen.width, 33)
            screen.pen = color.rgb(63, 83, 91)
            screen.rectangle(0, 94, screen.width, 2)
            screen.rectangle(0, 111, screen.width, 1)
            screen.pen = color.rgb(35, 46, 56)
            for f in (self.player, self.enemy):
                screen.rectangle(int(f["x"]) - 13, 91, 26, 3)
            if self.stage == 3:
                screen.pen = color.rgb(255, 230, 150)
                screen.rectangle(143, 32, 8, 8)
            self.draw_fighter(self.player, 79, self.enemy["x"])
            self.draw_fighter(self.enemy, 79, self.player["x"])
            screen.pen = color.rgb(255, 255, 255)
            draw_text("自分", 3, 1)
            draw_text("相手", 140, 1)
            self.draw_gauge(3, 12, self.player["hp"], color.rgb(80, 230, 120))
            self.draw_gauge(92, 12, self.enemy["hp"], color.rgb(80, 230, 120), True)
            full = color.rgb(255, 255, 190) if (badge.ticks // 250) % 2 else color.rgb(255, 190, 50)
            blue = color.rgb(50, 180, 255)
            self.draw_gauge(3, 20, self.player["meter"], full if self.player["meter"] == 100 else blue)
            self.draw_gauge(92, 20, self.enemy["meter"], full if self.enemy["meter"] == 100 else blue, True)
            screen.pen = color.rgb(255, 255, 255)
            screen.text("HP", 72, 10)
            screen.text("SP", 72, 19)
            title = JP_STAGES[self.stage] + ("" if self.clock_ok else " ?")
            if self.mode == "tournament":
                title = JP_ROUNDS[self.round]
            elif self.mode == "tutorial":
                title = "練習"
            draw_text(title, 64, 29)
            if self.player["guard_hit"] or self.enemy["guard_hit"]:
                screen.pen = color.rgb(255, 240, 120)
                draw_text("ガード!", 58, 40)
                screen.pen = color.rgb(255, 255, 255)
            if self.mode == "tutorial":
                screen.pen = color.rgb(28, 36, 48)
                screen.rectangle(0, 95, screen.width, 25)
                screen.pen = color.rgb(255, 255, 255)
                draw_text(JP_PROMPTS[self.tutorial_step][0], 4, 96)
                draw_text(JP_PROMPTS[self.tutorial_step][1], 4, 108)
            elif not self.player["hp"] or not self.enemy["hp"]:
                result = "引き分け" if self.player["hp"] == self.enemy["hp"] else ("勝ち" if self.player["hp"] else "負け")
                if self.mode == "tournament" and self.player["hp"] and self.round == len(ROUNDS) - 1:
                    result = "優勝!"
                draw_text(result, 50, 39)
                if self.mode == "tournament" and self.player["hp"] and self.round < len(ROUNDS) - 1:
                    draw_text("決定: 次の試合", 4, 105)
                else:
                    draw_text("戻る: メニュー", 35, 105)


game = Game()


def update():
    game.update()


def on_exit():
    game.close_link()


run(update)
