# Bilingual facade over the two native keyword-spotting modules.
#
#   import openkws
#   eng = openkws.Engine("en", "/sdcard/examples/31-OPEN-KWS/")
#   for kw_id, score, th, start_ms, end_ms, weakest in eng.push(pcm):
#       ...
#
# Chinese wake words run through open_kws (59 initial/final units) and English
# ones through open_kws_en (42 ARPAbet units). The two models are trained on
# different unit inventories, so their kmodels, frontend constants and enroll
# files are NOT interchangeable and no attempt is made to unify them. What this
# module unifies is only the surface: one object, one set of method names, one
# event shape, so an application can switch language with a parameter.
#
# Everything language specific is data, held in PROFILES below: asset paths,
# the calibrated verification thresholds and sensitivity tiers, and the way a
# unit sequence is rendered for display. Those numbers were calibrated per
# language and must not be shared -- see each profile's comments.
#
# Only one engine is alive at a time. Switching language means close() on the
# old one and a new Engine(); the kmodel of the old language is released back
# to the KPU pool, so peak memory stays at a single model.

import os

# ---------------------------------------------------------------- native modules

_NATIVE = {}
for _lang, _name in (("zh", "open_kws"), ("en", "open_kws_en")):
    try:
        _NATIVE[_lang] = __import__(_name)
    except ImportError as e:
        # A Kconfig option can leave either module out of the firmware; the
        # application then simply offers fewer languages.
        print("openkws: %s not in this firmware (%s)" % (_name, e))

LANGS = ("zh", "en")


def available():
    """Languages this firmware can actually run, in LANGS order."""
    return tuple(l for l in LANGS if l in _NATIVE)


# ---------------------------------------------------------------- profiles

# Per-language constants. The sensitivity tiers are (label, threshold bias,
# n_hyps, alpha, delta) and feed set_sensitivity() + set_verify(); a trigger
# needs
#   score > threshold + bias                                  (first stage)
#   max over n_hyps hypotheses of the weakest syllable
#       + alpha * (score - threshold) > verify_th + delta      (second stage)
PROFILES = {
    "zh": {
        "label": "中文",
        "n_units": 59,
        "model": "zh/model/kws.kmodel",
        "assets": "zh/assets",
        "units": "zh/units.txt",
        "langpack": None,                 # syllables follow from the unit ids
        "enroll_dir": "enroll/zh/",
        # Calibrated for the Chinese model. -3.0 is its weakest-syllable cut.
        "verify_threshold": -3.0,
        "tiers": (("灵敏", -0.15, 8, 0.0, 0.0),
                  ("正常", 0.0, 8, 2.0, 1.25),
                  ("保守", 0.15, 3, 2.0, 1.25)),
        "default_tier": 1,
        "min_dur": 0.6,
    },
    "en": {
        "label": "English",
        "n_units": 42,
        "model": "en/model/kws_en.kmodel",
        "assets": "en/assets",
        "units": "en/units_en.txt",
        "langpack": "en/assets/langpack_en.json",
        "enroll_dir": "enroll/en/",
        # MUST stay -6.0, not the Chinese -3.0: English weak forms put true
        # wake-ups as low as -4.33, so -3.0 rejects about 5% of them. The
        # figure comes from the English model's calibration, not from taste.
        "verify_threshold": -6.0,
        # Only "Normal" is the measured configuration: 64/64 on the K230
        # positives, 1/64 on "Hey Ken-" prefixes. The other two tiers are
        # reasoned from the same data, not independently evaluated.
        "tiers": (("Sensitive", -0.15, 8, 0.0, 0.0),
                  ("Normal", 0.0, 1, 0.0, 0.0),
                  ("Conservative", 0.15, 1, 0.0, 1.4)),
        "default_tier": 1,
        "min_dur": 0.5,
    },
}

# Recording quality limits, identical for both languages. The native default
# clip ratio (1e-3) is too strict for the K230 microphone, which clips ~0.35%
# of samples on a normal take.
CLIP_RATIO_MAX = 0.005

# The SNR gate is a floor, not a quality bar. At 10 dB -- the native default --
# a normal room with a fan or a street outside rejects most takes, and the user
# cannot enrol anything at all. Below 3 dB the loud frames carry barely twice
# the energy of the noise, so the decode is junk and accepting it would only
# produce a wake word that never fires; that case stays rejected. Between the
# two the take is accepted and the app warns, which is the user's call to make.
MIN_SNR_DB = 3.0
WARN_SNR_DB = 10.0


