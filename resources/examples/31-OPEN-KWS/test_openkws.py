# On-board test for open_kws / open_kws_en, driven through openkws.py.
#
# Run it on the board the same way as the example:
#     /sdcard/examples/31-OPEN-KWS/test_openkws.py
# Results go to the serial console; no display, no touch panel and no
# microphone are needed, every signal is synthesised. Nothing is written to
# the enrollment directories, so a run leaves registered words alone.
#
# The cases are chosen for where this code can go wrong *quietly*. Loading the
# other language's model or CMVN constants, loading a record that belongs to
# the other inventory, and failing to hand a kmodel back when the language
# switches all produce a system that looks healthy and behaves wrongly. Those
# get cases. Argument validation in the bindings, setters that echo a value
# back, and debug views nothing calls do not: when they break, they break
# loudly, and a test is not what finds them.
#
# Each check reports the first thing it found wrong, so a merged case still
# names the exact failure. Cases are independent; one failure does not stop
# the run.
#
# What it cannot tell you: numerical correctness or whether a real wake word
# actually fires. The acoustic path is never compared against reference
# values, so an algorithm returning well-formed but wrong numbers passes here;
# a real wake-up needs a microphone and a voice.
import sys

ROOT = "/sdcard/examples/31-OPEN-KWS/"
if ROOT[:-1] not in sys.path:
    sys.path.insert(0, ROOT[:-1])

import array
import gc
import math
import os

import openkws

SR = openkws.SAMPLE_RATE
CHUNK = openkws.CHUNK

# ---------------------------------------------------------------- harness

class Runner:
    def __init__(self):
        self.ok = self.fail = self.skip = 0
        self.failures = []

    def check(self, name, fn):
        """Run one case. fn() returns True, or raises, or returns a reason string."""
        try:
            r = fn()
        except Exception as e:
            self.fail += 1
            self.failures.append("%s: %s: %s" % (name, type(e).__name__, e))
            print("  FAIL %-44s %s: %s" % (name, type(e).__name__, e))
            return False
        if r is True:
            self.ok += 1
            print("  ok   %s" % name)
            return True
        self.fail += 1
        self.failures.append("%s: %s" % (name, r))
        print("  FAIL %-44s %s" % (name, r))
        return False

    def skipped(self, name, why):
        self.skip += 1
        print("  skip %-44s %s" % (name, why))

    def section(self, title):
        print("\n--- %s" % title)

    def summary(self):
        print("\n%s" % ("=" * 64))
        print("%d passed, %d failed, %d skipped" % (self.ok, self.fail, self.skip))
        for f in self.failures:
            print("  ! %s" % f)
        print("%s" % ("ALL PASSED" if not self.fail else "FAILED"))
        return self.fail == 0


def raises(fn, *types):
    """True when fn() raises one of types; a reason string otherwise."""
    try:
        fn()
    except types:
        return True
    except Exception as e:
        return "raised %s instead of %s" % (type(e).__name__,
                                            "/".join(t.__name__ for t in types))
    return "did not raise"


# ---------------------------------------------------------------- signals

def pcm_silence(n):
    return bytes(2 * n)


def pcm_tone(n, freq=440, amp=6000):
    buf = array.array("h", bytes(2 * n))
    k = 2.0 * math.pi * freq / SR
    for i in range(n):
        buf[i] = int(amp * math.sin(k * i))
    return bytes(buf)


def pcm_sweep(n, f0=180, f1=2600, amp=9000):
    """A rising chirp with an envelope: not speech, but broadband enough that
    the frontend and the encoder see something non-trivial."""
    buf = array.array("h", bytes(2 * n))
    for i in range(n):
        t = i / n
        f = f0 + (f1 - f0) * t
        env = min(1.0, 4.0 * t, 4.0 * (1.0 - t))
        buf[i] = int(amp * env * math.sin(2.0 * math.pi * f * i / SR))
    return bytes(buf)


# Units valid in both inventories (ids < 42 < 59), so one literal serves both.
def record(kw_id="t_kw", units=(18, 15, 22, 13, 25), th=-3.0, verify=None):
    rec = {"kw_id": kw_id, "threshold": th,
           "hypotheses": [{"units": list(units), "weight": 1.0}]}
    if verify is not None:
        rec["verify"] = verify
    return rec


# ---------------------------------------------------------------- module level

