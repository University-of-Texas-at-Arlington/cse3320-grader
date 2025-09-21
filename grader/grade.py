#!/usr/bin/env python3
import argparse, json, os, re, sys, time, yaml, pexpect, pathlib

def spawn_qemu(timeout):
    # The xv6 Makefile usually has a qemu-nox target: no graphics/serial to stdio
    # If additional parameters are needed, you can add -snapshot to QEMUEXTRA in the Makefile to prevent disk writes
    return pexpect.spawn("/bin/bash", ["-lc", "make qemu-nox"], encoding="utf-8", timeout=timeout)

def expect_prompt(child, prompt_re):
    child.expect(prompt_re)

def run_cmd(child, cmd, ok_re, timeout):
    child.sendline(cmd)
    child.expect(ok_re, timeout=timeout)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--emit", default="")
    args = ap.parse_args()

    with open(args.spec) as f:
        spec = yaml.safe_load(f)

    boot_checks = spec.get("pre_boot_expect", [])      # Strings/regex expected during the boot phase
    prompt_re   = spec.get("boot_regex", r"\$ ")       # xv6 shell prompt
    cases       = spec["cases"]

    total  = sum(c.get("points", 5) for c in cases) + sum(i.get("points",5) for i in boot_checks)
    earned = 0
    results = []

    pathlib.Path("grade-report").mkdir(exist_ok=True)
    child = spawn_qemu(args.timeout)
    # Record the full serial log for review
    child.logfile = open("grade-report/qemu.log", "w", buffering=1)

    try:
        # First check: kernel boot phase output
        for it in boot_checks:
            name  = it["name"]
            regex = it["ok_regex"]
            pts   = it.get("points", 5)
            to    = it.get("timeout", args.timeout)
            try:
                child.expect(regex, timeout=to)
                earned += pts
                results.append({"name": name, "score": pts, "max_score": pts, "status": "passed"})
            except Exception as e:
                results.append({"name": name, "score": 0, "max_score": pts, "status": "failed", "reason": str(e)})

        # Wait for the shell prompt
        child.expect(prompt_re, timeout=args.timeout)

        # Then check: user-space commands
        for c in cases:
            name  = c["name"]
            cmd   = c["cmd"]
            regex = c["ok_regex"]
            pts   = c.get("points", 5)
            to    = c.get("timeout", args.timeout)
            try:
                child.sendline(cmd)
                child.expect(regex, timeout=to)
                earned += pts
                results.append({"name": name, "score": pts, "max_score": pts, "status": "passed"})
                # Return to the prompt to avoid interference with subsequent matches
                child.expect(prompt_re, timeout=args.timeout)
            except Exception as e:
                results.append({"name": name, "score": 0, "max_score": pts, "status": "failed", "reason": str(e)})

        # Attempt graceful exit
        try:
            child.sendcontrol('a'); child.send('x')
        except Exception:
            pass
    finally:
        try: child.terminate(force=True)
        except Exception: pass

    # Summary
    with open("grade-report/summary.txt","w") as f:
        for r in results:
            f.write(f"{r['name']}: {r['status']} ({r['score']}/{r['max_score']})\n")
    print(f"SCORE {earned}/{total}")

    if args.emit:
        out = {"tests":[{"name":r["name"],"score":r["score"],"max_score":r["max_score"]} for r in results]}
        with open(args.emit,"w") as f: json.dump(out, f, indent=2)

    sys.exit(0 if earned == total else 1)

if __name__ == "__main__":
    main()

    args = ap.parse_args()

    with open(args.spec) as f:
        spec = yaml.safe_load(f)

    prompt_re = spec.get("boot_regex", r"\$ ")
    cases = spec["cases"]

    total = sum(c.get("points",5) for c in cases)
    earned = 0
    results = []

    pathlib.Path("grade-report").mkdir(exist_ok=True)
    child = spawn_qemu(args.timeout)
    child.logfile = open("grade-report/qemu.log", "w", buffering=1)

    try:
        expect_prompt(child, prompt_re)

        for c in cases:
            name = c["name"]
            pts  = c.get("points",5)
            cmd  = c["cmd"]
            okre = c["ok_regex"]
            to   = c.get("timeout", args.timeout)
            try:
                run_cmd(child, cmd, okre, to)
                earned += pts
                results.append({"name": name, "score": pts, "max_score": pts, "status": "passed"})
            except Exception as e:
                results.append({"name": name, "score": 0, "max_score": pts, "status": "failed", "reason": str(e)})

        # Exit qemu (different branches may use Ctrl-a x; force terminate if it fails)
        try:
            child.sendcontrol('a'); child.send('x')
        except Exception:
            pass
    finally:
        try: child.terminate(force=True)
        except Exception: pass

    with open("grade-report/summary.txt","w") as f:
        for r in results:
            f.write(f"{r['name']}: {r['status']} ({r['score']}/{r['max_score']})\n")

    print(f"SCORE {earned}/{total}")

    if args.emit:
        out = {"tests":[{"name":r["name"],"score":r["score"],"max_score":r["max_score"]} for r in results]}
        with open(args.emit,"w") as f: json.dump(out, f, indent=2)

    sys.exit(0 if earned==total else 1)

if __name__ == "__main__":
    main()
