import re
from difflib import SequenceMatcher


class ChangeGroup(object):
    WORD_CAP = 3
    LINE_CAP = 1
    CAP_FILL = ["[...]"]
    first = False
    last = False

    def __init__(self, state, parts):
        self.state = state
        self.parts = parts

    def __len__(self):
        return len(self.parts)

    def brief_parts(self, joiner):
        cap = joiner == " " and self.WORD_CAP or self.LINE_CAP
        if self.state == "equal" and len(self) > cap + 1:
            if self.first:
                return self.CAP_FILL + self.parts[-cap:]
            elif self.last:
                return self.parts[:cap] + self.CAP_FILL
            elif len(self) > (cap * 2) + 1:
                return self.parts[:cap] + self.CAP_FILL + self.parts[-cap:]
        return self.parts

    def get_html(self, joiner, brief=False):
        txt = joiner.join(brief and self.brief_parts(joiner) or self.parts)
        if self.state == "insert":
            return '<span class="text-diff-added">{0}</span>'.format(txt)
        if self.state == "delete":
            return '<span class="text-diff-removed">{0}</span>'.format(txt)
        return txt


class Changes(object):
    WHITESPACES = re.compile("\s+", re.UNICODE)
    FIRST_TAG = re.compile(r"^(#\w+)", re.UNICODE)
    BULLETS = "•*→-‐‑‒–—―‣"

    def __init__(self, orig: str, changed: str):
        self.differ = SequenceMatcher()
        self.stripped_tag = ""
        self.has_lines = self.check_bullet_list(orig)
        self.orig = self.split(orig)
        # self.changed = self.split(self.has_lines and changed or changed.replace('\n', ' ⏎<br/> '))
        self.changed = self.split(self.strip_tag(changed, orig))
        self.change_groups = list()
        self.do_compare()

    def strip_tag(self, changed: str, orig: str) -> str:
        orig_match = self.FIRST_TAG.search(orig)

        def sub_tag(match):
            tag = match.group(1)
            if not orig_match or tag != orig_match.group(0):
                self.stripped_tag = tag + " "
                return ""
            return tag

        return self.FIRST_TAG.sub(sub_tag, changed).strip()

    @staticmethod
    def check_bullet_list(text: str) -> bool:
        lines = text.splitlines()
        if len(lines) > 1:
            return any(line.strip()[0] in Changes.BULLETS for line in lines)

    @property
    def joiner(self):
        return self.has_lines and "\n" or " "

    def split(self, txt):
        return (
            self.has_lines
            and txt.splitlines()
            or self.WHITESPACES.split(txt.replace("\n", " <br/> "))
        )

    def join(self, groups, brief, no_deleted) -> str:
        if no_deleted:
            groups = filter(lambda g: g.state != "delete", groups)
        return self.joiner.join(
            [cg.get_html(self.joiner, brief=brief) for cg in groups]
        )

    def add_change_group(self, state, astart, aend, bstart, bend):
        if state == "insert":
            parts = self.changed[bstart:bend]
        else:  # 'delete' och 'equal'
            parts = self.orig[astart:aend]
        self.change_groups.append(ChangeGroup(state, parts))

    def do_compare(self):
        self.differ.set_seqs(self.orig, self.changed)
        for opcode in self.differ.get_opcodes():
            state, positions = opcode[0], opcode[1:]
            if state == "replace":
                self.add_change_group("delete", *positions)
                self.add_change_group("insert", *positions)
            else:
                self.add_change_group(*opcode)
        if self.change_groups:
            self.change_groups[0].first = True
            self.change_groups[-1].last = True

    def get_html(self, brief=False, no_deleted=False) -> str:
        return self.stripped_tag + self.join(self.change_groups, brief, no_deleted)