def test_module(r):
    r.section("module")

    def surface():
        langs = openkws.available()
        if not langs or any(l not in openkws.LANGS for l in langs):
            return "available() gave %s" % (langs,)
        if (SR, CHUNK, openkws.MAX_KEYWORDS) != (16000, 2560, 8):
            return "constants %d/%d/%d" % (SR, CHUNK, openkws.MAX_KEYWORDS)
        missing = [l for l in langs if l not in openkws.PROFILES]
        return not missing or "no profile for %s" % missing
    r.check("module surface", surface)

    def helpers():
        """level / trim / ensure_dir: metering, endpointing and writing a
        keyword all go through these."""
        rms, peak = openkws.level(pcm_tone(CHUNK))
        if not (0.0 < rms < 1.0 and 0.0 < peak < 1.0):
            return "level(tone) = %.4f/%.4f" % (rms, peak)
        if openkws.level(pcm_silence(CHUNK)) != (0.0, 0.0):
            return "level(silence) is not zero"
        if openkws.trim(pcm_silence(SR)) is not None:
            return "trim found speech in silence"
        span = openkws.trim(pcm_silence(SR // 2) + pcm_sweep(SR) + pcm_silence(SR // 2))
        if span is None:
            return "trim found nothing in a loud middle section"
        if not (0 <= span[0] < span[1] <= SR * 2):
            return "trim span %d..%d" % span
        d = ROOT + "enroll/_t/"
        openkws.ensure_dir(d)                       # nested: MicroPython has no makedirs
        made = "_t" in os.listdir(ROOT + "enroll")
        try:
            os.rmdir(d[:-1])
        except OSError:
            pass
        return made or "ensure_dir did not create a nested path"
    r.check("audio helpers", helpers)

    def schemas():
        """Chinese records carry the verification threshold flat, English ones
        inside verify{}; the facade has to read either."""
        if openkws.verify_threshold({"verify_threshold": -3.0}) != -3.0:
            return "flat verify_threshold not read"
        if openkws.verify_threshold({"verify": {"threshold": -6.0}}) != -6.0:
            return "nested verify.threshold not read"
        if openkws.verify_threshold({}) is not None:
            return "a record without a threshold did not give None"
        if openkws.syllables({"verify": {"syllables": [2, 3]}}) != [2, 3]:
            return "syllables not read"
        return openkws.syllables({"verify_threshold": -3.0}) is None or \
            "syllables invented for a flat record"
    r.check("both record schemas are readable", schemas)


# ---------------------------------------------------------------- per language

def test_engine(r, lang):
    """Construction and, more to the point, release.

    Switching language closes one engine and opens the other. If the kmodel is
    not handed back to the KPU pool the second open fails, so the reopen loop
    is the real subject here.
    """
    p = openkws.PROFILES[lang]

    def load_and_release():
        e = openkws.Engine(lang, ROOT)
        try:
            if len(e.units) != p["n_units"]:
                return "units %d, profile says %d" % (len(e.units), p["n_units"])
            if not e.units_sha1:
                return "no units_sha1"
            if e.lang != lang or e.enroll_dir != ROOT + p["enroll_dir"]:
                return "lang/enroll_dir wrong"
        finally:
            e.close()
        for _ in range(3):
            e = openkws.Engine(lang, ROOT)
            e.close()
            gc.collect()
        return True
    r.check("engine loads, reports itself, releases x3", load_and_release)


def test_cross_language(r, lang, eng):
    """The quiet failures. A mismatched kmodel, mismatched CMVN constants or a
    record from the other inventory all load without complaint and then score
    nonsense; each has a guard, and each guard is checked here."""
    other = "en" if lang == "zh" else "zh"
    if other not in openkws.available():
        r.skipped("cross-language guards", "only one language built")
        return

    def assets():
        mine, theirs = openkws.PROFILES[lang], openkws.PROFILES[other]
        native = openkws._NATIVE[lang]
        bad = raises(lambda: native.Engine(ROOT + theirs["model"], ROOT + mine["assets"]),
                     RuntimeError)
        if bad is not True:
            return "the other model: %s" % bad
        return raises(lambda: native.Engine(ROOT + mine["model"], ROOT + theirs["assets"]),
                      RuntimeError)
    r.check("the other language's model and assets are refused", assets)

    def records():
        mine = eng.stamp(record("mine"))
        if not (mine["lang"] == lang and mine["units_sha1"] == eng.units_sha1
                and mine["n_units"] == eng.profile["n_units"]):
            return "stamp() did not mark the record"
        if not eng.accepts(mine):
            return "own record refused"
        if not eng.accepts(record("legacy")):
            return "a legacy record carrying no identity was refused"
        foreign = dict(mine)
        foreign["lang"] = other
        foreign["units_sha1"] = "deadbeef1234"
        foreign["n_units"] = openkws.PROFILES[other]["n_units"]
        return (not eng.accepts(foreign)) or "a foreign record was accepted"
    r.check("foreign records refused, legacy ones kept", records)


def test_keywords(r, eng):
    def manage():
        eng.clear_keywords()
        if eng.add_keyword(record("a")) != 0 or eng.add_keyword(record("b")) != 1:
            return "indices are not sequential"
        if eng.keywords() != ["a", "b"]:
            return "keywords() gave %s" % (eng.keywords(),)
        eng.clear_keywords()
        eng.set_keywords([record("x"), record("y")])
        if eng.keywords() != ["x", "y"]:
            return "set_keywords gave %s" % (eng.keywords(),)
        eng.clear_keywords()
        for i in range(openkws.MAX_KEYWORDS):
            eng.add_keyword(record("k%d" % i))
        out = raises(lambda: eng.add_keyword(record("over")), ValueError)
        eng.clear_keywords()
        return out
    r.check("keywords add / replace / clear / limit", manage)

    def rejects():
        """One case over every malformed shape rather than one case each: this
        is stable validation code, it only needs to be known to still be on."""
        bad = {
            "no hypotheses": {"threshold": -3.0},
            "no threshold": {"hypotheses": [{"units": [3]}]},
            "no units": {"threshold": -3.0, "hypotheses": [{"weight": 1.0}]},
            "empty units": {"threshold": -3.0, "hypotheses": [{"units": []}]},
            "unit out of range": {"threshold": -3.0, "hypotheses": [{"units": [999]}]},
            "negative unit": {"threshold": -3.0, "hypotheses": [{"units": [-1]}]},
            "nine hypotheses": {"threshold": -3.0, "hypotheses": [{"units": [3]}] * 9},
            "not a dict": [1, 2],
        }
        for name, rec in bad.items():
            out = raises(lambda rec=rec: eng.add_keyword(rec), ValueError, TypeError)
            if out is not True:
                return "%s: %s" % (name, out)
        # A grouping whose lengths do not add up is ignored and re-derived from
        # the language pack, so an older or hand-edited record still loads.
        eng.clear_keywords()
        rec = record("s", units=(18, 15, 22), verify={"syllables": [2, 2], "threshold": -6.0})
        out = eng.add_keyword(rec) == 0 or "a mismatched verify.syllables was rejected"
        eng.clear_keywords()
        return out
    r.check("malformed records refused, mismatched grouping re-derived", rejects)


def test_streaming(r, eng):
    def stream():
        eng.clear_keywords()
        eng.add_keyword(record("s"))
        eng.reset()
        ev = eng.push(pcm_silence(CHUNK))
        if not isinstance(ev, list):
            return "push did not return a list"
        for e in ev:
            if len(e) != 6:
                return "event has %d fields, expected 6" % len(e)
        eng.reset()
        for _ in range(4):
            eng.push(pcm_silence(CHUNK))
        st = eng.stats()
        want = 4 * CHUNK * 1000.0 / SR
        if abs(st["audio_ms"] - want) > 1.0:
            return "clock advanced %.1f ms, expected %.1f" % (st["audio_ms"], want)
        need = ("audio_ms", "fe_ms", "kpu_ms", "dec_ms", "n_infer", "n_skip",
                "last_score", "chunk_max", "best_score", "level", "speech", "keywords")
        missing = [k for k in need if k not in st]
        if missing:
            return "stats missing %s" % missing
        return isinstance(st["keywords"], list) or "stats.keywords is not a list"
    r.check("push events, clock and stats", stream)

    def gating():
        """With the VAD on, silence must not reach the KPU; with it off, it
        must. The cheapest proof the gate is wired to the encoder at all."""
        eng.set_vad(True)
        eng.reset()
        for _ in range(6):
            eng.push(pcm_silence(CHUNK))
        skipped = eng.stats()["n_skip"]
        eng.set_vad(False)
        eng.reset()
        for _ in range(6):
            eng.push(pcm_silence(CHUNK))
        ran = eng.stats()["n_infer"]
        eng.set_vad(True)
        if skipped == 0:
            return "VAD on: nothing was skipped"
        return ran > 0 or "VAD off: no inference ran"
    r.check("VAD gates silence, disabling it runs the KPU", gating)

    def no_false_wake():
        """A threshold only a near-perfect match reaches, so a chirp firing
        means the trigger path is broken, not that the day was noisy."""
        eng.clear_keywords()
        eng.add_keyword(record("strict", th=-0.2))
        eng.set_vad(False)
        eng.reset()
        fired = []
        for _ in range(8):
            fired += eng.push(pcm_sweep(CHUNK))
        eng.set_vad(True)
        eng.clear_keywords()
        return not fired or "a chirp triggered %d wake-up(s)" % len(fired)
    r.check("a non-speech chirp does not wake a word", no_false_wake)


def test_enrollment(r, eng):
    """The state machine end to end: several steps, several early-exit error
    paths, and a progress counter only some of them touch.

    A chirp is not speech, so the run ends in a documented error rather than a
    keyword. What is checked is that the path executes and reports that error
    instead of hanging or raising something unexpected.
    """
    r.check("enroll_result before enroll_begin raises",
            lambda: raises(lambda: eng.enroll_result("t"), ValueError, RuntimeError))

    # The enroller captures the quality limits when enroll_begin() constructs
    # it, so they must be relaxed BEFORE that call -- a synthesised chirp has
    # too flat an energy profile to clear the default 10 dB SNR floor.
    eng._eng.set_quality(clip_ratio=1.0, min_snr=-200.0)
    eng.enroll_begin()

    def takes():
        if eng._eng.enroll_count() != 0:
            return "enroll_count did not start at zero"
        # Silence stays refused with the gate wide open: the peak check runs
        # ahead of the SNR one and set_quality cannot switch it off.
        ok, reason, m = eng.enroll_add(pcm_silence(SR), None)
        if ok:
            return "silence was accepted as a take"
        missing = [k for k in ("dur", "peak", "clip_ratio", "snr_db") if k not in m]
        if missing:
            return "metrics missing %s" % missing
        early = raises(lambda: eng.enroll_result("t"), ValueError)
        if early is not True:
            return "result before the steps finished: %s" % early
        refused = []
        for i in range(3):
            ok, reason, _ = eng.enroll_add(pcm_sweep(int(SR * 0.8), f0=200 + 90 * i), None)
            if not ok:
                refused.append(reason)
        if refused:
            return "takes refused: %s" % ", ".join(refused)
        return eng._eng.enroll_count() == 3 or "enroll_count did not follow"
    r.check("silence refused, three synthetic takes accepted", takes)

    def run():
        done, progress, total = False, 0, 1
        for _ in range(400):                       # bounded: the loop must end
            done, progress, total = eng.enroll_step()
            if done:
                break
        if not done:
            return "did not finish in 400 steps"
        if not (0 <= progress <= total):
            return "progress %d/%d out of range" % (progress, total)
        if total <= 1:
            return "three takes on file but total is %d" % total
        known = ("need at least 2 recordings", "no unit sequence decoded",
                 "no phoneme sequence decoded", "keyword too short",
                 "wake word too short", "recordings inconsistent", "model error")
        try:
            rec = eng.enroll_result("t_kw")
        except ValueError as e:
            return str(e) in known or "undocumented error %r" % str(e)
        for k in ("kw_id", "hypotheses", "threshold"):
            if k not in rec:
                return "record missing %s" % k
        return True
    r.check("enroll_step runs to a documented outcome", run)

    eng.enroll_end()
    eng._eng.set_quality(clip_ratio=openkws.CLIP_RATIO_MAX, min_snr=openkws.MIN_SNR_DB)
    r.check("enroll_add after enroll_end raises",
            lambda: raises(lambda: eng.enroll_add(pcm_tone(SR), None), RuntimeError))


def test_english_rules(r, eng):
    """The only language rule that runs on the board. Chinese syllables follow
    from the unit ids; English ones are cut at enrollment by the language pack
    and have to be right, because the second stage groups by those lengths."""
    def syllables():
        kendryte = [18, 15, 22, 13, 25, 11, 30, 8, 33]      # HH EY K EH N D R AY T
        got = eng._eng.syllabify(kendryte)
        if got != [2, 3, 4]:
            return "syllabify gave %s, expected [2, 3, 4]" % (got,)
        if eng._eng.syllabify([24, 24, 24]) is not None:    # M M M, no vowel nucleus
            return "a sequence with no vowel nucleus got a grouping"
        rendered = eng.unit_text(record("g", units=kendryte,
                                        verify={"syllables": [2, 3, 4], "threshold": -6.0}))
        return rendered.count("|") == 2 or "unit_text did not group: %r" % rendered
    r.check("syllabification and syllable rendering", syllables)


# ---------------------------------------------------------------- main

def main():
    print("open_kws interface test")
    print("languages in this firmware: %s" % (openkws.available(),))
    r = Runner()
    test_module(r)

    for lang in openkws.available():
        r.section(lang)
        test_engine(r, lang)
        eng = None
        try:
            eng = openkws.Engine(lang, ROOT)
            test_cross_language(r, lang, eng)
            test_keywords(r, eng)
            test_streaming(r, eng)
            test_enrollment(r, eng)
            if lang == "en":
                test_english_rules(r, eng)
        except Exception as e:
            r.fail += 1
            r.failures.append("%s: aborted: %s: %s" % (lang, type(e).__name__, e))
            print("  FAIL %s aborted: %s: %s" % (lang, type(e).__name__, e))
        finally:
            if eng is not None:
                eng.close()
            gc.collect()

    return r.summary()


if __name__ == "__main__":
    main()
