# -*- coding: utf-8 -*-
"""扶摇主持人工作台 - 数据层与通用工具"""
import os
import sys
import sqlite3
import json
import base64
import hashlib
import logging
import shutil
import zipfile
import tempfile
import datetime

APP_NAME = "主持人工作台"
APP_VERSION = "4.8.2"


def base_dir() -> str:
    """程序根目录：打包后为 exe 所在目录，开发时为脚本目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def open_path(path):
    import subprocess
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif os.name == "nt":
            os.startfile(str(path))
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


def data_dir() -> str:
    """数据目录：打包后放用户本地数据区，避免污染桌面/程序目录；开发时放项目 data"""
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        d = os.path.join(base, "HostWorkbench", "data")
        legacy = os.path.join(base, "FuyaoHostTool", "data")
        if not os.path.exists(d) and os.path.exists(legacy):
            d = legacy
    else:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(d, exist_ok=True)
    return d


def asset_path(name: str) -> str:
    """内置资源路径：打包后从 PyInstaller 解包目录取，开发时取项目 assets"""
    if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None):
        root = sys._MEIPASS
    else:
        root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, "assets", name)


def setup_logging(level_name: str = "INFO"):
    log_dir = os.path.join(data_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level_name.upper(), logging.INFO))
    for h in list(logger.handlers):
        logger.removeHandler(h)
    fh = logging.FileHandler(os.path.join(log_dir, "app.log"), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(sh)


DB_PATH = os.path.join(data_dir(), "host.db")


class DB:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.init_tables()

    def init_tables(self):
        c = self.conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            client TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            venue TEXT DEFAULT '',
            time_slot TEXT DEFAULT '',
            fee TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            region TEXT DEFAULT '',
            created TEXT DEFAULT ''
        )""")
        # 兼容旧版数据库：补 region 列
        try:
            cols = [r["name"] for r in c.execute("PRAGMA table_info(events)").fetchall()]
            for _col in ("region", "company", "deposit"):
                if _col not in cols:
                    c.execute("ALTER TABLE events ADD COLUMN %s TEXT DEFAULT ''" % _col)
        except Exception:
            pass
        c.execute("""CREATE TABLE IF NOT EXISTS memos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due TEXT DEFAULT '',
            category TEXT DEFAULT '',
            important INTEGER DEFAULT 0,
            done INTEGER DEFAULT 0,
            created TEXT DEFAULT ''
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS prep_templates(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            path TEXT,
            builtin INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS prep_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT DEFAULT '婚礼物品',
            name TEXT DEFAULT '',
            qty TEXT DEFAULT '',
            done INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            sort INTEGER DEFAULT 0,
            created TEXT DEFAULT ''
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS prep_people(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            role TEXT DEFAULT '',
            note TEXT DEFAULT '',
            project TEXT DEFAULT '',
            headcount TEXT DEFAULT '',
            event TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            person TEXT DEFAULT '',
            sort INTEGER DEFAULT 0,
            created TEXT DEFAULT ''
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS prep_flow(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT DEFAULT '',
            title TEXT DEFAULT '',
            content TEXT DEFAULT '',
            note TEXT DEFAULT '',
            sort INTEGER DEFAULT 0,
            created TEXT DEFAULT ''
        )""")
        # 兼容旧库：流程补「地点 / 指定音乐」列
        try:
            cols = [r["name"] for r in c.execute("PRAGMA table_info(prep_flow)").fetchall()]
            for _col in ("location", "music", "content"):
                if _col not in cols:
                    c.execute("ALTER TABLE prep_flow ADD COLUMN %s TEXT DEFAULT ''" % _col)
        except Exception:
            pass
        # 兼容旧库：人员清单增加 项目/人数/负责事件/说明/负责人
        try:
            cols = [r["name"] for r in c.execute("PRAGMA table_info(prep_people)").fetchall()]
            for _col in ("project", "headcount", "event", "detail", "person"):
                if _col not in cols:
                    c.execute("ALTER TABLE prep_people ADD COLUMN %s TEXT DEFAULT ''" % _col)
            c.execute("UPDATE prep_people SET person=name WHERE COALESCE(person,'')=''")
            c.execute("UPDATE prep_people SET event=role WHERE COALESCE(event,'')=''")
            c.execute("UPDATE prep_people SET detail=note WHERE COALESCE(detail,'')=''")
            c.execute("UPDATE prep_people SET project=role WHERE COALESCE(project,'')='' AND COALESCE(role,'')<>''")
        except Exception:
            pass
        c.execute("""CREATE TABLE IF NOT EXISTS prep_docs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT DEFAULT '',
            path TEXT DEFAULT '',
            text TEXT DEFAULT '',
            created TEXT DEFAULT ''
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS questionnaires(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '',
            couple TEXT DEFAULT '',
            wedding_date TEXT DEFAULT '',
            venue TEXT DEFAULT '',
            template_name TEXT DEFAULT '',
            template_path TEXT DEFAULT '',
            template_text TEXT DEFAULT '',
            form_url TEXT DEFAULT '',
            qr_path TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created TEXT DEFAULT '',
            updated TEXT DEFAULT ''
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS questionnaire_submissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            questionnaire_id INTEGER NOT NULL,
            guest_name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            answers_json TEXT DEFAULT '{}',
            remote_hash TEXT DEFAULT '',
            created TEXT DEFAULT ''
        )""")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_qsub_hash ON questionnaire_submissions(questionnaire_id, remote_hash)")
        self._seed_prep(c)
        self.conn.commit()

    def _seed_prep(self, c):
        """首次运行时写入一份可编辑的备婚清单"""
        if c.execute("SELECT COUNT(*) n FROM prep_items").fetchone()["n"] > 0:
            return
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        items = [
            ("婚礼物品", "喜糖 / 伴手礼", "按人数 +20 份", ""),
            ("婚礼物品", "请柬 / 电子请帖", "按宾客数", ""),
            ("婚礼物品", "签到本 + 签到笔", "2 套", ""),
            ("婚礼物品", "席位卡 / 桌卡", "按桌数", ""),
            ("婚礼物品", "婚戒 + 戒枕", "1 对", ""),
            ("婚礼物品", "胸花 / 手腕花", "按人员", ""),
            ("婚礼物品", "敬酒服 / 香槟酒", "2 瓶", ""),
            ("婚礼物品", "红包 / 改口红包", "按习俗", ""),
            ("婚礼物品", "鲜花（手捧 / 桌花）", "按场布", ""),
            ("婚礼物品", "音响 / 备用电池", "1 套", ""),
            ("婚礼物品", "主持手卡 / 流程单", "3 份", ""),
            ("婚礼物品", "雨伞 / 应急针线包", "1 套", ""),
        ]
        for i, (cat, name, qty, note) in enumerate(items):
            c.execute("INSERT INTO prep_items(category,name,qty,note,sort,created) VALUES(?,?,?,?,?,?)",
                      (cat, name, qty, note, i, now))
        people = [
            ("主持人", "", "全场主持 / 串场", ""),
            ("婚礼督导", "", "流程执行 / 催场", ""),
            ("音控师", "", "音乐 / 话筒", ""),
            ("灯光师", "", "灯光 / 追光", ""),
            ("摄影师", "", "跟拍 / 合影", ""),
            ("摄像师", "", "全程录像", ""),
            ("化妆师", "", "新娘妆 / 补妆", ""),
            ("伴郎", "", "开门 / 递戒指", ""),
            ("伴娘", "", "裙摆 / 手捧花", ""),
        ]
        for i, (name, phone, role, note) in enumerate(people):
            c.execute("INSERT INTO prep_people(project,headcount,event,detail,person,phone,name,role,note,sort,created) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (role, "", role, note, name, phone, name, role, note, i, now))
        flow = [
            ("09:00", "新娘化妆 / 新郎准备", "化妆师、伴娘到位"),
            ("13:00", "场布验收", "督导核对桌数、席位卡、音响"),
            ("14:30", "彩排", "新人、伴郎伴娘、督导走位"),
            ("15:30", "迎宾 / 签到", "签到本、伴手礼就位"),
            ("16:28", "暖场 / 开场提示", "音控确认 BGM"),
            ("16:35", "新人入场", "追光、花瓣、音乐 cue"),
            ("17:00", "仪式环节", "宣誓、交换戒指、感恩父母"),
            ("17:40", "敬酒", "按桌序进行，督导引导"),
            ("19:30", "送客 / 收尾", "清点物品、结算尾款"),
        ]
        for i, (t, title, note) in enumerate(flow):
            c.execute("INSERT INTO prep_flow(time,title,note,sort,created) VALUES(?,?,?,?,?)",
                      (t, title, note, i, now))

    # ---------- 备婚清单 ----------
    def prep_items(self, category=None):
        q = "SELECT * FROM prep_items"
        args = ()
        if category:
            q += " WHERE category=?"
            args = (category,)
        q += " ORDER BY sort, id"
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def prep_add_item(self, category="婚礼物品", name="", qty="", note=""):
        c = self.conn.cursor()
        n = c.execute("SELECT COALESCE(MAX(sort),-1)+1 s FROM prep_items").fetchone()["s"]
        c.execute("INSERT INTO prep_items(category,name,qty,note,sort,created) VALUES(?,?,?,?,?,?)",
                  (category, name, qty, note, n,
                   datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.conn.commit()
        return c.lastrowid

    def prep_update_item(self, iid, **kw):
        fields = ("category", "name", "qty", "done", "note")
        cur = dict(self.conn.execute("SELECT * FROM prep_items WHERE id=?", (iid,)).fetchone())
        cur.update({k: v for k, v in kw.items() if k in fields})
        self.conn.execute("UPDATE prep_items SET category=?, name=?, qty=?, done=?, note=? WHERE id=?",
                          (cur["category"], cur["name"], cur["qty"], cur["done"], cur["note"], iid))
        self.conn.commit()

    def prep_delete_item(self, iid):
        self.conn.execute("DELETE FROM prep_items WHERE id=?", (iid,))
        self.conn.commit()

    def prep_people(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM prep_people ORDER BY sort, id").fetchall()]

    def prep_add_person(self, project="", headcount="", event="", detail="", person="", phone=""):
        c = self.conn.cursor()
        n = c.execute("SELECT COALESCE(MAX(sort),-1)+1 s FROM prep_people").fetchone()["s"]
        c.execute("INSERT INTO prep_people(project,headcount,event,detail,person,phone,name,role,note,sort,created) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (project, headcount, event, detail, person, phone,
                   person, event, detail, n,
                   datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.conn.commit()
        return c.lastrowid

    def prep_update_person(self, pid, **kw):
        fields = ("project", "headcount", "event", "detail", "person", "phone",
                  "name", "role", "note")
        cur = dict(self.conn.execute("SELECT * FROM prep_people WHERE id=?", (pid,)).fetchone())
        cur.update({k: v for k, v in kw.items() if k in fields})
        sets = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE prep_people SET {sets} WHERE id=?",
                          (*(cur[k] for k in fields), pid))
        self.conn.commit()

    def prep_delete_person(self, pid):
        self.conn.execute("DELETE FROM prep_people WHERE id=?", (pid,))
        self.conn.commit()

    def prep_flow(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM prep_flow ORDER BY sort, id").fetchall()]

    def prep_add_flow(self, time="", title="", content="", location="", note="", music=""):
        c = self.conn.cursor()
        n = c.execute("SELECT COALESCE(MAX(sort),-1)+1 s FROM prep_flow").fetchone()["s"]
        c.execute("INSERT INTO prep_flow(time,title,content,note,location,music,sort,created) "
                  "VALUES(?,?,?,?,?,?,?,?)",
                  (time, title, content, note, location, music, n,
                   datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.conn.commit()
        return c.lastrowid

    def prep_update_flow(self, fid, **kw):
        fields = ("time", "title", "content", "note", "location", "music")
        cur = dict(self.conn.execute("SELECT * FROM prep_flow WHERE id=?", (fid,)).fetchone())
        cur.update({k: v for k, v in kw.items() if k in fields})
        self.conn.execute(
            "UPDATE prep_flow SET time=?, title=?, content=?, note=?, location=?, music=? WHERE id=?",
            (cur["time"], cur["title"], cur.get("content", ""), cur["note"], cur.get("location", ""),
             cur.get("music", ""), fid))
        self.conn.commit()

    def prep_set_order(self, table, ids):
        """按给定 id 顺序重排 sort（多选上移/下移用）"""
        for i, rid in enumerate(ids):
            self.conn.execute(f"UPDATE {table} SET sort=? WHERE id=?", (i, rid))
        self.conn.commit()

    def prep_delete_flow(self, fid):
        self.conn.execute("DELETE FROM prep_flow WHERE id=?", (fid,))
        self.conn.commit()

    def prep_move(self, table, rid, delta):
        """在同类清单里上移/下移一行"""
        rows = [dict(r) for r in self.conn.execute(
            f"SELECT id, sort FROM {table} ORDER BY sort, id").fetchall()]
        idx = next((i for i, r in enumerate(rows) if r["id"] == rid), -1)
        if idx < 0:
            return
        j = idx + delta
        if j < 0 or j >= len(rows):
            return
        a, b = rows[idx], rows[j]
        self.conn.execute(f"UPDATE {table} SET sort=? WHERE id=?", (b["sort"], a["id"]))
        self.conn.execute(f"UPDATE {table} SET sort=? WHERE id=?", (a["sort"], b["id"]))
        self.conn.commit()

    # ---------- 备婚文档 ----------
    def prep_docs(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM prep_docs ORDER BY id DESC").fetchall()]

    def prep_add_doc(self, name, text, path=""):
        c = self.conn.cursor()
        c.execute("INSERT INTO prep_docs(name,path,text,created) VALUES(?,?,?,?)",
                  (name, path, text, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.conn.commit()
        return c.lastrowid

    def prep_update_doc(self, did, text):
        self.conn.execute("UPDATE prep_docs SET text=? WHERE id=?", (text, did))
        self.conn.commit()

    def prep_delete_doc(self, did):
        self.conn.execute("DELETE FROM prep_docs WHERE id=?", (did,))
        self.conn.commit()

    # ---------- 档期 ----------
    def events_on(self, date_str: str):
        cur = self.conn.execute("SELECT * FROM events WHERE date=? ORDER BY time_slot", (date_str,))
        return [dict(r) for r in cur.fetchall()]

    def events_between(self, d1: str, d2: str):
        cur = self.conn.execute("SELECT * FROM events WHERE date>=? AND date<=? ORDER BY date, time_slot", (d1, d2))
        return [dict(r) for r in cur.fetchall()]

    def events_all(self):
        cur = self.conn.execute("SELECT * FROM events ORDER BY date")
        return [dict(r) for r in cur.fetchall()]

    def event_counts_month(self, year: int, month: int) -> dict:
        prefix = f"{year:04d}-{month:02d}"
        cur = self.conn.execute("SELECT date, COUNT(*) n FROM events WHERE date LIKE ? GROUP BY date", (prefix + "%",))
        return {r["date"]: r["n"] for r in cur.fetchall()}

    def add_event(self, **kw) -> int:
        c = self.conn.cursor()
        c.execute("""INSERT INTO events(date, client, phone, venue, time_slot, fee, notes, region, company, deposit, created)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                  (kw.get("date", ""), kw.get("client", ""), kw.get("phone", ""),
                   kw.get("venue", ""), kw.get("time_slot", ""), kw.get("fee", ""),
                   kw.get("notes", ""), kw.get("region", ""), kw.get("company", ""),
                   kw.get("deposit", ""),
                   datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.conn.commit()
        return c.lastrowid

    def update_event(self, eid: int, **kw):
        c = self.conn.cursor()
        c.execute("""UPDATE events SET date=?, client=?, phone=?, venue=?, time_slot=?, fee=?, notes=?, region=?, company=?, deposit=? WHERE id=?""",
                  (kw.get("date", ""), kw.get("client", ""), kw.get("phone", ""), kw.get("venue", ""),
                   kw.get("time_slot", ""), kw.get("fee", ""), kw.get("notes", ""),
                   kw.get("region", ""), kw.get("company", ""), kw.get("deposit", ""), eid))
        self.conn.commit()

    def delete_event(self, eid: int):
        self.conn.execute("DELETE FROM events WHERE id=?", (eid,))
        self.conn.commit()

    # ---------- 备忘 ----------
    def memos_all(self, only_open=False):
        q = "SELECT * FROM memos"
        if only_open:
            q += " WHERE done=0"
        q += " ORDER BY important DESC, due ASC, id DESC"
        cur = self.conn.execute(q)
        return [dict(r) for r in cur.fetchall()]

    def add_memo(self, title, due="", category="", important=0) -> int:
        c = self.conn.cursor()
        c.execute("INSERT INTO memos(title, due, category, important, done, created) VALUES(?,?,?,?,0,?)",
                  (title, due, category, important, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.conn.commit()
        return c.lastrowid

    def update_memo(self, mid, **kw):
        fields = []
        vals = []
        for k in ("title", "due", "category", "important", "done"):
            if k in kw:
                fields.append(f"{k}=?")
                vals.append(kw[k])
        if not fields:
            return
        vals.append(mid)
        self.conn.execute(f"UPDATE memos SET {', '.join(fields)} WHERE id=?", vals)
        self.conn.commit()

    def delete_memo(self, mid):
        self.conn.execute("DELETE FROM memos WHERE id=?", (mid,))
        self.conn.commit()

    def due_memos(self, now_str: str):
        cur = self.conn.execute("SELECT * FROM memos WHERE done=0 AND due != '' AND due<=? ORDER BY due", (now_str,))
        return [dict(r) for r in cur.fetchall()]

    # ---------- 设置 ----------
    def get_setting(self, key, default=""):
        cur = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row["value"] if row else default

    def set_setting(self, key, value):
        self.conn.execute("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=?",
                          (key, str(value), str(value)))
        self.conn.commit()

    def stats(self):
        cur = self.conn.execute("SELECT COUNT(*) n FROM events")
        total = cur.fetchone()["n"]
        cur = self.conn.execute("SELECT COUNT(*) n FROM memos WHERE done=0")
        open_memo = cur.fetchone()["n"]
        return {"events": total, "open_memos": open_memo}

    # ---------- 年度统计 ----------
    # ---------- 客户问卷 ----------
    def questionnaires(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM questionnaires ORDER BY wedding_date DESC, id DESC").fetchall()]

    def questionnaire(self, qid):
        r = self.conn.execute("SELECT * FROM questionnaires WHERE id=?", (qid,)).fetchone()
        return dict(r) if r else None

    def add_questionnaire(self, data: dict) -> int:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        c = self.conn.execute(
            """INSERT INTO questionnaires(title,couple,wedding_date,venue,template_name,template_path,
               template_text,form_url,qr_path,notes,created,updated)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data.get("title", ""), data.get("couple", ""), data.get("wedding_date", ""),
             data.get("venue", ""), data.get("template_name", ""), data.get("template_path", ""),
             data.get("template_text", ""), data.get("form_url", ""), data.get("qr_path", ""),
             data.get("notes", ""), now, now))
        self.conn.commit()
        return int(c.lastrowid)

    def update_questionnaire(self, qid, **kw):
        if not kw:
            return
        allowed = {"title", "couple", "wedding_date", "venue", "template_name", "template_path",
                   "template_text", "form_url", "qr_path", "notes"}
        fields = [k for k in kw if k in allowed]
        if not fields:
            return
        sets = ",".join(f"{k}=?" for k in fields)
        args = [kw[k] for k in fields] + [datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), qid]
        self.conn.execute(f"UPDATE questionnaires SET {sets},updated=? WHERE id=?", args)
        self.conn.commit()

    def delete_questionnaire(self, qid):
        self.conn.execute("DELETE FROM questionnaire_submissions WHERE questionnaire_id=?", (qid,))
        self.conn.execute("DELETE FROM questionnaires WHERE id=?", (qid,))
        self.conn.commit()

    def questionnaire_submissions(self, qid):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM questionnaire_submissions WHERE questionnaire_id=? ORDER BY id DESC", (qid,)).fetchall()]

    def add_questionnaire_submission(self, qid, guest_name, phone, answers: dict, remote_hash: str) -> bool:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        c = self.conn.execute(
            """INSERT OR IGNORE INTO questionnaire_submissions
               (questionnaire_id,guest_name,phone,answers_json,remote_hash,created)
               VALUES(?,?,?,?,?,?)""",
            (qid, guest_name, phone, json.dumps(answers, ensure_ascii=False), remote_hash, now))
        self.conn.commit()
        return c.rowcount > 0

    def stats_year(self, year: int) -> dict:
        prefix = f"{year}-"
        rows = self.conn.execute(
            "SELECT region, fee, date FROM events WHERE date LIKE ?", (prefix + "%",)).fetchall()
        total_fee = 0.0
        regions = {"市区": 0, "省内": 0, "省外": 0, "未填": 0}
        monthly = [0] * 12
        for r in rows:
            fee = _parse_money(r["fee"])
            total_fee += fee
            reg = (r["region"] or "").strip()
            regions[reg if reg in regions else "未填"] += 1
            try:
                m = int(r["date"][5:7])
                monthly[m - 1] += 1
            except Exception:
                pass
        return {
            "year": year,
            "count": len(rows),
            "income": total_fee,
            "regions": regions,
            "monthly": monthly,
        }

    def income_by_year(self) -> dict:
        rows = self.conn.execute("SELECT date, fee FROM events").fetchall()
        out = {}
        for r in rows:
            y = (r["date"] or "")[:4]
            if not y.isdigit():
                continue
            out[y] = out.get(y, 0.0) + _parse_money(r["fee"])
        return out


# ---------------- 全局设置（模块级便捷函数） ----------------
_shared_db_obj = None


def _shared():
    global _shared_db_obj
    if _shared_db_obj is None:
        _shared_db_obj = DB()
    return _shared_db_obj


def default_backup_dir() -> str:
    """默认备份目录：Windows 为 D:\主持人工作台，macOS 为 ~/Documents/主持人工作台数据"""
    if sys.platform == "darwin":
        d = os.path.join(os.path.expanduser("~"), "Documents", "主持人工作台数据")
    else:
        d = os.path.join("D:" + os.sep, "主持人工作台")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        d = os.path.join(data_dir(), "backups")
        os.makedirs(d, exist_ok=True)
    return d


def get_setting(key: str, default: str = "") -> str:
    try:
        return _shared().get_setting(key, default)
    except Exception:
        return default


def set_setting(key: str, value: str):
    try:
        _shared().set_setting(key, value)
    except Exception:
        pass


# ---------------- 工具 ----------------
def _parse_money(text) -> float:
    """从文本中解析金额：支持 '3000'、'￥3,000'、'3000元' 等"""
    if text is None:
        return 0.0
    s = str(text).strip().replace(",", "").replace("，", "")
    buf = []
    for ch in s:
        if ch.isdigit() or ch == ".":
            buf.append(ch)
        elif buf:
            break
    try:
        return float("".join(buf)) if buf else 0.0
    except Exception:
        return 0.0


def configure_ffmpeg():
    """让 pydub 使用内置 ffmpeg（打包后位于 assets/ffmpeg.exe）"""
    try:
        from pydub import AudioSegment
        candidates = [
            asset_path("ffmpeg.exe"),
            os.path.join(os.path.dirname(sys.executable), "assets", "ffmpeg.exe"),
        ]
        for p in candidates:
            if os.path.exists(p):
                AudioSegment.converter = p
                AudioSegment.ffmpeg = p
                return p
        # 开发环境：用 imageio_ffmpeg 提供的二进制
        try:
            import imageio_ffmpeg
            p = imageio_ffmpeg.get_ffmpeg_exe()
            if os.path.exists(p):
                AudioSegment.converter = p
                AudioSegment.ffmpeg = p
                return p
        except Exception:
            pass
        return None
    except Exception:
        return None


# ---------------- 加密备份 ----------------
def _derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000, dklen=32)


def export_backup(password: str, out_path: str) -> str:
    """将数据库与配置打包并用 AES-GCM 加密（自带 salt/nonce）"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    tmpd = tempfile.mkdtemp()
    try:
        zip_path = os.path.join(tmpd, "backup.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(DB_PATH, "host.db")
            cfg = os.path.join(data_dir(), "settings_export.json")
            with open(cfg, "w", encoding="utf-8") as f:
                f.write(json.dumps({"exported": datetime.datetime.now().isoformat()}, ensure_ascii=False))
            z.write(cfg, "meta.json")
        with open(zip_path, "rb") as f:
            raw = f.read()
        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = _derive_key(password, salt)
        enc = AESGCM(key).encrypt(nonce, raw, None)
        blob = salt + nonce + enc
        with open(out_path, "wb") as f:
            f.write(blob)
        return out_path
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def import_backup(path: str, password: str) -> bool:
    """解密备份并覆盖数据库；失败返回 False"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    with open(path, "rb") as f:
        blob = f.read()
    if len(blob) < 44:
        return False
    salt, nonce, enc = blob[:16], blob[16:28], blob[28:]
    key = _derive_key(password, salt)
    try:
        raw = AESGCM(key).decrypt(nonce, enc, None)
    except Exception:
        return False
    tmpd = tempfile.mkdtemp()
    try:
        zp = os.path.join(tmpd, "b.zip")
        with open(zp, "wb") as f:
            f.write(raw)
        with zipfile.ZipFile(zp) as z:
            names = z.namelist()
            if "host.db" not in names:
                return False
            backup_now = DB_PATH + ".bak_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            if os.path.exists(DB_PATH):
                shutil.copy2(DB_PATH, backup_now)
            z.extract("host.db", tmpd)
            shutil.copy2(os.path.join(tmpd, "host.db"), DB_PATH)
        return True
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


# ---------------- 整体数据导出 / 导入（无密码） ----------------
AUTO_KEEP = 3


def _skip_export(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if any(p in ("logs", "__pycache__", "backups", "selftest") for p in parts):
        return True
    low = rel.lower()
    return low.endswith((".log", ".tmp", ".pyc"))


def export_all(out_path: str) -> str:
    """把整个数据目录打包成 zip（含数据库、设置、模板、主持词等），不加密。"""
    root = data_dir()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ("logs", "__pycache__", "backups", "selftest")]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root)
                if _skip_export(rel):
                    continue
                z.write(full, rel)
        z.writestr("manifest.json", json.dumps({
            "app": APP_NAME, "version": APP_VERSION,
            "exported": datetime.datetime.now().isoformat(timespec="seconds"),
            "kind": "full-data",
        }, ensure_ascii=False, indent=2))
    return out_path


def import_all(zip_path: str) -> bool:
    """导入整体数据包，覆盖当前数据；导入前自动备份当前 host.db。"""
    try:
        if not zipfile.is_zipfile(zip_path):
            # 兼容 4.8.1 之前的加密 .fhbackup（旧备份无密码）
            return import_backup(zip_path, "")
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            if "host.db" not in names and "manifest.json" not in names:
                return False
            root = data_dir()
            if os.path.exists(DB_PATH):
                shutil.copy2(DB_PATH, DB_PATH + ".before_import_" +
                             datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
            tmp = tempfile.mkdtemp()
            try:
                z.extractall(tmp)
                for dirpath, _dirs, files in os.walk(tmp):
                    for fn in files:
                        src = os.path.join(dirpath, fn)
                        rel = os.path.relpath(src, tmp)
                        if rel == "manifest.json":
                            continue
                        dst = os.path.join(root, rel)
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        return True
    except Exception:
        return False


def _prune_auto_backups(folder: str, keep: int = AUTO_KEEP):
    try:
        files = [os.path.join(folder, f) for f in os.listdir(folder)
                 if f.startswith("主持人工作台数据_") and f.lower().endswith(".zip")]
        files.sort(key=os.path.getmtime, reverse=True)
        for f in files[keep:]:
            try:
                os.remove(f)
            except Exception:
                pass
    except Exception:
        pass


def auto_backup_if_due(force: bool = False) -> str:
    """距上次自动备份 >=24 小时则导出一次，保留最新 3 份；返回新文件或空串。"""
    folder = get_setting("backup_dir", "") or default_backup_dir()
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        folder = default_backup_dir()
    last = get_setting("auto_backup_last", "")
    now = datetime.datetime.now()
    if not force and last:
        try:
            prev = datetime.datetime.fromisoformat(last)
            if (now - prev).total_seconds() < 24 * 3600:
                return ""
        except Exception:
            pass
    name = "主持人工作台数据_" + now.strftime("%Y%m%d_%H%M%S") + ".zip"
    out = os.path.join(folder, name)
    try:
        export_all(out)
        set_setting("auto_backup_last", now.isoformat(timespec="seconds"))
        _prune_auto_backups(folder, AUTO_KEEP)
        return out
    except Exception:
        return ""


# ---------------- AI 调用 ----------------
def call_ai(base_url: str, api_key: str, model: str, prompt: str, timeout=90) -> str:
    """OpenAI 兼容接口调用"""
    import requests
    base = base_url.rstrip("/")
    if not base.endswith("/v1"):
        url = base + "/v1/chat/completions"
    else:
        url = base + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model or "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "stream": False,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]