# ---------------------------------------------------------------- helpers

def ensure_dir(path):
    """mkdir -p for a trailing-slash directory path. The enroll directories are
    nested (enroll/zh, enroll/en) and MicroPython's os has no makedirs, so a
    plain mkdir would fail whenever the parent is missing."""
    parts = [p for p in path.split("/") if p]
    cur = "/" if path.startswith("/") else ""
    for p in parts:
        cur = cur + p if cur in ("", "/") else cur + "/" + p
        try:
            os.mkdir(cur)
        except OSError:
            pass            # already there, or a parent we are not allowed to make


def _read_units(path):
    try:
        with open(path) as f:
            return [l.split()[0] for l in f if l.strip()]
    except OSError:
        return None


def _sha1_12(path):
    """First 12 hex digits of the unit table, the fingerprint stored in every
    enroll file so a record can never be loaded against the wrong inventory."""
    try:
        import hashlib
        with open(path, "rb") as f:
            h = hashlib.sha1(f.read()).digest()
        return "".join("%02x" % b for b in h)[:12]
    except Exception as e:
        print("openkws: units_sha1 unavailable (%s)" % e)
        return None


def _read_langpack(path, units):
    """(nuclei ids, onset id lists, min_nuclei, min_units) or None. Only the
    English enroller uses it; the native module carries the same table as a
    fallback, so a missing file is not fatal."""
    if not units:
        return None
    try:
        import json
        with open(path) as f:
            lp = json.load(f)
        u2i = {u: i for i, u in enumerate(units)}
        nuclei = [u2i[s] for s in lp["nuclei"] if s in u2i]
        onsets = []
        for o in lp["onsets"]:
            syms = o.split()
            ids = [u2i[s] for s in syms if s in u2i]
            if len(ids) == len(syms):
                onsets.append(ids)
        gate = lp.get("gate", {})
        if not nuclei:
            return None
        return nuclei, onsets, int(gate.get("min_nuclei", 3)), int(gate.get("min_units", 6))
    except Exception as e:
        print("openkws: langpack unreadable (%s), using the built-in table" % e)
        return None


def verify_threshold(rec):
    """Second-stage threshold of an enroll record, or None when it has none.
    Chinese records carry it flat, English ones inside "verify"."""
    v = rec.get("verify")
    if isinstance(v, dict):
        return v.get("threshold")
    return rec.get("verify_threshold")


def syllables(rec):
    """Unit count per syllable of the main hypothesis, or None. Only English
    records store it; Chinese syllables are implied by the unit ids."""
    v = rec.get("verify")
    return v.get("syllables") if isinstance(v, dict) else None


# ---------------------------------------------------------------- engine

class Engine:
    """One language's engine. Create, use, close(); create another to switch."""

    def __init__(self, lang, root):
        if lang not in _NATIVE:
            raise ValueError("language %r is not in this firmware" % lang)
        p = PROFILES[lang]
        self.lang = lang
        self.profile = p
        self.root = root
        self.mod = _NATIVE[lang]
        self.enroll_dir = root + p["enroll_dir"]
        self.units = _read_units(root + p["units"])
        self.units_sha1 = _sha1_12(root + p["units"])
        self._eng = self.mod.Engine(root + p["model"], root + p["assets"])
        if p["langpack"]:
            self._apply_langpack(root + p["langpack"])
        self._eng.set_quality(clip_ratio=CLIP_RATIO_MAX, min_snr=MIN_SNR_DB)

    def _apply_langpack(self, path):
        lp = _read_langpack(path, self.units)
        if lp is None:
            return
        nuclei, onsets, min_nuclei, min_units = lp
        try:
            self._eng.set_langpack(nuclei, onsets, min_nuclei=min_nuclei, min_units=min_units)
            print("openkws[%s]: langpack %d nuclei / %d onsets, gate %d syllables / %d units"
                  % (self.lang, len(nuclei), len(onsets), min_nuclei, min_units))
        except Exception as e:
            print("openkws: set_langpack failed (%s), using the built-in table" % e)

    # -------------------------------------------------- lifetime
    def close(self):
        """Release the kmodel and its KPU tensors. Call before switching."""
        if self._eng is not None:
            try:
                self._eng.deinit()
            except Exception as e:
                print("openkws: deinit failed (%s)" % e)
            self._eng = None

    # -------------------------------------------------- streaming
    def push(self, pcm):
        """One PCM chunk in, wake-up events out, always as
        (kw_id, score, threshold, start_ms, end_ms, weakest_syllable).
        The Chinese module reports no weakest syllable, so it comes back None."""
        return self._six(self._eng.push(pcm))

    def flush(self):
        return self._six(self._eng.flush())

    def _six(self, events):
        if self.lang == "zh":
            return [(e[0], e[1], e[2], e[3], e[4], None) for e in events]
        return events

    def reset(self):
        self._eng.reset()

    def stats(self):
        return self._eng.stats()

    def set_vad(self, on):
        self._eng.set_vad(on)

    # -------------------------------------------------- keywords
    def add_keyword(self, rec):
        return self._eng.add_keyword(rec)

    def set_keywords(self, recs):
        self._eng.set_keywords(recs)

    def clear_keywords(self):
        self._eng.clear_keywords()

    def keywords(self):
        return self._eng.keywords()

    def accepts(self, rec):
        """Whether an enroll record belongs to this language's inventory.
        Without this an English record loads into the Chinese engine without
        complaint -- every English unit id is also a valid Chinese one -- and
        silently scores nonsense."""
        got = rec.get("units_sha1")
        if self.units_sha1 and got and got != self.units_sha1:
            return False
        n = rec.get("n_units")
        if n is not None and n != self.profile["n_units"]:
            return False
        lang = rec.get("lang")
        return lang is None or lang == self.lang

    def stamp(self, rec):
        """Tag a fresh record with the identity accepts() checks for."""
        rec["lang"] = self.lang
        if self.units_sha1:
            rec["units_sha1"] = self.units_sha1
        rec["n_units"] = self.profile["n_units"]
        return rec

    # -------------------------------------------------- tuning
    def set_tier(self, idx):
        """Apply one of the profile's sensitivity tiers; returns its label."""
        label, bias, n_hyps, alpha, delta = self.profile["tiers"][idx]
        self._eng.set_sensitivity(bias)
        self._eng.set_verify(n_hyps=n_hyps, alpha=alpha, delta=delta)
        return label

    def tier_bias(self, idx):
        return self.profile["tiers"][idx][1]

    # -------------------------------------------------- enrollment
    def enroll_begin(self):
        self._eng.enroll_begin()

    def enroll_add(self, pcm, noise=None):
        return self._eng.enroll_add(pcm, noise)

    def enroll_step(self):
        return self._eng.enroll_step()

    def enroll_result(self, kw_id):
        """The native record, tagged with the language identity. Each language
        keeps its own schema so the file stays loadable by its own module."""
        rec = self._eng.enroll_result(kw_id)
        if verify_threshold(rec) is None:
            rec["verify_threshold"] = self.profile["verify_threshold"]
        return self.stamp(rec)

    def enroll_confusion(self):
        return self._eng.enroll_confusion()

    def enroll_end(self):
        self._eng.enroll_end()

    def probe(self, rec, pcm):
        return self._eng.probe(rec, pcm)

    # -------------------------------------------------- display
    def unit_text(self, rec):
        """The main hypothesis as readable symbols. English groups them into
        syllables with "|", using the grouping stored at enrollment."""
        ids = rec["hypotheses"][0]["units"]
        if self.units:
            names = [self.units[u] if 0 <= u < len(self.units) else str(u) for u in ids]
        else:
            names = [str(u) for u in ids]
        syls = syllables(rec)
        if not syls:
            return " ".join(names)
        out, k = [], 0
        for n in syls:
            if k >= len(names):
                break
            out.append(" ".join(names[k:k + n]))
            k += n
        if k < len(names):
            out.append(" ".join(names[k:]))
        return " | ".join(out)


# ---------------------------------------------------------------- module helpers

def _any_native():
    for l in LANGS:
        if l in _NATIVE:
            return _NATIVE[l]
    raise ImportError("no keyword spotting module in this firmware")


# Sample rate and chunk size are the same for both models; take them from
# whichever module exists.
SAMPLE_RATE = _any_native().SAMPLE_RATE
CHUNK = _any_native().CHUNK
MAX_KEYWORDS = _any_native().MAX_KEYWORDS


def level(pcm):
    """(rms, peak) of an int16 chunk, both normalised to [0, 1]."""
    return _any_native().level(pcm)


def trim(pcm, lang=None):
    """Sample span of the spoken part, or None. Language independent, but the
    duration clamp differs slightly, so honour the caller's language."""
    mod = _NATIVE[lang] if lang in _NATIVE else _any_native()
    return mod.trim(pcm)
